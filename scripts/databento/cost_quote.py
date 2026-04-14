"""Free Databento cost-quote preview for 3-month NQ.c.0 MBO.

Runs metadata.get_cost() — no charge, no download. Use output to
decide whether to commit to download_nq_mbo.py.

Usage:
    export DATABENTO_API_KEY=db-...
    python scripts/databento/cost_quote.py
"""
import os
import sys
from datetime import date, timedelta

import databento as db


def main() -> int:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("ERROR: DATABENTO_API_KEY not set", file=sys.stderr)
        return 1

    end = date.today()
    start = end - timedelta(days=90)

    client = db.Historical(key=key)

    for schema in ("mbo", "mbp-10", "trades"):
        try:
            cost = client.metadata.get_cost(
                dataset="GLBX.MDP3",
                symbols=["NQ.c.0"],
                stype_in="continuous",
                schema=schema,
                start=start.isoformat(),
                end=end.isoformat(),
            )
            size = client.metadata.get_billable_size(
                dataset="GLBX.MDP3",
                symbols=["NQ.c.0"],
                stype_in="continuous",
                schema=schema,
                start=start.isoformat(),
                end=end.isoformat(),
            )
            print(f"{schema:8s}  ${cost:>10.2f}  {size / 1e9:>8.2f} GB billable")
        except Exception as exc:
            print(f"{schema:8s}  ERROR: {exc}")

    print(f"\nRange: {start} -> {end} (NQ.c.0 continuous, dataset=GLBX.MDP3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
