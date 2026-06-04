"""MAD Levels Service — polls Telegram channels every 5s, writes JSON for NT8.

Uses polling (iter_messages with min_id) instead of event handlers — much more
reliable for private channels. Runs hidden with a system tray icon.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import tempfile
import threading
from datetime import datetime, timezone, timedelta, time as dtime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import pystray
from telethon import TelegramClient
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import ChatInviteAlready

# ── Paths ───────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parents[1]
load_dotenv(SCRIPT_DIR / ".env")

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_FILE = str(SCRIPT_DIR / "deep6_telegram")

NQ_CHANNEL_HASH = "J4WHzA8EE5E2N2Nl"
ES_CHANNEL_HASH = "mAiBHnFQ3gA4YjA1"

RAW_NQ_PATH = ROOT / "data" / "telegram_levels" / "raw_nq.json"
RAW_ES_PATH = ROOT / "data" / "telegram_levels" / "raw_es.json"
NT8_TEMPLATES = Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6"
OUTPUT_PATH = NT8_TEMPLATES / "mad_levels.json"

LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "mad_levels_service.log"
PID_PATH = SCRIPT_DIR / ".mad_levels.pid"

ET = ZoneInfo("America/New_York")
TICK_SIZE = 0.25
CLUSTER_TICKS = 4
POLL_SECONDS = 5

NQ_ABSORPTION_RE = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
ES_ABSORPTION_RE = re.compile(r"^ES absorption at:\s*([\d.]+)$")

# ── Logging ─────────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
log = logging.getLogger("mad")
log.setLevel(logging.INFO)
_fh = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s", datefmt="%H:%M:%S"))
log.addHandler(_fh)
try:
    if sys.stderr and hasattr(sys.stderr, "fileno"):
        sys.stderr.fileno()
        _sh = logging.StreamHandler(sys.stderr)
        _sh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        log.addHandler(_sh)
except (OSError, ValueError):
    pass


# ── Lock / PID ──────────────────────────────────────────────────────────
def acquire_lock() -> bool:
    if PID_PATH.exists():
        try:
            old_pid = int(PID_PATH.read_text().strip())
            os.kill(old_pid, 0)
            log.error("Already running (PID %d)", old_pid)
            return False
        except (OSError, ValueError):
            pass
    PID_PATH.write_text(str(os.getpid()))
    return True


def release_lock():
    PID_PATH.unlink(missing_ok=True)


# ── Session window ──────────────────────────────────────────────────────
def session_window_for_date(d):
    s = d.replace(hour=8, minute=30, second=0, microsecond=0)
    e = d.replace(hour=16, minute=0, second=0, microsecond=0)
    return s.astimezone(timezone.utc), e.astimezone(timezone.utc)


def find_latest_session(timestamps):
    now_et = datetime.now(ET)
    for days_back in range(8):
        candidate = now_et - timedelta(days=days_back)
        start, end = session_window_for_date(candidate)
        for ts_str in timestamps:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if start <= ts <= end:
                    return start, end
            except (ValueError, TypeError):
                continue
    return session_window_for_date(now_et)


def parse_ts(s):
    try:
        ts = datetime.fromisoformat(s)
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


# ── Monitor ─────────────────────────────────────────────────────────────
class Monitor:
    def __init__(self):
        self.levels: list[dict] = []
        self.session_start = datetime.min.replace(tzinfo=timezone.utc)
        self.session_end = datetime.min.replace(tzinfo=timezone.utc)

    def load_historical(self):
        self.levels.clear()
        all_ts = []
        raw = {}
        for path, src in [(RAW_NQ_PATH, "NQ"), (RAW_ES_PATH, "ES")]:
            if not path.exists():
                log.info("%s: no raw file", src)
                continue
            msgs = json.loads(path.read_text(encoding="utf-8"))
            raw[src] = msgs
            for m in msgs:
                if m.get("date"):
                    all_ts.append(m["date"])

        self.session_start, self.session_end = find_latest_session(all_ts)
        se = self.session_start.astimezone(ET)
        log.info("Session: %s %s-%s ET", se.strftime("%b %d"),
                 se.strftime("%I:%M%p"), self.session_end.astimezone(ET).strftime("%I:%M%p"))

        for src, msgs in raw.items():
            rx = NQ_ABSORPTION_RE if src == "NQ" else ES_ABSORPTION_RE
            n = 0
            for m in msgs:
                txt = (m.get("text") or "").strip()
                ts_str = m.get("date", "")
                if not txt or not ts_str:
                    continue
                ts = parse_ts(ts_str)
                if ts < self.session_start or ts > self.session_end:
                    continue
                if match := rx.match(txt):
                    self.levels.append({"price": float(match.group(1)), "source": src,
                                        "type": "absorption", "timestamp_utc": ts_str, "count": 1})
                    n += 1
            log.info("  %s: %d absorptions", src, n)

        self._deduplicate()
        self._write_json()
        log.info("Wrote %d levels", len(self.levels))

    def add_level(self, price, source, ts_str, msg_id=None):
        now_et = datetime.now(ET)
        today_start, today_end = session_window_for_date(now_et)
        ts = parse_ts(ts_str)

        if today_start <= ts <= today_end:
            if self.session_start != today_start:
                log.info("New session day")
                self.levels.clear()
                self.session_start = today_start
                self.session_end = today_end
        elif not (self.session_start <= ts <= self.session_end):
            # ALWAYS accept — just log that it's outside RTH
            log.info("Outside RTH but accepting: %s %.2f at %s", source, price, ts_str)

        self.levels.append({"price": price, "source": source, "type": "absorption",
                            "timestamp_utc": ts_str, "count": 1})
        self._deduplicate()
        self._write_json()
        self._append_raw(price, source, ts_str, msg_id)
        log.info(">>> NEW %s %.2f — %d levels", source, price, len(self.levels))
        return True

    def _deduplicate(self):
        cd = TICK_SIZE * CLUSTER_TICKS
        by_src = {}
        for lv in self.levels:
            by_src.setdefault(lv["source"], []).append(lv)
        merged = []
        for src, grp in by_src.items():
            grp.sort(key=lambda r: r["price"])
            clusters = []
            for rec in grp:
                found = False
                for c in clusters:
                    if abs(rec["price"] - c["price"]) <= cd:
                        if rec["timestamp_utc"] > c["timestamp_utc"]:
                            c["timestamp_utc"] = rec["timestamp_utc"]
                        c["count"] = c.get("count", 1) + 1
                        found = True
                        break
                if not found:
                    clusters.append({**rec})
            merged.extend(clusters)
        self.levels = merged

    def _write_json(self):
        nq_levels = [l for l in self.levels if l["source"] == "NQ"]
        es_levels = [l for l in self.levels if l["source"] == "ES"]

        # Auto-compute ES→NQ ratio from latest prices in both channels
        ratio = 0.0
        if nq_levels and es_levels:
            latest_nq = max(nq_levels, key=lambda l: l["timestamp_utc"])["price"]
            latest_es = max(es_levels, key=lambda l: l["timestamp_utc"])["price"]
            if latest_es > 0:
                ratio = latest_nq / latest_es

        # Stamp nq_equivalent on every ES level
        out_levels = []
        for lv in self.levels:
            entry = {**lv}
            if lv["source"] == "ES" and ratio > 0:
                entry["nq_equivalent"] = round(lv["price"] * ratio, 2)
            out_levels.append(entry)

        if ratio > 0:
            log.info("ES→NQ ratio: %.4f", ratio)

        payload = {
            "service": "mad_levels_service", "version": "3.1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "session_start_utc": self.session_start.isoformat(),
            "session_end_utc": self.session_end.isoformat(),
            "session_date_et": self.session_start.astimezone(ET).strftime("%Y-%m-%d"),
            "nq_count": len(nq_levels), "es_count": len(es_levels),
            "es_nq_ratio": round(ratio, 4) if ratio > 0 else None,
            "levels": out_levels,
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=str(OUTPUT_PATH.parent), prefix=".mad.", suffix=".tmp", delete=False) as tmp:
            tmp.write(data); tmp.flush(); os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, OUTPUT_PATH)
        _update_tray("Live", f"{len(nq_levels)} NQ + {len(es_levels)} ES levels", "green")

    @staticmethod
    def _append_raw(price, source, ts_str, msg_id=None):
        path = RAW_NQ_PATH if source == "NQ" else RAW_ES_PATH
        entry = {"message_id": msg_id, "date": ts_str, "edit_date": None,
                 "sender_id": None, "text": f"{source} absorption at: {price:.2f}",
                 "media_type": None, "reply_to": None, "forwarded": False}
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            existing.insert(0, entry)
            path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.warning("append_raw: %s", e)


# ── Tray icon ───────────────────────────────────────────────────────────
_tray_icon = None
_tray_status = "Starting..."
_tray_levels = ""


def _make_icon(color="green"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(30, 30, 30, 230))
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default()
    draw.text((14, 12), "M", fill=(255, 255, 80), font=font)
    dc = {"green": (0, 200, 0), "red": (200, 0, 0), "yellow": (200, 200, 0)}.get(color, (128, 128, 128))
    draw.ellipse([44, 44, 60, 60], fill=dc)
    return img


def _update_tray(status, levels="", color="green"):
    global _tray_status, _tray_levels
    _tray_status = status
    _tray_levels = levels
    if _tray_icon and _tray_icon.visible:
        _tray_icon.icon = _make_icon(color)
        _tray_icon.title = f"MAD Levels — {status}"


def _open_log(icon, item):
    os.startfile(str(LOG_PATH))


def _stop_service(icon, item):
    log.info("Stop from tray")
    icon.stop()
    os._exit(0)


def _start_tray():
    global _tray_icon
    menu = pystray.Menu(
        pystray.MenuItem(lambda t: f"Status: {_tray_status}", None, enabled=False),
        pystray.MenuItem(lambda t: _tray_levels or "No levels", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Log", _open_log),
        pystray.MenuItem("Stop Service", _stop_service),
    )
    _tray_icon = pystray.Icon("MAD Levels", _make_icon("yellow"), "MAD Levels — Starting...", menu)
    _tray_icon.run()


# ── Telegram poller (not event-based — much more reliable) ──────────────
async def resolve_channel(client, invite_hash, label):
    try:
        result = await client(CheckChatInviteRequest(invite_hash))
        if isinstance(result, ChatInviteAlready):
            entity = result.chat
            log.info("  %s: %s (id=%d)", label, getattr(entity, "title", ""), entity.id)
            return entity
        from telethon.tl.functions.messages import ImportChatInviteRequest
        updates = await client(ImportChatInviteRequest(invite_hash))
        if updates.chats:
            e = updates.chats[0]
            log.info("  %s: joined %s", label, getattr(e, "title", ""))
            return e
    except Exception as e:
        log.error("  %s: %s", label, e)
    return None


def get_last_msg_id(path: Path) -> int:
    """Get the highest message_id from a raw JSON file."""
    if not path.exists():
        return 0
    try:
        msgs = json.loads(path.read_text(encoding="utf-8"))
        return max((m.get("message_id") or 0) for m in msgs) if msgs else 0
    except Exception:
        return 0


async def run_monitor():
    monitor = Monitor()
    log.info("Loading historical...")
    monitor.load_historical()

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH,
                            auto_reconnect=True, connection_retries=None, retry_delay=5)
    await client.connect()

    if not await client.is_user_authorized():
        log.error("Not authorized — run download_history.py first")
        _update_tray("Not authorized", color="red")
        return

    me = await client.get_me()
    log.info("Telegram: %s", me.first_name)

    log.info("Resolving channels...")
    nq_entity = await resolve_channel(client, NQ_CHANNEL_HASH, "NQ")
    es_entity = await resolve_channel(client, ES_CHANNEL_HASH, "ES")

    if not nq_entity and not es_entity:
        log.error("No channels resolved")
        _update_tray("No channels", color="red")
        return

    # Get the last known message IDs to only fetch NEW messages
    nq_last_id = get_last_msg_id(RAW_NQ_PATH)
    es_last_id = get_last_msg_id(RAW_ES_PATH)
    log.info("Starting poll loop (every %ds) — NQ last_id=%d, ES last_id=%d",
             POLL_SECONDS, nq_last_id, es_last_id)

    nq_n = sum(1 for l in monitor.levels if l["source"] == "NQ")
    es_n = sum(1 for l in monitor.levels if l["source"] == "ES")
    _update_tray("Live", f"{nq_n} NQ + {es_n} ES levels", "green")

    # ── Poll loop ───────────────────────────────────────────────────────
    while True:
        try:
            # Check NQ channel for new messages
            if nq_entity:
                async for msg in client.iter_messages(nq_entity, min_id=nq_last_id, limit=50):
                    if msg.id <= nq_last_id:
                        continue
                    nq_last_id = max(nq_last_id, msg.id)
                    text = (msg.text or "").strip()
                    if not text:
                        continue
                    ts = msg.date
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts_str = ts.isoformat()
                    log.info("NQ msg #%d: %s", msg.id, text[:80])
                    if m := NQ_ABSORPTION_RE.match(text):
                        monitor.add_level(float(m.group(1)), "NQ", ts_str, msg.id)
                    else:
                        log.info("  (no regex match)")

            # Check ES channel for new messages
            if es_entity:
                async for msg in client.iter_messages(es_entity, min_id=es_last_id, limit=50):
                    if msg.id <= es_last_id:
                        continue
                    es_last_id = max(es_last_id, msg.id)
                    text = (msg.text or "").strip()
                    if not text:
                        continue
                    ts = msg.date
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts_str = ts.isoformat()
                    log.info("ES msg #%d: %s", msg.id, text[:80])
                    if m := ES_ABSORPTION_RE.match(text):
                        monitor.add_level(float(m.group(1)), "ES", ts_str, msg.id)
                    else:
                        log.info("  (no regex match)")

        except Exception as e:
            log.warning("Poll error: %s", e)
            _update_tray("Reconnecting...", color="yellow")

        await asyncio.sleep(POLL_SECONDS)


async def main_loop():
    while True:
        try:
            _update_tray("Connecting...", color="yellow")
            await run_monitor()
        except KeyboardInterrupt:
            log.info("Stopped")
            break
        except Exception as e:
            _update_tray("Crashed", color="red")
            log.exception("Crash: %s — restart 10s", e)
            await asyncio.sleep(10)


def main():
    if not acquire_lock():
        sys.exit(1)
    log.info("=== MAD Levels Service PID %d ===", os.getpid())
    tray = threading.Thread(target=_start_tray, daemon=True)
    tray.start()
    try:
        asyncio.run(main_loop())
    finally:
        release_lock()
        if _tray_icon:
            _tray_icon.stop()


if __name__ == "__main__":
    main()
