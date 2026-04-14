"""Download NQ.c.0 MBO from Databento as a DBN.zst file (one per session).

Streams `timeseries.get_range` directly to disk so we pay once. Designed
for small 3-10 day backfills; for full-month batches use batch.submit_job.

Usage:
    export DATABENTO_API_KEY=db-...
    python scripts/databento/download_nq_mbo.py --start 2026-04-08 --end 2026-04-11

End is EXCLUSIVE per Databento convention.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import databento as db


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD (exclusive)")
    p.add_argument("--symbol", default="NQ.c.0")
    p.add_argument("--dataset", default="GLBX.MDP3")
    p.add_argument("--schema", default="mbo", choices=["mbo", "mbp-10", "trades"])
    p.add_argument("--dir", default="data/databento/nq_mbo", help="Output directory")
    args = p.parse_args()

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("ERROR: DATABENTO_API_KEY not set", file=sys.stderr)
        return 1

    out_dir = Path(args.dir) / "raw_dbn"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.symbol.replace('.', '_')}_{args.schema}_{args.start}_{args.end}.dbn.zst"

    client = db.Historical(key=key)

    # Cost confirmation — we already know from the earlier quote, but show it.
    cost = client.metadata.get_cost(
        dataset=args.dataset, symbols=[args.symbol], stype_in="continuous",
        schema=args.schema, start=args.start, end=args.end,
    )
    size = client.metadata.get_billable_size(
        dataset=args.dataset, symbols=[args.symbol], stype_in="continuous",
        schema=args.schema, start=args.start, end=args.end,
    )
    print(f"Quote: ${cost:.2f} / {size/1e9:.2f} GB billable for "
          f"{args.symbol} {args.schema} {args.start} -> {args.end}")

    if out_file.exists():
        print(f"OK existing file at {out_file} ({out_file.stat().st_size / 1e6:.1f} MB) — skipping download")
        return 0

    t0 = time.time()
    print(f"Downloading to {out_file} ...")
    store = client.timeseries.get_range(
        dataset=args.dataset,
        symbols=[args.symbol],
        stype_in="continuous",
        schema=args.schema,
        start=args.start,
        end=args.end,
        path=str(out_file),
    )
    elapsed = time.time() - t0
    disk_mb = out_file.stat().st_size / 1e6
    print(f"Done in {elapsed:.1f}s — {disk_mb:.1f} MB on disk (zstd compressed)")

    # Write manifest for reproducibility + checksum
    sha = hashlib.sha256()
    with out_file.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)

    manifest_path = Path(args.dir) / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    manifest[out_file.name] = {
        "symbol": args.symbol,
        "dataset": args.dataset,
        "schema": args.schema,
        "start": args.start,
        "end": args.end,
        "cost_usd": float(cost),
        "billable_bytes": int(size),
        "disk_bytes": out_file.stat().st_size,
        "sha256": sha.hexdigest(),
        "downloaded_at_unix": int(time.time()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest updated: {manifest_path}")

    # Quick sanity read
    rec_count = 0
    for _ in store:
        rec_count += 1
        if rec_count >= 5:
            break
    print(f"Sanity: first {rec_count} records readable from DBN")

    return 0


if __name__ == "__main__":
    sys.exit(main())
