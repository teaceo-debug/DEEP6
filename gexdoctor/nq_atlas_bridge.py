#!/usr/bin/env python3
"""
GEX Doctor — NQ Atlas Bridge
============================================================
Reads live GEX data from the local nq_atlas server
(http://localhost:8766) and writes enriched gex_nq.json for
the NinjaTrader GEXDoctor indicator to read.

Use this instead of the main gexdoctor producer when the
FlashAlpha API quota is exhausted or you want to avoid
double-polling the same API key.

Usage:
    python nq_atlas_bridge.py                    # continuous, 15s
    python nq_atlas_bridge.py --once             # single cycle
    python nq_atlas_bridge.py --interval 30      # custom interval
    python nq_atlas_bridge.py --url http://localhost:8766
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("httpx not installed. Run: pip install httpx")

log = logging.getLogger("nq_atlas_bridge")

DEFAULT_ATLAS_URL = "http://localhost:8766"
DEFAULT_OUTPUT = Path(
    r"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json"
)
DEFAULT_INTERVAL = 15


# ---------------------------------------------------------------------------
# Data reading
# ---------------------------------------------------------------------------

def fetch_atlas_state(base_url: str, timeout: float = 5.0) -> dict:
    """GET /state from nq_atlas. Returns full state dict."""
    resp = httpx.get(f"{base_url}/state", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _f(d: dict, *keys, default=None) -> float | None:
    """Safely walk nested dicts and return a float or None."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def _s(d: dict, *keys, default: str = "") -> str:
    """Safely walk nested dicts and return a string."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return str(cur) if cur is not None else default


# ---------------------------------------------------------------------------
# State → enriched JSON
# ---------------------------------------------------------------------------

def build_output(state: dict) -> dict:
    """Convert nq_atlas state dict to enriched gex_nq.json payload."""
    spots   = state.get("spots") or {}
    fa      = state.get("flashalpha") or {}
    bias    = state.get("bias") or {}
    fa_lvl  = (fa.get("levels") or {}).get("levels") or {}
    fa_sum  = fa.get("summary") or {}
    fa_0dte = fa.get("zero_dte") or {}
    fa_pin  = fa_0dte.get("pin_risk") or {}
    fa_exp  = fa_sum.get("exposures") or {}
    fa_0lvl = fa_0dte.get("levels") or {}

    # -- Spots & conversion factor --
    qqq_spot = _f(spots, "QQQ") or 0.0
    nq_spot  = _f(spots, "NQ")  or 0.0
    factor   = (nq_spot / qqq_spot) if qqq_spot > 0 else 41.0

    def to_nq(v):
        return round(v * factor, 2) if v is not None else None

    # -- Levels (QQQ → NQ) --
    # Prefer zero_dte levels when available (more precise intraday),
    # fall back to full-chain levels
    gamma_flip = to_nq(
        _f(fa_lvl, "gamma_flip")
        or _f(fa_0dte.get("regime") or {}, "gamma_flip")
    )
    call_wall = to_nq(
        _f(fa_0lvl, "call_wall")
        or _f(fa_lvl, "call_wall")
    )
    put_wall = to_nq(
        _f(fa_0lvl, "put_wall")
        or _f(fa_lvl, "put_wall")
    )
    max_pain  = to_nq(_f(fa_pin, "max_pain"))
    magnet_qqq = _f(fa_pin, "magnet_strike") or _f(fa_lvl, "zero_dte_magnet")
    primary_magnet = to_nq(magnet_qqq)

    # -- Regime --
    regime_raw = _s(fa_sum, "regime") or _s(
        (fa_0dte.get("regime") or {}), "label"
    )
    if "positive" in regime_raw.lower():
        regime = "POS_GEX"
    elif "negative" in regime_raw.lower():
        regime = "NEG_GEX"
    else:
        regime = "NEUTRAL"

    # -- Net GEX --
    net_gex = _f(fa_exp, "net_gex") or _f(state.get("gex") or {}, "net_gex")

    # -- Pin risk --
    pin_risk = _f(fa_pin, "pin_score")  # 0-100 score from zero_dte

    # -- Magnet confidence (pin_score → 0.0-1.0) --
    magnet_confidence = round(min(pin_risk / 100.0, 1.0), 3) if pin_risk else 0.65

    # -- Bias --
    bias_dir_raw = _s(bias, "direction").lower()
    if bias_dir_raw == "bullish":
        bias_direction = "bullish"
    elif bias_dir_raw == "bearish":
        bias_direction = "bearish"
    else:
        bias_direction = "neutral"

    # Map conviction 0-10 → simple lean text
    conviction = _f(bias, "conviction") or 0
    lean = _s(bias, "narrative") or f"{bias_direction.title()} ({regime})"
    if len(lean) > 120:
        lean = lean[:117] + "..."

    # -- Invalidation --
    if primary_magnet and gamma_flip:
        if primary_magnet > nq_spot:
            invalidation_level = gamma_flip - 10
            invalidation_reason = "Break below gamma flip invalidates upside magnet pull"
        else:
            invalidation_level = gamma_flip + 10
            invalidation_reason = "Break above gamma flip invalidates downside magnet pull"
    else:
        invalidation_level = None
        invalidation_reason = "No clear magnet"

    # -- Caveats --
    caveats = []
    errors = state.get("errors") or []
    for e in errors[-1:]:  # only most recent error
        msg = e.get("msg", "")
        if "quota" in msg.lower():
            caveats.append("FlashAlpha quota exhausted — using last cached data")
            break
    if state.get("degraded"):
        caveats.append("nq_atlas in degraded state")

    # -- As-of timestamp --
    # Use current write time, not the FA cache timestamp.
    # The FA timestamp can be many minutes old (e.g. after quota exhaustion),
    # which causes the NT8 indicator to show STALE immediately.
    as_of = datetime.now(timezone.utc).isoformat()

    return {
        "instrument":          "NQ",
        "flip":                gamma_flip,
        "call_wall":           call_wall,
        "put_wall":            put_wall,
        "next_call":           None,
        "next_put":            None,
        "net_gex":             net_gex,
        "regime":              regime,
        "primary_magnet":      primary_magnet,
        "magnet_confidence":   magnet_confidence,
        "bias_direction":      bias_direction,
        "invalidation_level":  round(invalidation_level, 2) if invalidation_level else None,
        "invalidation_reason": invalidation_reason,
        "lean":                lean,
        "pin_risk":            pin_risk,
        "max_pain":            max_pain,
        "caveats":             caveats,
        "as_of":               as_of,
        "source":              f"nq_atlas-bridge-x{factor:.2f}",
        "stale_after_seconds": 300,
        "nq_spot":             round(nq_spot, 2),
        "qqq_spot":            round(qqq_spot, 4),
    }


# ---------------------------------------------------------------------------
# Atomic write (same pattern as gex_producer.py)
# ---------------------------------------------------------------------------

def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        tmp.replace(path)           # atomic rename — preferred
    except (PermissionError, OSError):
        # NT8 may have the file locked; fall back to direct overwrite
        try:
            path.write_text(content, encoding="utf-8")
        except Exception:
            pass
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Level cache — survive quota gaps without going blank
# ---------------------------------------------------------------------------

_level_cache: dict = {
    # Hardcoded fallback: last known good EOD levels from 2026-05-28
    # These will be used when nq_atlas returns null (FA quota exhausted)
    # and overwritten automatically when live data becomes available again.
    "flip": 28804.6,
    "call_wall": 30242.82,
    "put_wall": 30001.73,
    "primary_magnet": 30201.73,
    "invalidation_level": 28814.6,
    "pin_risk": 74.0,
    "max_pain": 29873.01,
}


def _seed_cache_from_file(path: Path) -> None:
    """On startup, load last known good levels from existing gex_nq.json."""
    global _level_cache
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("flip") and data.get("call_wall") and data.get("put_wall"):
            for k in ("flip", "call_wall", "put_wall", "primary_magnet",
                      "invalidation_level", "pin_risk", "max_pain"):
                if data.get(k) is not None:
                    _level_cache[k] = data[k]
            log.info("seeded level cache from existing file: flip=%s CW=%s PW=%s",
                     _level_cache.get("flip"), _level_cache.get("call_wall"), _level_cache.get("put_wall"))
    except Exception as exc:
        log.debug("could not seed cache from file: %s", exc)


def _merge_cache(payload: dict) -> dict:
    """If current payload has null walls, fill from cache. Update cache on good data."""
    global _level_cache
    level_keys = ("flip", "call_wall", "put_wall", "primary_magnet",
                  "invalidation_level", "pin_risk", "max_pain")
    has_levels = payload.get("flip") and payload.get("call_wall") and payload.get("put_wall")

    if has_levels:
        # Good data — update the cache
        for k in level_keys:
            if payload.get(k) is not None:
                _level_cache[k] = payload[k]
        return payload

    if _level_cache:
        # No live levels — fill from cache, flag as cached
        merged = dict(payload)
        for k in level_keys:
            if k in _level_cache:
                merged[k] = _level_cache[k]
        caveats = list(merged.get("caveats") or [])
        if not any("cached" in c.lower() for c in caveats):
            caveats.insert(0, "Showing last known levels (FA quota exhausted - resets midnight UTC)")
        merged["caveats"] = caveats
        merged["source"] = merged.get("source", "") + "-cached"
        merged["stale_after_seconds"] = 86400  # don't flicker stale on cached data
        return merged

    return payload


# ---------------------------------------------------------------------------
# Single cycle
# ---------------------------------------------------------------------------

def run_cycle(atlas_url: str, output_path: Path) -> dict | None:
    try:
        state = fetch_atlas_state(atlas_url)
    except Exception as exc:
        log.error("nq_atlas fetch failed: %s", exc)
        return None

    payload = _merge_cache(build_output(state))
    write_atomic(output_path, payload)

    log.info(
        "wrote gex_nq.json  magnet=%-10s  flip=%-10s  CW=%-10s  PW=%-10s  regime=%s  bias=%s",
        payload["primary_magnet"],
        payload["flip"],
        payload["call_wall"],
        payload["put_wall"],
        payload["regime"],
        payload["bias_direction"],
    )
    return payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="GEX Doctor — NQ Atlas Bridge")
    p.add_argument("--url",      default=DEFAULT_ATLAS_URL, help="nq_atlas base URL")
    p.add_argument("--output",   default=str(DEFAULT_OUTPUT), help="Output JSON path")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                   help="Poll interval seconds (default 15)")
    p.add_argument("--once",     action="store_true", help="Run one cycle and exit")
    p.add_argument("--verbose",  action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    output_path = Path(args.output)
    interval    = max(10, args.interval)

    # Seed cache from existing file so levels survive quota gaps / restarts
    _seed_cache_from_file(output_path)

    if args.once:
        result = run_cycle(args.url, output_path)
        if result:
            print(f"magnet={result['primary_magnet']}  flip={result['flip']}"
                  f"  CW={result['call_wall']}  PW={result['put_wall']}"
                  f"  regime={result['regime']}  bias={result['bias_direction']}")
            return 0
        return 1

    print(f"GEX Doctor Bridge  ->  {args.url}  ->  {output_path}")
    print(f"Interval: {interval}s  |  Ctrl+C to stop\n")

    consecutive_failures = 0
    while True:
        t0 = time.monotonic()
        result = run_cycle(args.url, output_path)
        if result is None:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                log.error("5 consecutive failures — sleeping 5 min")
                time.sleep(300)
                consecutive_failures = 0
        else:
            consecutive_failures = 0

        elapsed = time.monotonic() - t0
        sleep_for = max(1.0, interval - elapsed)
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
