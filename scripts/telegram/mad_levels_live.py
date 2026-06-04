"""Live MAD Levels monitor — real-time Telegram listener → NT8 JSON bridge.

Connects to Telegram, monitors NQ + ES MAD Levels channels, and instantly
writes mad_levels.json to the NT8 templates directory when a new absorption
level fires. The NT8 indicator polls this file every 5 seconds.

Usage:
    python scripts/telegram/mad_levels_live.py              # default 48h lookback
    python scripts/telegram/mad_levels_live.py --hours 24   # custom lookback

Runs forever. Ctrl+C to stop.

Prerequisites:
    - Telegram session must exist (run download_history.py once first)
    - .env with TELEGRAM_API_ID and TELEGRAM_API_HASH
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import ChatInviteAlready

# ── Config ──────────────────────────────────────────────────────────────
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

TICK_SIZE = 0.25
CLUSTER_TICKS = 4

ET = ZoneInfo("America/New_York")
SESSION_OPEN = dtime(8, 30)
SESSION_CLOSE = dtime(16, 0)

NQ_ABSORPTION_RE = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
ES_ABSORPTION_RE = re.compile(r"^ES absorption at:\s*([\d.]+)$")
NQ_SESSION_HEADER = "NQ Asian and London sessions' intraday swing H/L:"
ES_SESSION_HEADER = "ES Asian and London sessions' intraday swing H/L:"


# ── Monitor ─────────────────────────────────────────────────────────────

class MADLevelsMonitor:
    def __init__(self):
        self.levels: list[dict] = []
        self.nq_entity = None
        self.es_entity = None
        self.channel_ids: set[int] = set()

    @staticmethod
    def _session_window_for_date(date_et: datetime) -> tuple[datetime, datetime]:
        """Return 8:30a–4:00p ET window for a given ET date."""
        start_et = date_et.replace(hour=8, minute=30, second=0, microsecond=0)
        end_et = date_et.replace(hour=16, minute=0, second=0, microsecond=0)
        return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)

    def _find_session(self, all_timestamps: list[str]) -> tuple[datetime, datetime]:
        """Find the most recent trading session that has data.

        If today (8:30a–4:00p ET) has levels, use today.
        Otherwise walk back up to 7 days to find the last session with data.
        """
        now_et = datetime.now(ET)
        for days_back in range(8):
            candidate = now_et - timedelta(days=days_back)
            start, end = self._session_window_for_date(candidate)
            for ts_str in all_timestamps:
                ts = self._parse_ts(ts_str)
                if start <= ts <= end:
                    return start, end
        # Fallback: today's window (will produce 0 levels)
        return self._session_window_for_date(now_et)

    def _in_session(self, ts_str: str, start: datetime, end: datetime) -> bool:
        """Check if a timestamp falls within the given session window."""
        ts = self._parse_ts(ts_str)
        if ts == datetime.min.replace(tzinfo=timezone.utc):
            return False
        return start <= ts <= end

    def load_historical(self) -> None:
        """Seed levels from raw Telegram exports (most recent session with data)."""
        self.levels.clear()

        # Collect all timestamps to find the right session
        all_timestamps: list[str] = []
        raw_by_source: dict[str, list[dict]] = {}
        for path, source in [(RAW_NQ_PATH, "NQ"), (RAW_ES_PATH, "ES")]:
            if not path.exists():
                print(f"  {source}: {path.name} not found — skipping history")
                continue
            messages = json.loads(path.read_text(encoding="utf-8"))
            raw_by_source[source] = messages
            for msg in messages:
                ts_str = msg.get("date", "")
                if ts_str:
                    all_timestamps.append(ts_str)

        start, end = self._find_session(all_timestamps)
        self._session_start = start
        self._session_end = end
        session_et = start.astimezone(ET)
        print(f"  Session: {session_et.strftime('%b %d')} {session_et.strftime('%I:%M %p')}–{end.astimezone(ET).strftime('%I:%M %p')} ET")

        for source, messages in raw_by_source.items():
            absorption_re = NQ_ABSORPTION_RE if source == "NQ" else ES_ABSORPTION_RE
            count = 0
            for msg in messages:
                text = (msg.get("text") or "").strip()
                ts_str = msg.get("date", "")
                if not text or not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < start or ts > end:
                        continue
                except (ValueError, TypeError):
                    continue
                if m := absorption_re.match(text):
                    self.levels.append({
                        "price": float(m.group(1)),
                        "source": source,
                        "type": "absorption",
                        "timestamp_utc": ts_str,
                        "count": 1,
                    })
                    count += 1
            print(f"  {source}: {count} absorptions")

        self._deduplicate()
        self._write_json()

    def add_level(self, price: float, source: str, timestamp_utc: str) -> None:
        """Add a new absorption and immediately update the JSON bridge.

        On a new trading day, the session window auto-advances: if the incoming
        level belongs to today's session but the stored levels are from yesterday,
        the old levels are pruned and the window shifts to today.
        """
        # Check if this level starts a new session day
        now_et = datetime.now(ET)
        today_start, today_end = self._session_window_for_date(now_et)
        ts = self._parse_ts(timestamp_utc)

        if today_start <= ts <= today_end:
            # Level is in today's session — shift window if needed
            if not hasattr(self, '_session_start') or self._session_start != today_start:
                print(f"  New session day — clearing previous levels")
                self.levels.clear()
                self._session_start = today_start
                self._session_end = today_end
        else:
            # Outside any session window — skip
            now_str = datetime.now().strftime("%H:%M:%S")
            print(f"  [{now_str}] {source} {price:.2f} outside RTH — skipped")
            return

        self.levels.append({
            "price": price,
            "source": source,
            "type": "absorption",
            "timestamp_utc": timestamp_utc,
            "count": 1,
        })
        self._deduplicate()
        self._write_json()
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"  [{now_str}] NEW {source} absorption at {price:.2f} — JSON updated")

    def _deduplicate(self) -> None:
        cluster_dist = TICK_SIZE * CLUSTER_TICKS
        by_source: dict[str, list[dict]] = {}
        for lvl in self.levels:
            by_source.setdefault(lvl["source"], []).append(lvl)

        merged: list[dict] = []
        for source, group in by_source.items():
            group.sort(key=lambda r: r["price"])
            clusters: list[dict] = []
            for rec in group:
                found = False
                for c in clusters:
                    if abs(rec["price"] - c["price"]) <= cluster_dist:
                        if rec["timestamp_utc"] > c["timestamp_utc"]:
                            c["timestamp_utc"] = rec["timestamp_utc"]
                        c["count"] = c.get("count", 1) + 1
                        found = True
                        break
                if not found:
                    clusters.append({**rec})
            merged.extend(clusters)
        self.levels = merged

    def _write_json(self) -> None:
        nq = [l for l in self.levels if l["source"] == "NQ"]
        es = [l for l in self.levels if l["source"] == "ES"]
        start = getattr(self, '_session_start', datetime.now(timezone.utc))
        end = getattr(self, '_session_end', datetime.now(timezone.utc))
        payload = {
            "service": "mad_levels_live",
            "version": "2.1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "session_start_utc": start.isoformat(),
            "session_end_utc": end.isoformat(),
            "session_date_et": start.astimezone(ET).strftime("%Y-%m-%d"),
            "nq_count": len(nq),
            "es_count": len(es),
            "levels": self.levels,
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=str(OUTPUT_PATH.parent),
            prefix=f".{OUTPUT_PATH.stem}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(serialized)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, OUTPUT_PATH)

    @staticmethod
    def _parse_ts(ts_str: str) -> datetime:
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts
        except (ValueError, TypeError):
            return datetime.min.replace(tzinfo=timezone.utc)


# ── Telegram connection ─────────────────────────────────────────────────

async def resolve_channel(client: TelegramClient, invite_hash: str, label: str):
    """Resolve a private channel from its invite hash."""
    try:
        result = await client(CheckChatInviteRequest(invite_hash))
        if isinstance(result, ChatInviteAlready):
            entity = result.chat
            print(f"  {label}: {getattr(entity, 'title', 'OK')} (id={entity.id})")
            return entity
        else:
            from telethon.tl.functions.messages import ImportChatInviteRequest
            updates = await client(ImportChatInviteRequest(invite_hash))
            if updates.chats:
                entity = updates.chats[0]
                print(f"  {label}: joined {getattr(entity, 'title', 'OK')} (id={entity.id})")
                return entity
    except Exception as e:
        print(f"  {label}: ERROR — {e}")
    return None


async def main() -> None:
    print("MAD Levels Live Monitor")
    print("=" * 60)

    monitor = MADLevelsMonitor()

    # Load today's session levels from history
    print("\nLoading today's session levels...")
    monitor.load_historical()
    print(f"  Total: {len(monitor.levels)} levels written to JSON\n")

    # Connect
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("ERROR: Not authorized. Run download_history.py first to set up session.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Telegram: logged in as {me.first_name}\n")

    # Resolve channels
    print("Resolving channels...")
    monitor.nq_entity = await resolve_channel(client, NQ_CHANNEL_HASH, "NQ")
    monitor.es_entity = await resolve_channel(client, ES_CHANNEL_HASH, "ES")

    chats = []
    if monitor.nq_entity:
        chats.append(monitor.nq_entity)
        monitor.channel_ids.add(monitor.nq_entity.id)
    if monitor.es_entity:
        chats.append(monitor.es_entity)
        monitor.channel_ids.add(monitor.es_entity.id)

    if not chats:
        print("\nERROR: Could not resolve any channels. Exiting.")
        await client.disconnect()
        return

    # Register real-time event handler.
    # Use regex on message text to identify source (NQ/ES) instead of
    # comparing chat_id — Telegram channel IDs use -100 prefix in events
    # but entity.id doesn't, so direct comparison breaks.
    @client.on(events.NewMessage(chats=chats))
    async def on_new_message(event):
        text = (event.message.text or "").strip()
        if not text:
            return

        ts = event.message.date
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_str = ts.isoformat()
        now_str = datetime.now().strftime("%H:%M:%S")

        if m := NQ_ABSORPTION_RE.match(text):
            monitor.add_level(float(m.group(1)), "NQ", ts_str)
        elif m := ES_ABSORPTION_RE.match(text):
            monitor.add_level(float(m.group(1)), "ES", ts_str)
        else:
            # Log non-absorption messages so we know the handler fires
            preview = text[:60].replace("\n", " ")
            print(f"  [{now_str}] msg: {preview}...")

    print(f"\n{'=' * 60}")
    print("LIVE — monitoring NQ + ES channels for new absorptions")
    print(f"Output: {OUTPUT_PATH}")
    print("Ctrl+C to stop")
    print(f"{'=' * 60}\n")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\n[MAD Levels] Stopped.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
