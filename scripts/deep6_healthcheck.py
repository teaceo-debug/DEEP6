#!/usr/bin/env python3
"""DEEP6 Pipeline Health Check — verify backend + WebSocket + frontend + schema alignment.

Usage:
    python scripts/deep6_healthcheck.py
    python scripts/deep6_healthcheck.py --backend-url http://localhost:8000
    python scripts/deep6_healthcheck.py --timeout 10 --verbose
    python scripts/deep6_healthcheck.py --skip-frontend

Exit codes:
    0 — all GREEN
    1 — any RED (hard failure)
    2 — any YELLOW (degraded / skipped)
"""
from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import re
import socket
import sys
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# ---------------------------------------------------------------------------
# ANSI colour helpers (no external deps)
# ---------------------------------------------------------------------------
_RESET  = "\033[0m"
_GREEN  = "\033[32m"
_RED    = "\033[31m"
_YELLOW = "\033[33m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[36m"

def _green(s: str)  -> str: return f"{_GREEN}{s}{_RESET}"
def _red(s: str)    -> str: return f"{_RED}{s}{_RESET}"
def _yellow(s: str) -> str: return f"{_YELLOW}{s}{_RESET}"
def _bold(s: str)   -> str: return f"{_BOLD}{s}{_RESET}"
def _dim(s: str)    -> str: return f"{_DIM}{s}{_RESET}"
def _cyan(s: str)   -> str: return f"{_CYAN}{s}{_RESET}"

PASS_ICON = _green("[✓]")
FAIL_ICON = _red("[✗]")
SKIP_ICON = _yellow("[?]")

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
_results: list[tuple[str, str, str]] = []  # (status, label, detail)

def _record(status: str, label: str, detail: str = "") -> None:
    _results.append((status, label, detail))
    icon = PASS_ICON if status == "PASS" else (FAIL_ICON if status == "FAIL" else SKIP_ICON)
    detail_str = f" {_dim('— ' + detail)}" if detail else ""
    print(f"  {icon} {label:<40}{detail_str}")

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _http_get(url: str, timeout: float) -> tuple[int, bytes]:
    """Return (status_code, body). Raises on connection error."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()

def _http_post(url: str, payload: dict, timeout: float) -> tuple[int, bytes]:
    """POST JSON. Returns (status_code, body)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

# ---------------------------------------------------------------------------
# WebSocket minimal client (pure stdlib — no `websockets` needed)
# ---------------------------------------------------------------------------
import base64
import hashlib
import os
import struct

class _WsClient:
    """Minimal WebSocket client over raw socket (RFC 6455 subset).

    Supports: connect, send_text (masked), recv_one_frame (text/binary),
    close. Enough for health-check purposes.
    """

    def __init__(self, host: str, port: int, path: str, timeout: float = 5.0):
        self._host = host
        self._port = port
        self._path = path
        self._timeout = timeout
        self._sock: Optional[socket.socket] = None

    def connect(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        s = socket.create_connection((self._host, self._port), timeout=self._timeout)
        s.sendall(
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: {self._host}:{self._port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n".encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = s.recv(4096)
            if not chunk:
                raise ConnectionError("Server closed connection during WS handshake")
            resp += chunk
        first_line = resp.split(b"\r\n", 1)[0]
        if b"101" not in first_line:
            raise ConnectionError(f"WS upgrade failed: {first_line.decode(errors='replace')}")
        self._sock = s

    def send_text(self, text: str) -> None:
        payload = text.encode()
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        length = len(payload)
        if length <= 125:
            header = struct.pack("BB", 0x81, 0x80 | length) + mask
        elif length <= 65535:
            header = struct.pack("!BBH", 0x81, 0xFE, length) + mask
        else:
            header = struct.pack("!BBQ", 0x81, 0xFF, length) + mask
        self._sock.sendall(header + masked)  # type: ignore[union-attr]

    def recv_frame(self, deadline: float) -> Optional[str]:
        """Read one WS frame, returning text. Returns None on timeout."""
        s = self._sock
        if s is None:
            return None
        s.settimeout(max(0.01, deadline - time.monotonic()))
        try:
            b0, b1 = struct.unpack("BB", _recv_exactly(s, 2))
            opcode = b0 & 0x0F
            masked = bool(b1 & 0x80)
            length = b1 & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", _recv_exactly(s, 2))
            elif length == 127:
                (length,) = struct.unpack("!Q", _recv_exactly(s, 8))
            mask_key = _recv_exactly(s, 4) if masked else b""
            data = _recv_exactly(s, length)
            if masked:
                data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
            if opcode in (0x1, 0x2):  # text or binary
                return data.decode(errors="replace")
            return None  # ping/pong/close — skip
        except (socket.timeout, TimeoutError):
            return None

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.sendall(struct.pack("BB", 0x88, 0x80) + b"\x00\x00\x00\x00")
            except Exception:
                pass
            self._sock.close()
            self._sock = None


def _recv_exactly(s: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed mid-frame")
        buf += chunk
    return buf


# ---------------------------------------------------------------------------
# Schema drift check
# ---------------------------------------------------------------------------
_PROJECT_ROOT = "/Users/teaceo/DEEP6"

def _extract_python_live_types() -> set[str]:
    """Parse LiveMessage union members from schemas.py via regex."""
    path = f"{_PROJECT_ROOT}/deep6/api/schemas.py"
    try:
        with open(path) as f:
            src = f.read()
    except FileNotFoundError:
        return set()
    # LiveMessage = Union[LiveBarMessage, LiveSignalMessage, ...]
    m = re.search(r"LiveMessage\s*=\s*Union\[([^\]]+)\]", src)
    if not m:
        return set()
    names = {n.strip() for n in m.group(1).split(",")}
    return names


def _extract_ts_live_types() -> set[str]:
    """Parse LiveMessage union members from deep6.ts via regex."""
    path = f"{_PROJECT_ROOT}/dashboard/types/deep6.ts"
    try:
        with open(path) as f:
            src = f.read()
    except FileNotFoundError:
        return set()
    # export type LiveMessage = | LiveBarMessage | LiveSignalMessage | ...;
    m = re.search(r"export\s+type\s+LiveMessage\s*=\s*((?:\s*\|\s*\w+)+)\s*;", src, re.DOTALL)
    if not m:
        return set()
    names = {n.strip().lstrip("|").strip() for n in re.findall(r"\|\s*(\w+)", m.group(1))}
    return names


_PY_TO_TS: dict[str, str] = {
    "LiveBarMessage":    "LiveBarMessage",
    "LiveSignalMessage": "LiveSignalMessage",
    "LiveScoreMessage":  "LiveScoreMessage",
    "LiveStatusMessage": "LiveStatusMessage",
    "LiveTapeMessage":   "LiveTapeMessage",
}

# ---------------------------------------------------------------------------
# Test payloads (one per LiveMessage type)
# ---------------------------------------------------------------------------
_NOW = time.time()
_SESSION_ID = "healthcheck-session"

_TEST_PAYLOADS = {
    "bar": {
        "type": "bar",
        "session_id": _SESSION_ID,
        "bar_index": 0,
        "bar": {
            "session_id": _SESSION_ID,
            "bar_index": 0,
            "ts": _NOW,
            "open": 19500.0, "high": 19510.0, "low": 19495.0, "close": 19505.0,
            "total_vol": 1000, "bar_delta": 50, "cvd": 200,
            "poc_price": 19503.0, "bar_range": 15.0,
            "running_delta": 200, "max_delta": 100, "min_delta": -20,
            "levels": {},
        },
    },
    "signal": {
        "type": "signal",
        "event": {
            "ts": _NOW, "bar_index_in_session": 0,
            "total_score": 72.0, "tier": "TYPE_B",
            "direction": 1, "engine_agreement": 0.8,
            "category_count": 3, "categories_firing": ["ABSORPTION"],
            "gex_regime": "NEUTRAL", "kronos_bias": 55.0,
        },
        "narrative": "Health check signal",
    },
    "score": {
        "type": "score",
        "total_score": 65.0, "tier": "TYPE_B",
        "direction": 1, "categories_firing": ["ABSORPTION"],
        "category_scores": {}, "kronos_bias": 55.0,
        "kronos_direction": "LONG", "gex_regime": "NEUTRAL",
    },
    "tape": {
        "type": "tape",
        "event": {
            "ts": _NOW, "price": 19505.0, "size": 10,
            "side": "ASK", "marker": "",
        },
    },
    "status": {
        "type": "status",
        "connected": True, "pnl": 0.0,
        "circuit_breaker_active": False, "feed_stale": False,
        "ts": _NOW,
        "session_start_ts": _NOW, "bars_received": 0,
        "signals_fired": 0, "last_signal_tier": "",
        "uptime_seconds": 0, "active_clients": 1,
    },
}

# ---------------------------------------------------------------------------
# Main check runner
# ---------------------------------------------------------------------------

def parse_url(url: str) -> tuple[str, int]:
    p = urllib.parse.urlparse(url)
    host = p.hostname or "localhost"
    port = p.port or (443 if p.scheme == "https" else 8000)
    return host, port


def run_checks(backend_url: str, frontend_url: str, timeout: float,
               verbose: bool, skip_frontend: bool) -> int:
    """Run all checks. Returns exit code (0/1/2)."""

    b_host, b_port = parse_url(backend_url)

    print()
    print(_bold("DEEP6 PIPELINE HEALTH CHECK"))
    print(_cyan("═" * 55))
    print()

    # ------------------------------------------------------------------
    # 1. Backend boot
    # ------------------------------------------------------------------
    backend_ok = False
    try:
        code, body = _http_get(f"{backend_url}/api/session/status", timeout)
        if code == 200:
            _record("PASS", "Backend boot", f"uvicorn :{b_port} responds")
            backend_ok = True
            if verbose:
                try:
                    data = json.loads(body)
                    print(_dim(f"         {json.dumps(data, indent=2)[:300]}"))
                except Exception:
                    pass
        else:
            _record("FAIL", "Backend boot", f"HTTP {code} (expected 200)")
    except Exception as e:
        _record("FAIL", "Backend boot",
                f"Connection refused — Is uvicorn running? Try: uvicorn deep6.api.app:app --port {b_port}")
        if verbose:
            print(_dim(f"         Error: {e}"))

    # ------------------------------------------------------------------
    # 2. HTTP endpoints
    # ------------------------------------------------------------------
    if backend_ok:
        try:
            code, body = _http_get(f"{backend_url}/api/session/status", timeout)
            if code == 200:
                data = json.loads(body)
                # Validate it has expected LiveStatusMessage fields
                required = {"connected", "ts", "pnl"}
                missing = required - set(data.keys())
                if missing:
                    _record("FAIL", "HTTP endpoints",
                            f"/api/session/status missing fields: {missing}")
                else:
                    _record("PASS", "HTTP endpoints", "/api/session/status → 200 with valid JSON")
            else:
                _record("FAIL", "HTTP endpoints", f"HTTP {code}")
        except Exception as e:
            _record("FAIL", "HTTP endpoints", str(e))
    else:
        _record("SKIP", "HTTP endpoints", "skipped — backend not reachable")

    # ------------------------------------------------------------------
    # 3. WebSocket accept
    # ------------------------------------------------------------------
    ws_ok = False
    ws_client: Optional[_WsClient] = None
    if backend_ok:
        try:
            ws_client = _WsClient(b_host, b_port, "/ws/live", timeout)
            ws_client.connect()
            ws_ok = True
            _record("PASS", "WebSocket accept", f"/ws/live → 101 Switching Protocols")
        except Exception as e:
            _record("FAIL", "WebSocket accept", str(e))
            ws_client = None
    else:
        _record("SKIP", "WebSocket accept", "skipped — backend not reachable")

    # ------------------------------------------------------------------
    # 4 + 5. Message round-trip + all 5 message types
    # ------------------------------------------------------------------
    if ws_ok and ws_client is not None:
        received_types: dict[str, bool] = {}

        # Collect frames in a background thread while we POST
        collected: list[str] = []
        stop_event = threading.Event()

        def _collect():
            deadline = time.monotonic() + timeout + 1.0
            while not stop_event.is_set() and time.monotonic() < deadline:
                frame = ws_client.recv_frame(deadline=time.monotonic() + 0.3)
                if frame:
                    collected.append(frame)

        collector = threading.Thread(target=_collect, daemon=True)
        collector.start()

        # Brief pause so the collector thread is listening
        time.sleep(0.05)

        # POST each message type
        post_errors = []
        for msg_type, payload in _TEST_PAYLOADS.items():
            try:
                code, resp_body = _http_post(
                    f"{backend_url}/api/live/test-broadcast", payload, timeout
                )
                if code != 200:
                    post_errors.append(f"{msg_type}: HTTP {code} — {resp_body.decode(errors='replace')[:100]}")
                elif verbose:
                    print(_dim(f"         POST type={msg_type!r} → HTTP {code}"))
            except Exception as e:
                post_errors.append(f"{msg_type}: {e}")

        # Wait for frames to arrive
        time.sleep(min(timeout * 0.5, 1.5))
        stop_event.set()
        collector.join(timeout=2.0)

        # Parse collected frames
        for raw in collected:
            try:
                msg = json.loads(raw)
                t = msg.get("type")
                if t:
                    received_types[t] = True
            except Exception:
                pass

        # Round-trip result (any message received = basic round-trip works)
        if received_types:
            first = next(iter(received_types))
            _record("PASS", "Message round-trip",
                    f"POST test-broadcast → received on WS (first: type={first!r})")
        else:
            detail = "; ".join(post_errors) if post_errors else "no frames received within timeout"
            _record("FAIL", "Message round-trip", detail)

        # All 5 types
        expected = {"bar", "signal", "score", "tape", "status"}
        missing_types = expected - set(received_types.keys())
        extra_detail = ""
        if post_errors:
            extra_detail = f"  POST errors: {'; '.join(post_errors)}"
        if not missing_types:
            _record("PASS", "All 5 message types",
                    "bar, signal, score, tape, status all received")
        else:
            _record("FAIL", "All 5 message types",
                    f"missing: {sorted(missing_types)}{extra_detail}")

        if verbose and extra_detail:
            print(_dim(f"         {extra_detail}"))

        # Clean up WS
        try:
            ws_client.close()
        except Exception:
            pass
    else:
        _record("SKIP", "Message round-trip", "skipped — WebSocket not connected")
        _record("SKIP", "All 5 message types", "skipped — WebSocket not connected")

    # ------------------------------------------------------------------
    # 6. Replay endpoint
    # ------------------------------------------------------------------
    if backend_ok:
        try:
            code, body = _http_get(f"{backend_url}/api/replay/sessions", timeout)
            if code == 200:
                data = json.loads(body)
                if isinstance(data, list):
                    session_count = len(data)
                    # Also test 404 for fake session
                    try:
                        code2, _ = _http_get(
                            f"{backend_url}/api/replay/fake-session-hc/0", timeout
                        )
                        graceful = code2 == 404
                    except urllib.error.HTTPError as he:
                        graceful = he.code == 404
                    except Exception:
                        graceful = False

                    graceful_str = "404 on unknown" if graceful else "no 404 on unknown"
                    _record("PASS" if graceful else "FAIL",
                            "Replay endpoint",
                            f"/api/replay/sessions → [{session_count} sessions]; {graceful_str}")
                else:
                    _record("FAIL", "Replay endpoint", "response is not a JSON array")
            else:
                _record("FAIL", "Replay endpoint", f"HTTP {code}")
        except Exception as e:
            _record("FAIL", "Replay endpoint", str(e))
    else:
        _record("SKIP", "Replay endpoint", "skipped — backend not reachable")

    # ------------------------------------------------------------------
    # 7. Frontend boot
    # ------------------------------------------------------------------
    f_host, f_port = parse_url(frontend_url)
    frontend_ok = False
    if skip_frontend:
        _record("SKIP", "Frontend boot", "--skip-frontend flag set")
    else:
        try:
            code, body = _http_get(f"{frontend_url}/", timeout)
            has_html = b"<html" in body.lower() or b"<!doctype" in body.lower()
            if code == 200 and has_html:
                _record("PASS", "Frontend boot", f"Next.js :{f_port} responds with HTML")
                frontend_ok = True
            elif code == 200:
                _record("PASS", "Frontend boot",
                        f"Next.js :{f_port} → 200 (no <html> tag — may be API route)")
                frontend_ok = True
            else:
                _record("FAIL", "Frontend boot",
                        f"HTTP {code} — Is Next.js running? Try: cd dashboard && npm run dev")
        except Exception as e:
            _record("FAIL", "Frontend boot",
                    f"Connection refused — Is Next.js running? Try: cd dashboard && npm run dev")
            if verbose:
                print(_dim(f"         Error: {e}"))

    # ------------------------------------------------------------------
    # 8. Frontend → WS (lightweight: verify WS port is actually open from
    #    loopback — no puppeteer needed)
    # ------------------------------------------------------------------
    if skip_frontend:
        _record("SKIP", "Frontend WS reachability", "--skip-frontend flag set")
    elif not frontend_ok:
        _record("SKIP", "Frontend WS reachability", "skipped — frontend not reachable")
    else:
        # Check the WS port is reachable from loopback (same host as frontend)
        try:
            s = socket.create_connection((b_host, b_port), timeout=timeout)
            s.close()
            _record("PASS", "Frontend WS reachability",
                    f"WS port {b_port} reachable from loopback (browser can connect)")
        except Exception as e:
            _record("FAIL", "Frontend WS reachability",
                    f"WS port {b_port} not reachable: {e}")

    # ------------------------------------------------------------------
    # 9. Schema sync — LiveMessage TS union ↔ Python
    # ------------------------------------------------------------------
    py_types = _extract_python_live_types()
    ts_types = _extract_ts_live_types()

    if not py_types:
        _record("SKIP", "Schema sync",
                "Could not parse deep6/api/schemas.py LiveMessage union")
    elif not ts_types:
        _record("SKIP", "Schema sync",
                "Could not parse dashboard/types/deep6.ts LiveMessage union")
    else:
        # Normalise: Python uses class names, TS uses interface names — same names here
        drift = []
        for py_name in py_types:
            ts_name = _PY_TO_TS.get(py_name, py_name)
            if ts_name not in ts_types:
                drift.append(f"{py_name} → {ts_name} missing in TS")
        for ts_name in ts_types:
            if ts_name not in _PY_TO_TS.values():
                drift.append(f"{ts_name} in TS but not in Python union")

        if not drift:
            types_str = ", ".join(sorted(ts_types))
            _record("PASS", "Schema sync",
                    f"LiveMessage union aligned ({len(ts_types)} types: {types_str})")
        else:
            _record("FAIL", "Schema sync", f"drift detected: {'; '.join(drift)}")

        if verbose:
            print(_dim(f"         Python types : {sorted(py_types)}"))
            print(_dim(f"         TS types     : {sorted(ts_types)}"))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print(_cyan("═" * 55))

    n_pass = sum(1 for r in _results if r[0] == "PASS")
    n_fail = sum(1 for r in _results if r[0] == "FAIL")
    n_skip = sum(1 for r in _results if r[0] == "SKIP")
    total  = len(_results)

    if n_fail == 0 and n_skip == 0:
        verdict = _green(f"RESULT: {n_pass}/{total} GREEN — READY FOR LIVE DATA")
        exit_code = 0
    elif n_fail == 0:
        verdict = _yellow(f"RESULT: {n_pass}/{total} GREEN, {n_skip} SKIPPED — DEGRADED")
        exit_code = 2
    else:
        verdict = _red(f"RESULT: {n_pass}/{total} GREEN, {n_fail} FAILED — NOT READY")
        exit_code = 1

    print(f"  {_bold(verdict)}")
    print()

    if n_fail > 0:
        print(_red("  Failed checks:"))
        for status, label, detail in _results:
            if status == "FAIL":
                print(f"    {FAIL_ICON} {label}")
                if detail:
                    print(f"       {_dim(detail)}")
        print()

    return exit_code


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DEEP6 end-to-end pipeline health check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--backend-url",  default="http://localhost:8000",
                        help="FastAPI backend base URL (default: http://localhost:8000)")
    parser.add_argument("--frontend-url", default="http://localhost:3000",
                        help="Next.js frontend base URL (default: http://localhost:3000)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="Per-test timeout in seconds (default: 5)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show individual request details")
    parser.add_argument("--skip-frontend", action="store_true",
                        help="Skip frontend checks (if dashboard is not running)")
    args = parser.parse_args()

    exit_code = run_checks(
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
        timeout=args.timeout,
        verbose=args.verbose,
        skip_frontend=args.skip_frontend,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
