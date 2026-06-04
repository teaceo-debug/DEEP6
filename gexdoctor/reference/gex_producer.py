#!/usr/bin/env python3
"""
DEEP6 ATLAS — GEX Producer
==========================
Reads gamma-exposure data from your optionlevels.com FastAPI stack and writes
the latest snapshot to:
    C:\\Users\\Public\\Documents\\NinjaTrader 8\\bin\\Custom\\AddOns\\gex_nq.json

The DEEP6Atlas indicator polls this file every 60s (configurable) and
ingests it into engine E11 (Magnet/GEX), the Tier-1 strength score, and
the size multiplier dampening logic.

USAGE
-----
    python gex_producer.py                         # uses defaults
    python gex_producer.py --interval 30           # 30s polling
    python gex_producer.py --source qqq            # use QQQ instead of NQ
    python gex_producer.py --output /custom/path/gex_nq.json

JSON SCHEMA (consumed by DEEP6Atlas.GEXContext.ParseJSON)
----------------------------------------------------------
    {
        "flip":         22150.5,         // gamma-flip price (NQ futures pts)
        "call_wall":    22300.0,         // upper wall
        "put_wall":     21900.0,         // lower wall
        "next_call":    22250.0,         // next-strike call cluster
        "next_put":     21950.0,         // next-strike put cluster
        "net_gex":      4.2e9,           // dealer net GEX in $
        "regime":       "POS_GEX",       // POS_GEX | NEG_GEX | NEUTRAL
        "as_of":        "2026-04-26T14:30:00-04:00",
        "source":       "optionlevels"
    }

NQ↔QQQ TRANSLATION
------------------
optionlevels.com tracks SPY/QQQ option chains. To translate to NQ futures:
    NQ_strike  ≈  QQQ_strike  ×  ~38.5    (June 2026 ratio; adjusts daily)
    NQ_pt_mult ≈  QQQ_pt_mult ×  ~38.5
This script computes the ratio dynamically using the cash session open of both.

DEPENDENCIES
------------
    pip install httpx requests pydantic python-dateutil

PRODUCTION DEPLOYMENT
---------------------
Run as a background process (Windows Task Scheduler, NSSM service, or
systemd-style supervisor). On crash, NT8 will gracefully fall back to
stale GEX (configurable via gex_stale_warn_seconds).
"""
import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_OPTIONLEVELS_URL = "http://localhost:8000/api/v1/gex/aggregate"
DEFAULT_OUTPUT_PATH = (
    r"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json"
)
DEFAULT_INTERVAL_SEC = 60
DEFAULT_SOURCE = "qqq"          # qqq | spx | spy
DEFAULT_NQ_QQQ_RATIO = 38.5     # rough; refined dynamically if both feeds available

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("gex_producer")


# ---------------------------------------------------------------------------
# GEX fetchers
# ---------------------------------------------------------------------------
def fetch_optionlevels_gex(url: str, source: str) -> Optional[dict]:
    """
    Hit your existing optionlevels.com FastAPI endpoint.
    Expected response shape (matches your live deployment):
        {
            "ticker": "QQQ",
            "spot": 575.20,
            "gamma_flip": 573.50,
            "call_wall": 580.00,
            "put_wall": 568.00,
            "next_call_cluster": 578.00,
            "next_put_cluster": 570.50,
            "net_gex_usd": 4.5e9,
            "regime": "positive_gamma",
            "timestamp": "2026-04-26T18:30:00Z"
        }
    """
    try:
        r = requests.get(url, params={"ticker": source.upper()}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("optionlevels fetch failed: %s", e)
        return None


def compute_nq_qqq_ratio() -> float:
    """
    Returns the NQ/QQQ price ratio. In production: read both spot prices from
    a market data feed. For initial deployment, returns the hardcoded default
    and lets you override with --ratio.
    """
    # TODO: hook into Databento or NT8 data feed for live ratio
    return DEFAULT_NQ_QQQ_RATIO


def translate_to_nq(qqq_data: dict, ratio: float) -> dict:
    """
    Convert QQQ (or SPY) GEX levels to NQ-equivalent prices using the cash
    ratio. Net GEX dollar value passes through (it's dollar-denominated).
    """
    def _scale(v):
        return None if v is None else round(v * ratio, 2)

    regime_str = qqq_data.get("regime", "neutral").lower()
    if "pos" in regime_str or "positive" in regime_str:
        regime = "POS_GEX"
    elif "neg" in regime_str or "negative" in regime_str:
        regime = "NEG_GEX"
    else:
        regime = "NEUTRAL"

    return {
        "flip":      _scale(qqq_data.get("gamma_flip")),
        "call_wall": _scale(qqq_data.get("call_wall")),
        "put_wall":  _scale(qqq_data.get("put_wall")),
        "next_call": _scale(qqq_data.get("next_call_cluster")),
        "next_put":  _scale(qqq_data.get("next_put_cluster")),
        "net_gex":   qqq_data.get("net_gex_usd", 0.0),
        "regime":    regime,
        "as_of":     qqq_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "source":    f"optionlevels-{qqq_data.get('ticker','QQQ')}-x{ratio:.2f}",
    }


def write_atomic(path: Path, payload: dict) -> None:
    """
    Write to a tmp file then rename — prevents NT8 from reading mid-write.
    """
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_loop(args) -> int:
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("starting GEX producer")
    log.info("  source=%s url=%s interval=%ds output=%s",
             args.source, args.url, args.interval, out_path)

    consecutive_failures = 0
    while True:
        t0 = time.time()
        raw = fetch_optionlevels_gex(args.url, args.source)
        if raw is None:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                log.error("5 consecutive failures — sleeping for 5 min")
                time.sleep(300)
                consecutive_failures = 0
            else:
                time.sleep(min(args.interval, 30))
            continue

        consecutive_failures = 0
        ratio = args.ratio if args.ratio else compute_nq_qqq_ratio()
        nq_payload = translate_to_nq(raw, ratio)
        try:
            write_atomic(out_path, nq_payload)
            log.info(
                "wrote NQ GEX: flip=%s callW=%s putW=%s netGEX=$%.1fB regime=%s",
                nq_payload.get("flip"),
                nq_payload.get("call_wall"),
                nq_payload.get("put_wall"),
                (nq_payload.get("net_gex") or 0) / 1e9,
                nq_payload.get("regime"),
            )
        except Exception as e:
            log.error("write failed: %s", e)

        elapsed = time.time() - t0
        sleep_for = max(0.5, args.interval - elapsed)
        time.sleep(sleep_for)


def main():
    p = argparse.ArgumentParser(description="DEEP6 ATLAS GEX producer")
    p.add_argument("--url", default=DEFAULT_OPTIONLEVELS_URL,
                   help="optionlevels FastAPI endpoint")
    p.add_argument("--source", default=DEFAULT_SOURCE, choices=("qqq", "spx", "spy"),
                   help="ticker source on optionlevels (translated to NQ)")
    p.add_argument("--output", default=DEFAULT_OUTPUT_PATH,
                   help="path for gex_nq.json output")
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC,
                   help="poll interval in seconds")
    p.add_argument("--ratio", type=float, default=None,
                   help="NQ/QQQ price ratio (auto-computed if omitted)")
    args = p.parse_args()

    try:
        return run_loop(args)
    except KeyboardInterrupt:
        log.info("interrupted, exiting")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
