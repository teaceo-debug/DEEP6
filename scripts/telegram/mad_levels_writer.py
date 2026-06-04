"""Write MAD Levels absorption data to NT8 templates directory for chart overlay.

Reads raw_nq.json and raw_es.json (Telegram MAD Levels channel exports),
extracts recent absorption levels, and writes a compact JSON file that the
DEEP6 MADAbsorptionLevels NinjaTrader indicator reads on every bar.

Usage:
    # One-shot: parse and write current levels
    python scripts/telegram/mad_levels_writer.py

    # Custom lookback (default 24h)
    python scripts/telegram/mad_levels_writer.py --hours 48

    # Continuous mode: re-write every N seconds (pair with download_history.py cron)
    python scripts/telegram/mad_levels_writer.py --watch 60

Output:
    %USERPROFILE%\\Documents\\NinjaTrader 8\\templates\\DEEP6\\mad_levels.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Paths ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
RAW_NQ_PATH = ROOT / "data" / "telegram_levels" / "raw_nq.json"
RAW_ES_PATH = ROOT / "data" / "telegram_levels" / "raw_es.json"

NT8_TEMPLATES = Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6"
OUTPUT_PATH = NT8_TEMPLATES / "mad_levels.json"

# ── Parsing ─────────────────────────────────────────────────────────────
NQ_ABSORPTION_RE = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
ES_ABSORPTION_RE = re.compile(r"^ES absorption at:\s*([\d.]+)$")

NQ_SESSION_HEADER = "NQ Asian and London sessions' intraday swing H/L:"
ES_SESSION_HEADER = "ES Asian and London sessions' intraday swing H/L:"

ET = ZoneInfo("America/New_York")
SESSION_OPEN = dtime(8, 30)
SESSION_CLOSE = dtime(16, 0)


def parse_raw_messages(path: Path, source: str) -> list[dict]:
    """Parse a raw Telegram JSON export into structured level records."""
    if not path.exists():
        return []

    messages = json.loads(path.read_text(encoding="utf-8"))
    absorption_re = NQ_ABSORPTION_RE if source == "NQ" else ES_ABSORPTION_RE
    session_header = NQ_SESSION_HEADER if source == "NQ" else ES_SESSION_HEADER

    records: list[dict] = []
    for msg in messages:
        text = (msg.get("text") or "").strip()
        if not text:
            continue

        ts = msg.get("date", "")

        # Absorption alerts
        if m := absorption_re.match(text):
            records.append({
                "price": float(m.group(1)),
                "source": source,
                "type": "absorption",
                "timestamp_utc": ts,
            })
            continue

        # Session swing levels
        if text.startswith(session_header):
            body = text[len(session_header):].replace("|", "\n")
            prices = re.findall(r"\d+(?:\.\d+)?", body)
            for p in prices:
                records.append({
                    "price": float(p),
                    "source": source,
                    "type": "session_level",
                    "timestamp_utc": ts,
                })

    return records


def session_window_for_date(date_et: datetime) -> tuple[datetime, datetime]:
    """Return 8:30a–4:00p ET window for a given date."""
    start_et = date_et.replace(hour=8, minute=30, second=0, microsecond=0)
    end_et = date_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def find_latest_session(records: list[dict]) -> tuple[datetime, datetime]:
    """Find the most recent trading session that has data.

    Checks today first, then walks back up to 7 days.
    """
    now_et = datetime.now(ET)
    for days_back in range(8):
        candidate = now_et - timedelta(days=days_back)
        start, end = session_window_for_date(candidate)
        for r in records:
            ts_str = r.get("timestamp_utc", "")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if start <= ts <= end:
                    return start, end
            except (ValueError, TypeError):
                continue
    return session_window_for_date(now_et)


def filter_session(records: list[dict]) -> tuple[list[dict], datetime, datetime]:
    """Keep only records from the most recent session with data (8:30a–4:00p ET)."""
    start, end = find_latest_session(records)
    result = []
    for r in records:
        ts_str = r.get("timestamp_utc", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if start <= ts <= end:
                result.append(r)
        except (ValueError, TypeError):
            continue
    return result, start, end


def deduplicate(records: list[dict], tick_size: float = 0.25, cluster_ticks: int = 4) -> list[dict]:
    """Merge levels within cluster_ticks of each other, keeping the most recent."""
    if not records:
        return []

    cluster_dist = tick_size * cluster_ticks
    # Sort by price
    sorted_recs = sorted(records, key=lambda r: r["price"])
    clusters: list[dict] = []

    for rec in sorted_recs:
        merged = False
        for cluster in clusters:
            if abs(rec["price"] - cluster["price"]) <= cluster_dist:
                # Keep the most recent timestamp
                if rec["timestamp_utc"] > cluster["timestamp_utc"]:
                    cluster["timestamp_utc"] = rec["timestamp_utc"]
                cluster["count"] = cluster.get("count", 1) + 1
                merged = True
                break
        if not merged:
            clusters.append({**rec, "count": 1})

    return clusters


def write_atomic(payload: dict, output_path: Path) -> None:
    """Atomic write: tempfile + os.replace to prevent partial reads by NT8."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2) + "\n"

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(output_path.parent),
        prefix=f".{output_path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(serialized)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)

    os.replace(tmp_path, output_path)


def build_payload() -> dict:
    """Parse, filter to most recent session, deduplicate, and package for NT8."""
    nq_records = parse_raw_messages(RAW_NQ_PATH, "NQ")
    es_records = parse_raw_messages(RAW_ES_PATH, "ES")

    all_records = nq_records + es_records
    session, start, end = filter_session(all_records)

    # Deduplicate NQ and ES separately (different price scales)
    nq_session = [r for r in session if r["source"] == "NQ"]
    es_session = [r for r in session if r["source"] == "ES"]

    nq_deduped = deduplicate(nq_session)
    es_deduped = deduplicate(es_session, tick_size=0.25, cluster_ticks=4)

    levels = nq_deduped + es_deduped

    return {
        "service": "mad_levels",
        "version": "2.1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "session_start_utc": start.isoformat(),
        "session_end_utc": end.isoformat(),
        "session_date_et": start.astimezone(ET).strftime("%Y-%m-%d"),
        "nq_count": len(nq_deduped),
        "es_count": len(es_deduped),
        "levels": levels,
    }


def run_once() -> None:
    """Single parse-and-write cycle (most recent session 8:30a–4:00p ET)."""

    payload = build_payload()
    write_atomic(payload, OUTPUT_PATH)

    nq_count = payload["nq_count"]
    es_count = payload["es_count"]
    print(f"[MAD Levels] Wrote {nq_count} NQ + {es_count} ES levels to {OUTPUT_PATH}")
    for lvl in payload["levels"]:
        tag = lvl["source"]
        print(f"  {tag}  {lvl['price']:.2f}  ({lvl['type']}, hits={lvl.get('count', 1)})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write MAD Levels to NT8 JSON bridge (today's session)")
    parser.add_argument("--watch", type=int, default=0, help="Re-write interval in seconds (0 = one-shot)")
    args = parser.parse_args()

    if args.watch > 0:
        print(f"[MAD Levels] Watch mode: re-writing every {args.watch}s (Ctrl+C to stop)")
        while True:
            try:
                run_once()
                time.sleep(args.watch)
            except KeyboardInterrupt:
                print("\n[MAD Levels] Stopped.")
                break
    else:
        run_once()


if __name__ == "__main__":
    main()
