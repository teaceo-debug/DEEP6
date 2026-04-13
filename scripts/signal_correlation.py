"""Signal correlation matrix analysis for DEEP6 signal engines.

Computes pairwise Pearson correlation across all implemented signal types
(ImbalanceType x11, DeltaType x13, AuctionType x6) to identify redundant
signal pairs before Phase 7 scorer finalization.

Addresses ARCH-04 success criterion 5: Document any signal pair with r > 0.7
to prevent double-counting correlated signals in the confluence score.

Usage (live Databento fetch):
    python scripts/signal_correlation.py --start 2026-04-09 --end 2026-04-10

Usage (from existing backtest CSV):
    python scripts/signal_correlation.py --from-csv backtest_apr10.csv

Output:
    correlation_matrix.csv   -- full NxN Pearson matrix with signal names
    stdout                   -- human-readable summary of high-correlation pairs
"""
import argparse
import csv
import os
import sys
from datetime import datetime

import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep6.engines.imbalance import ImbalanceType, detect_imbalances
from deep6.engines.delta import DeltaEngine, DeltaType
from deep6.engines.auction import AuctionEngine, AuctionType
from deep6.state.footprint import FootprintBar


# ── Signal column definitions ──────────────────────────────────────────────────

# All signal types tracked in the binary matrix
IMB_SIGNALS = [f"IMB_{t.name}" for t in ImbalanceType]   # 11 columns
DELTA_SIGNALS = [f"DELT_{t.name}" for t in DeltaType]    # 13 columns
AUCT_SIGNALS = [f"AUCT_{t.name}" for t in AuctionType]   # 6 columns

ALL_SIGNALS = IMB_SIGNALS + DELTA_SIGNALS + AUCT_SIGNALS  # 30 columns total


# ── Bar processing ─────────────────────────────────────────────────────────────

def build_bars(data, bar_seconds: int = 60) -> list[FootprintBar]:
    """Build FootprintBars from Databento trade records.

    Reuses identical logic from scripts/backtest_signals.py.
    """
    bars = []
    current_bar = FootprintBar()
    current_boundary = None

    for record in data:
        price = record.price / 1e9
        size = record.size
        side = chr(record.side)
        bar_epoch = int(record.ts_event / 1e9) // bar_seconds * bar_seconds

        if current_boundary is None:
            current_boundary = bar_epoch

        if bar_epoch > current_boundary:
            current_bar.finalize(prior_cvd=bars[-1].cvd if bars else 0)
            current_bar.timestamp = current_boundary
            bars.append(current_bar)
            current_bar = FootprintBar()
            current_boundary = bar_epoch

        current_bar.add_trade(price, size, 1 if side == "A" else 2)

    if current_bar.total_vol > 0:
        current_bar.finalize(prior_cvd=bars[-1].cvd if bars else 0)
        current_bar.timestamp = current_boundary or 0
        bars.append(current_bar)

    return bars


def extract_signal_row(
    bar: FootprintBar,
    prior_bar: FootprintBar | None,
    delta_eng: DeltaEngine,
    auction_eng: AuctionEngine,
) -> list[int]:
    """Produce a binary row: 1 if signal type fired on this bar, 0 otherwise.

    Returns a list of length len(ALL_SIGNALS) in the same order.
    """
    # Imbalance signals
    imb_sigs = detect_imbalances(bar, prior_bar=prior_bar)
    fired_imb = {s.imb_type for s in imb_sigs}

    # Delta signals
    delta_sigs = delta_eng.process(bar)
    fired_delta = {s.delta_type for s in delta_sigs}

    # Auction signals
    auction_sigs = auction_eng.process(bar)
    fired_auct = {s.auction_type for s in auction_sigs}

    row: list[int] = []
    for t in ImbalanceType:
        row.append(1 if t in fired_imb else 0)
    for t in DeltaType:
        row.append(1 if t in fired_delta else 0)
    for t in AuctionType:
        row.append(1 if t in fired_auct else 0)

    return row


# ── Data sources ───────────────────────────────────────────────────────────────

def load_from_databento(start: str, end: str, bar_seconds: int) -> tuple[list[list[int]], int, str, str]:
    """Fetch NQ trades from Databento and extract signal binary matrix."""
    import databento as db
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        print("ERROR: Set DATABENTO_API_KEY in .env or environment")
        sys.exit(1)

    print(f"Fetching NQ trades {start} to {end}...")
    client = db.Historical(key=api_key)
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="trades",
        stype_in="continuous",
        symbols=["NQ.c.0"],
        start=f"{start}T13:30:00",
        end=f"{end}T20:00:00",
    )

    print("Building footprint bars...")
    bars = build_bars(data, bar_seconds=bar_seconds)
    print(f"Built {len(bars)} bars")

    matrix = _extract_matrix(bars)
    return matrix, len(bars), start, end


def load_from_csv(csv_path: str) -> tuple[list[list[int]], int, str, str]:
    """Load an existing backtest CSV and re-run signal extraction.

    The backtest CSV does not store per-bar raw footprint data, only aggregated
    signal counts. Since we need per-bar binary vectors, we reconstruct from the
    available signal columns. For signals with only count columns, we binarize
    (1 if count > 0).

    Falls back to the binarized-column approach rather than requiring re-fetch.
    """
    if not os.path.exists(csv_path):
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    print(f"Loading from CSV: {csv_path}")
    rows_raw = []
    timestamps: list[str] = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            rows_raw.append(row)
            timestamps.append(row.get("timestamp", ""))

    n_bars = len(rows_raw)
    if n_bars == 0:
        print("ERROR: CSV is empty")
        sys.exit(1)

    print(f"Loaded {n_bars} bars from CSV")

    # Build signal matrix from available CSV columns (binarized)
    # Map from signal column name to CSV field
    csv_col_map = {
        # Imbalance (available in backtest CSV through narrative imbalances)
        "IMB_STACKED_T1": "imb_stacked",
        "IMB_STACKED_T2": "imb_stacked",
        "IMB_STACKED_T3": "imb_stacked",
        "IMB_INVERSE_TRAP": "imb_traps",
        # Delta (direct columns)
        "DELT_DIVERGENCE": "delta_divergence",
        "DELT_SLINGSHOT": "delta_slingshot",
        "DELT_CVD_DIVERGENCE": "delta_cvd_div",
        # Auction (direct columns)
        "AUCT_FINISHED_AUCTION": "auction_finished",
        "AUCT_UNFINISHED_BUSINESS": "auction_unfinished",
    }

    matrix: list[list[int]] = []
    for row in rows_raw:
        vec: list[int] = []
        for sig_name in ALL_SIGNALS:
            if sig_name in csv_col_map:
                csv_field = csv_col_map[sig_name]
                try:
                    val = int(float(row.get(csv_field, "0")))
                    vec.append(1 if val > 0 else 0)
                except (ValueError, TypeError):
                    vec.append(0)
            else:
                # Signal not directly available in CSV — mark as unknown (0)
                vec.append(0)
        matrix.append(vec)

    # Infer date range from timestamps
    valid_ts = [t for t in timestamps if t]
    date_start = valid_ts[0] if valid_ts else "?"
    date_end = valid_ts[-1] if valid_ts else "?"

    print(
        "Note: --from-csv mode uses binarized backtest columns only. "
        "Signals not in the CSV will show as all-zero and be flagged as rare."
    )
    return matrix, n_bars, date_start, date_end


def _extract_matrix(bars: list[FootprintBar]) -> list[list[int]]:
    """Run signal engines on all bars and return binary matrix."""
    delta_eng = DeltaEngine()
    auction_eng = AuctionEngine()

    matrix: list[list[int]] = []
    for i, bar in enumerate(bars):
        prior_bar = bars[i - 1] if i > 0 else None
        row = extract_signal_row(bar, prior_bar, delta_eng, auction_eng)
        matrix.append(row)

    return matrix


# ── Analysis ───────────────────────────────────────────────────────────────────

def compute_correlation(matrix: list[list[int]]) -> np.ndarray:
    """Compute Pearson correlation matrix using numpy.corrcoef.

    Returns an NxN array where N = len(ALL_SIGNALS).
    """
    arr = np.array(matrix, dtype=np.float64)  # shape: (bars, signals)

    # corrcoef expects rows = variables, cols = observations
    # Transpose so each row is a signal vector across bars
    arr_t = arr.T  # shape: (signals, bars)

    # Check for zero-variance columns (signals that never fired or always fired)
    stdev = arr_t.std(axis=1)
    zero_var = np.where(stdev == 0)[0]
    if len(zero_var) > 0:
        zero_names = [ALL_SIGNALS[i] for i in zero_var]
        print(f"  Zero-variance signals (excluded from corrcoef): {zero_names}")
        # Replace with small noise to avoid NaN in corrcoef output
        arr_t = arr_t.copy().astype(np.float64)
        arr_t[zero_var, :] = np.nan  # will produce NaN correlations (correct)

    corr = np.corrcoef(arr_t)
    return corr


def write_csv(corr: np.ndarray, output_path: str) -> None:
    """Write correlation matrix to CSV with signal names as header and index."""
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        # Header row
        writer.writerow(["signal"] + ALL_SIGNALS)
        for i, sig_name in enumerate(ALL_SIGNALS):
            row = [sig_name]
            for j in range(len(ALL_SIGNALS)):
                val = corr[i, j]
                row.append(f"{val:.4f}" if not np.isnan(val) else "NaN")
            writer.writerow(row)
    print(f"Wrote correlation matrix to {output_path}")


def print_summary(
    corr: np.ndarray,
    matrix: list[list[int]],
    n_bars: int,
    date_start: str,
    date_end: str,
) -> None:
    """Print human-readable correlation summary to stdout."""
    arr = np.array(matrix, dtype=np.float64)
    fire_rates = arr.mean(axis=0)  # fraction of bars each signal fired

    print()
    print("=" * 70)
    print(f"SIGNAL CORRELATION ANALYSIS — {n_bars} bars, {date_start} to {date_end}")
    print(f"Signals tracked: {len(ALL_SIGNALS)} total "
          f"({len(IMB_SIGNALS)} imbalance, {len(DELTA_SIGNALS)} delta, {len(AUCT_SIGNALS)} auction)")
    print("=" * 70)

    # ── High-correlation pairs (|r| > 0.7) ─────────────────────────────────
    high_pairs: list[tuple[float, str, str, float, float]] = []
    med_pairs: list[tuple[float, str, str, float, float]] = []
    n = len(ALL_SIGNALS)

    for i in range(n):
        for j in range(i + 1, n):
            r = corr[i, j]
            if np.isnan(r):
                continue
            abs_r = abs(r)
            entry = (abs_r, ALL_SIGNALS[i], ALL_SIGNALS[j], fire_rates[i], fire_rates[j])
            if abs_r > 0.7:
                high_pairs.append(entry)
            elif abs_r > 0.5:
                med_pairs.append(entry)

    high_pairs.sort(reverse=True)
    med_pairs.sort(reverse=True)

    if high_pairs:
        print(f"\nHIGHLY CORRELATED PAIRS (|r| > 0.70) — {len(high_pairs)} pairs")
        print(f"  {'Signal A':<30} {'Signal B':<30} {'r':>8} {'Fire% A':>8} {'Fire% B':>8}")
        print(f"  {'-'*30} {'-'*30} {'-'*8} {'-'*8} {'-'*8}")
        for abs_r, a, b, ra, rb in high_pairs:
            r_signed = corr[ALL_SIGNALS.index(a), ALL_SIGNALS.index(b)]
            print(f"  {a:<30} {b:<30} {r_signed:>+8.4f} {ra*100:>7.1f}% {rb*100:>7.1f}%")
    else:
        print("\nHIGHLY CORRELATED PAIRS (|r| > 0.70): None found")

    if med_pairs:
        print(f"\nMODERATE CORRELATION PAIRS (|r| > 0.50) — {len(med_pairs)} pairs")
        print(f"  {'Signal A':<30} {'Signal B':<30} {'r':>8} {'Fire% A':>8} {'Fire% B':>8}")
        print(f"  {'-'*30} {'-'*30} {'-'*8} {'-'*8} {'-'*8}")
        for abs_r, a, b, ra, rb in med_pairs[:20]:  # cap at 20 rows
            r_signed = corr[ALL_SIGNALS.index(a), ALL_SIGNALS.index(b)]
            print(f"  {a:<30} {b:<30} {r_signed:>+8.4f} {ra*100:>7.1f}% {rb*100:>7.1f}%")
        if len(med_pairs) > 20:
            print(f"  ... and {len(med_pairs)-20} more (see CSV)")
    else:
        print("\nMODERATE CORRELATION PAIRS (|r| > 0.50): None found")

    # ── Rare signals (fire rate < 1%) ───────────────────────────────────────
    rare = [(ALL_SIGNALS[i], fire_rates[i]) for i in range(n) if fire_rates[i] < 0.01]
    if rare:
        print(f"\nRARE SIGNALS (fire rate < 1%) — {len(rare)} signals")
        print("  Correlations for these signals are unreliable (too few samples):")
        for name, rate in sorted(rare, key=lambda x: x[1]):
            count = int(rate * n_bars)
            print(f"    {name:<35} {rate*100:5.2f}%  ({count} bars)")
    else:
        print("\nRARE SIGNALS (fire rate < 1%): None — all signals fire adequately")

    # ── Fire rate summary ───────────────────────────────────────────────────
    print(f"\nSIGNAL FIRE RATES (all {len(ALL_SIGNALS)} signals):")
    print(f"  {'Signal':<35} {'Fire%':>7} {'Count':>7}")
    print(f"  {'-'*35} {'-'*7} {'-'*7}")
    for i, sig_name in enumerate(ALL_SIGNALS):
        rate = fire_rates[i]
        count = int(rate * n_bars)
        print(f"  {sig_name:<35} {rate*100:6.1f}% {count:>7}")

    print("=" * 70)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DEEP6 Signal Correlation Matrix — pairwise Pearson analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch live data from Databento (requires DATABENTO_API_KEY):
  python scripts/signal_correlation.py --start 2026-04-09 --end 2026-04-10

  # Re-analyze from existing backtest CSV (no API cost):
  python scripts/signal_correlation.py --from-csv backtest_apr10.csv

  # Custom output path and bar size:
  python scripts/signal_correlation.py --start 2026-04-09 --end 2026-04-10 \\
      --output results/corr.csv --bar-seconds 300
        """,
    )
    # Data source (mutually exclusive)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-csv", metavar="PATH",
                        help="Load existing backtest CSV instead of fetching from Databento")
    source.add_argument("--start", metavar="YYYY-MM-DD",
                        help="Start date for Databento fetch")

    parser.add_argument("--end", metavar="YYYY-MM-DD",
                        help="End date for Databento fetch (required with --start)")
    parser.add_argument("--output", default="correlation_matrix.csv",
                        help="Output CSV path (default: correlation_matrix.csv)")
    parser.add_argument("--bar-seconds", type=int, default=60,
                        help="Bar duration in seconds (default: 60)")

    args = parser.parse_args()

    # Validate args
    if args.from_csv is None and args.start is None:
        parser.error("Provide either --from-csv PATH or --start YYYY-MM-DD --end YYYY-MM-DD")
    if args.start and not args.end:
        parser.error("--end is required when --start is provided")

    # Load data
    if args.from_csv:
        matrix, n_bars, date_start, date_end = load_from_csv(args.from_csv)
    else:
        matrix, n_bars, date_start, date_end = load_from_databento(
            args.start, args.end, args.bar_seconds
        )

    if n_bars < 30:
        print(f"WARNING: Only {n_bars} bars — correlation estimates will be unreliable (need 30+)")

    print(f"Computing Pearson correlation matrix ({len(ALL_SIGNALS)} signals x {n_bars} bars)...")
    corr = compute_correlation(matrix)

    write_csv(corr, args.output)
    print_summary(corr, matrix, n_bars, str(date_start), str(date_end))


if __name__ == "__main__":
    main()
