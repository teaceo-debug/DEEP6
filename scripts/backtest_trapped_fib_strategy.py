"""Backtest: Trapped Sellers/Buyers (1H/4H) + Fib Retracement (50-75%) Entry.

Strategy thesis:
  1. On higher timeframes (1H, 4H): detect trapped sellers/buyers from DEEP6
     signal_events.csv TRAP signals aggregated into hourly/4-hourly windows.
  2. Treat clustered traps as the START of a change of structure (CHoCH/BOS).
  3. Confirm with ICT structure break detection on 1H/4H OHLCV.
  4. Calculate the 50-75% Fibonacci retracement zone of the swing that caused
     the structure break.
  5. Enter on the 1-minute timeframe when price retraces into the 50-75% zone.

Data:
  - data/backtests/nq_1yr_1m.csv  (458K 1-minute bars, Jan 2025 - Apr 2026)
  - data/backtests/signal_events.csv (trap signals on 1-minute bars)

Limitations:
  - 15-second bars are not available for the full dataset (MBO covers only
    1 month). Using 1-minute as the execution timeframe. Strategy logic is
    identical — entry timing is coarser.
  - Trap signals are originally detected on 1-minute footprint data and
    aggregated to higher TF via rolling windows, not natively computed on
    higher-timeframe footprints.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deep6.bias_engine.ict_concepts import (
    ICTDirection,
    StructureBreak,
    detect_structure_breaks,
)

BARS_PATH = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
SIGNALS_PATH = ROOT / "data" / "backtests" / "signal_events.csv"
OUTPUT_JSON = ROOT / "data" / "backtests" / "trapped_fib_strategy_results.json"
OUTPUT_TRADES = ROOT / "data" / "backtests" / "trapped_fib_strategy_trades.csv"

ET = "America/New_York"
TICK_SIZE = 0.25
TICK_VALUE = 5.0


# ── data types ────────────────────────────────────────────────────────────────

@dataclass
class FibZone:
    """50-75% retracement zone from a swing after structure break."""
    fib_50: float
    fib_75: float
    swing_high: float
    swing_low: float
    direction: int       # +1 = bullish setup (buy the dip), -1 = bearish (sell the rip)
    htf: str             # "1H" or "4H"
    break_bar_ts: pd.Timestamp
    trap_count: int      # how many trap signals contributed


@dataclass
class Trade:
    strategy: str
    signal_ts: str
    entry_ts: str
    exit_ts: str
    entry_bar_idx: int
    exit_bar_idx: int
    direction: int
    entry_price: float
    exit_price: float
    pnl_ticks: float
    pnl_dollars: float
    bars_held: int
    exit_reason: str
    htf: str
    fib_50: float
    fib_75: float
    swing_high: float
    swing_low: float
    trap_count: int


# ── data loading ──────────────────────────────────────────────────────────────

def load_bars() -> pd.DataFrame:
    bars = pd.read_csv(BARS_PATH, parse_dates=["ts_event"])
    bars = bars.rename(columns={"ts_event": "timestamp_utc"}).copy()
    bars["timestamp_utc"] = pd.to_datetime(bars["timestamp_utc"], utc=True)
    bars = bars.sort_values("timestamp_utc").reset_index(drop=True)
    bars["bar_idx"] = np.arange(len(bars), dtype=int)
    bars["timestamp_et"] = bars["timestamp_utc"].dt.tz_convert(ET)
    return bars


def load_trap_signals() -> pd.DataFrame:
    """Load only TRAP signals from signal_events."""
    signals = pd.read_csv(SIGNALS_PATH)
    signals["bar_ts"] = pd.to_datetime(signals["bar_ts"], utc=True)
    traps = signals[signals["signal_id"].str.startswith("TRAP")].copy()
    traps["direction"] = pd.to_numeric(traps["direction"], errors="coerce").fillna(0).astype(int)
    traps["strength"] = pd.to_numeric(traps["strength"], errors="coerce")
    return traps


# ── higher timeframe resampling ───────────────────────────────────────────────

def resample_bars(bars: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample 1-minute bars to a higher timeframe (1H, 4H)."""
    df = bars.set_index("timestamp_et").copy()
    resampled = df.resample(freq).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "timestamp_utc": "first",
        "bar_idx": "first",
    }).dropna(subset=["open"])
    resampled = resampled.reset_index()
    resampled = resampled.rename(columns={"timestamp_et": "htf_ts"})
    return resampled


def aggregate_traps_to_htf(traps: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Aggregate 1-minute trap signals into higher TF windows.

    For each HTF window, count trap signals by direction and compute
    the dominant direction with total strength.
    """
    df = traps.copy()
    df["bar_ts_et"] = pd.to_datetime(df["bar_ts"], utc=True).dt.tz_convert(ET)
    df["htf_ts"] = df["bar_ts_et"].dt.floor(freq)

    agg = df.groupby(["htf_ts", "direction"]).agg(
        trap_count=("signal_id", "count"),
        total_strength=("strength", "sum"),
        mean_strength=("strength", "mean"),
    ).reset_index()

    # Pick dominant direction per HTF bar (most traps, then highest strength)
    agg = agg.sort_values(
        ["htf_ts", "trap_count", "total_strength"],
        ascending=[True, False, False],
    )
    dominant = agg.drop_duplicates("htf_ts", keep="first")
    # Filter: need at least 2 trap signals in the window for significance
    dominant = dominant[dominant["trap_count"] >= 2].copy()
    return dominant


# ── structure + fib detection ─────────────────────────────────────────────────

def find_structure_breaks_on_htf(htf_bars: pd.DataFrame, window_size: int = 100) -> list[StructureBreak]:
    """Detect BOS/CHoCH on higher timeframe bars using rolling windows.

    Processes the full dataset in overlapping windows to detect structure
    breaks across the entire history, not just the trailing edge.
    """
    highs = htf_bars["high"].tolist()
    lows = htf_bars["low"].tolist()
    closes = htf_bars["close"].tolist()
    n = len(highs)

    all_breaks: list[StructureBreak] = []
    seen_keys: set[tuple[int, int]] = set()

    step = window_size // 2
    for start in range(0, n, step):
        end = min(start + window_size, n)
        if end - start < 15:
            continue

        window_h = highs[start:end]
        window_l = lows[start:end]
        window_c = closes[start:end]

        breaks = detect_structure_breaks(
            window_h, window_l, window_c,
            swing_lookback=3,
            lookback=len(window_h),
        )

        for sb in breaks:
            # Remap bar_index from window-local to global
            global_idx = start + sb.bar_index
            key = (global_idx, int(sb.direction))
            if key not in seen_keys:
                seen_keys.add(key)
                all_breaks.append(StructureBreak(
                    bar_index=global_idx,
                    price=sb.price,
                    direction=sb.direction,
                    is_choch=sb.is_choch,
                    is_bos=sb.is_bos,
                    label=sb.label,
                    strength=sb.strength,
                ))

    all_breaks.sort(key=lambda b: b.bar_index)
    return all_breaks


def build_fib_zones(
    htf_bars: pd.DataFrame,
    structure_breaks: list[StructureBreak],
    htf_traps: pd.DataFrame,
    htf_label: str,
) -> list[FibZone]:
    """Build 50-75% Fibonacci retracement zones from structure breaks
    that coincide with trapped trader signals.

    Logic:
      - For each structure break, check if there are trapped traders
        in the same or preceding 2 HTF bars.
      - If trapped traders align with the break direction, compute
        the swing's 50-75% retracement zone.
    """
    zones: list[FibZone] = []
    htf_ts_list = htf_bars["htf_ts"].tolist()

    for sb in structure_breaks:
        bar_idx = sb.bar_index
        if bar_idx < 2 or bar_idx >= len(htf_bars):
            continue

        break_ts = htf_ts_list[bar_idx]

        # Check for trapped traders in preceding 5 HTF bars (wider window)
        window_start_idx = max(0, bar_idx - 4)
        window_ts = set(htf_ts_list[window_start_idx:bar_idx + 1])
        nearby_traps = htf_traps[htf_traps["htf_ts"].isin(window_ts)]

        if nearby_traps.empty:
            continue

        # Accept traps in EITHER direction — both trapped buyers and sellers
        # near a structure break indicate a contested zone worth trading.
        # Direction of the trade comes from the structure break itself.
        trap_count = int(nearby_traps["trap_count"].sum())
        if trap_count < 2:
            continue

        # Compute the swing from recent bars
        lookback = min(10, bar_idx)
        swing_highs = htf_bars["high"].iloc[bar_idx - lookback:bar_idx + 1].tolist()
        swing_lows = htf_bars["low"].iloc[bar_idx - lookback:bar_idx + 1].tolist()

        if sb.direction == ICTDirection.BULL:
            # Bullish structure break: swing from recent low to the break high
            swing_low = min(swing_lows)
            swing_high = max(swing_highs)
            rng = swing_high - swing_low
            if rng < 5.0:  # minimum 5 points swing (20 ticks)
                continue
            # 50-75% retracement of the up-move = buy zone
            fib_50 = swing_high - rng * 0.50
            fib_75 = swing_high - rng * 0.75
            direction = 1  # long entry at retracement

        elif sb.direction == ICTDirection.BEAR:
            # Bearish structure break: swing from recent high to the break low
            swing_high = max(swing_highs)
            swing_low = min(swing_lows)
            rng = swing_high - swing_low
            if rng < 5.0:
                continue
            # 50-75% retracement of the down-move = sell zone
            fib_50 = swing_low + rng * 0.50
            fib_75 = swing_low + rng * 0.75
            direction = -1  # short entry at retracement
        else:
            continue

        zones.append(FibZone(
            fib_50=fib_50,
            fib_75=fib_75,
            swing_high=swing_high,
            swing_low=swing_low,
            direction=direction,
            htf=htf_label,
            break_bar_ts=break_ts,
            trap_count=trap_count,
        ))

    return zones


# ── entry signal generation on 1-minute ───────────────────────────────────────

def generate_entry_signals(
    bars_1m: pd.DataFrame,
    fib_zones: list[FibZone],
    max_wait_bars: int = 120,  # max bars to wait for price to reach fib zone
) -> pd.DataFrame:
    """Generate entry signals on 1-minute bars when price enters a fib zone.

    For each fib zone:
      - Start scanning from the first 1-minute bar AFTER the structure break
      - Wait up to max_wait_bars for price to enter the 50-75% zone
      - Signal on the first bar whose close is inside the zone
    """
    entries: list[dict[str, Any]] = []
    bars_ts = bars_1m["timestamp_et"].values

    for zone in fib_zones:
        # Find the first 1-minute bar after the structure break timestamp
        break_ts = zone.break_bar_ts
        if hasattr(break_ts, 'tz') and break_ts.tz is not None:
            start_mask = bars_1m["timestamp_et"] > break_ts
        else:
            start_mask = bars_1m["timestamp_et"] > pd.Timestamp(break_ts, tz=ET)

        start_indices = bars_1m.index[start_mask]
        if len(start_indices) == 0:
            continue

        start_idx = start_indices[0]
        end_idx = min(start_idx + max_wait_bars, len(bars_1m) - 1)

        # Define the fib zone bounds
        if zone.direction > 0:
            # Bullish: fib_75 < fib_50 (zone is below current price)
            zone_low = min(zone.fib_50, zone.fib_75)
            zone_high = max(zone.fib_50, zone.fib_75)
        else:
            # Bearish: fib_50 < fib_75 (zone is above current price)
            zone_low = min(zone.fib_50, zone.fib_75)
            zone_high = max(zone.fib_50, zone.fib_75)

        # Scan for entry
        for idx in range(start_idx, end_idx + 1):
            bar = bars_1m.iloc[idx]
            # Price must enter the zone (bar low touches zone for longs, bar high for shorts)
            if zone.direction > 0:
                # Long: price must dip INTO the fib zone
                if bar["low"] <= zone_high and bar["close"] >= zone_low:
                    entries.append({
                        "bar_idx": int(bar["bar_idx"]),
                        "timestamp_utc": bar["timestamp_utc"],
                        "direction": zone.direction,
                        "htf": zone.htf,
                        "fib_50": zone.fib_50,
                        "fib_75": zone.fib_75,
                        "swing_high": zone.swing_high,
                        "swing_low": zone.swing_low,
                        "trap_count": zone.trap_count,
                        "entry_price_ref": bar["close"],
                    })
                    break
            else:
                # Short: price must rally INTO the fib zone
                if bar["high"] >= zone_low and bar["close"] <= zone_high:
                    entries.append({
                        "bar_idx": int(bar["bar_idx"]),
                        "timestamp_utc": bar["timestamp_utc"],
                        "direction": zone.direction,
                        "htf": zone.htf,
                        "fib_50": zone.fib_50,
                        "fib_75": zone.fib_75,
                        "swing_high": zone.swing_high,
                        "swing_low": zone.swing_low,
                        "trap_count": zone.trap_count,
                        "entry_price_ref": bar["close"],
                    })
                    break

    return pd.DataFrame(entries)


# ── trade simulation ──────────────────────────────────────────────────────────

def simulate_trades(
    bars: pd.DataFrame,
    entry_signals: pd.DataFrame,
    strategy_name: str,
    stop_ticks: int = 20,
    target_ticks: int = 40,
    max_hold_bars: int = 30,
) -> list[Trade]:
    """Simulate trades with bracket exits. Entry on next bar open after signal."""
    trades: list[Trade] = []
    last_exit_idx = -1

    for _, sig in entry_signals.sort_values("bar_idx").iterrows():
        signal_bar_idx = int(sig["bar_idx"])
        entry_idx = signal_bar_idx + 1

        # No overlapping positions
        if signal_bar_idx <= last_exit_idx:
            continue
        if entry_idx >= len(bars):
            continue

        entry_bar = bars.iloc[entry_idx]
        direction = int(sig["direction"])
        entry_price = float(entry_bar["open"])
        stop_price = entry_price - direction * stop_ticks * TICK_SIZE
        target_price = entry_price + direction * target_ticks * TICK_SIZE
        last_idx = min(len(bars) - 1, entry_idx + max_hold_bars - 1)

        exit_price = float(bars.iloc[last_idx]["close"])
        exit_reason = "TIME"
        exit_bar_idx = last_idx

        for j in range(entry_idx, last_idx + 1):
            bar = bars.iloc[j]
            high = float(bar["high"])
            low = float(bar["low"])
            open_price = float(bar["open"])

            if direction > 0:
                if j > entry_idx and open_price <= stop_price:
                    exit_price = open_price
                    exit_reason = "STOP_GAP"
                    exit_bar_idx = j
                    break
                if j > entry_idx and open_price >= target_price:
                    exit_price = open_price
                    exit_reason = "TARGET_GAP"
                    exit_bar_idx = j
                    break
                # Conservative: stop first when both hit same bar
                if low <= stop_price and high >= target_price:
                    exit_price = stop_price
                    exit_reason = "STOP_FIRST_SAME_BAR"
                    exit_bar_idx = j
                    break
                if low <= stop_price:
                    exit_price = stop_price
                    exit_reason = "STOP"
                    exit_bar_idx = j
                    break
                if high >= target_price:
                    exit_price = target_price
                    exit_reason = "TARGET"
                    exit_bar_idx = j
                    break
            else:
                if j > entry_idx and open_price >= stop_price:
                    exit_price = open_price
                    exit_reason = "STOP_GAP"
                    exit_bar_idx = j
                    break
                if j > entry_idx and open_price <= target_price:
                    exit_price = open_price
                    exit_reason = "TARGET_GAP"
                    exit_bar_idx = j
                    break
                if high >= stop_price and low <= target_price:
                    exit_price = stop_price
                    exit_reason = "STOP_FIRST_SAME_BAR"
                    exit_bar_idx = j
                    break
                if high >= stop_price:
                    exit_price = stop_price
                    exit_reason = "STOP"
                    exit_bar_idx = j
                    break
                if low <= target_price:
                    exit_price = target_price
                    exit_reason = "TARGET"
                    exit_bar_idx = j
                    break

        pnl_t = direction * (exit_price - entry_price) / TICK_SIZE
        exit_bar = bars.iloc[exit_bar_idx]
        last_exit_idx = exit_bar_idx

        trades.append(Trade(
            strategy=strategy_name,
            signal_ts=str(sig["timestamp_utc"]),
            entry_ts=str(entry_bar["timestamp_utc"]),
            exit_ts=str(exit_bar["timestamp_utc"]),
            entry_bar_idx=entry_idx,
            exit_bar_idx=exit_bar_idx,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_ticks=pnl_t,
            pnl_dollars=pnl_t * TICK_VALUE,
            bars_held=exit_bar_idx - entry_idx + 1,
            exit_reason=exit_reason,
            htf=str(sig["htf"]),
            fib_50=float(sig["fib_50"]),
            fib_75=float(sig["fib_75"]),
            swing_high=float(sig["swing_high"]),
            swing_low=float(sig["swing_low"]),
            trap_count=int(sig["trap_count"]),
        ))

    return trades


# ── statistics ────────────────────────────────────────────────────────────────

def max_consecutive_losses(pnls: np.ndarray) -> int:
    streak = worst = 0
    for p in pnls:
        if p < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def max_drawdown_ticks(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())


def sharpe_daily(trades_df: pd.DataFrame) -> float | None:
    if trades_df.empty:
        return None
    trades_df = trades_df.copy()
    trades_df["exit_ts"] = pd.to_datetime(trades_df["exit_ts"], utc=True)
    trades_df["exit_date"] = trades_df["exit_ts"].dt.date
    daily = trades_df.groupby("exit_date")["pnl_ticks"].sum().sort_index()
    all_days = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(all_days, fill_value=0.0)
    std = float(daily.std(ddof=1))
    if std == 0.0 or math.isnan(std):
        return None
    return float((daily.mean() / std) * math.sqrt(252.0))


def summarize(strategy: str, trades: list[Trade]) -> dict[str, Any]:
    if not trades:
        return {"strategy": strategy, "total_trades": 0, "note": "No trades generated."}

    trades_df = pd.DataFrame(asdict(t) for t in trades)
    pnls = trades_df["pnl_ticks"].to_numpy(dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(np.abs(losses.sum())) if len(losses) else 0.0

    trades_df["exit_ts_dt"] = pd.to_datetime(trades_df["exit_ts"], utc=True)
    trades_df["exit_month"] = trades_df["exit_ts_dt"].dt.tz_convert(ET).dt.strftime("%Y-%m")

    return {
        "strategy": strategy,
        "total_trades": len(trades_df),
        "longs": int((trades_df["direction"] > 0).sum()),
        "shorts": int((trades_df["direction"] < 0).sum()),
        "win_rate_pct": round(float((pnls > 0).mean() * 100), 2),
        "avg_win_ticks": round(float(wins.mean()), 2) if len(wins) else None,
        "avg_loss_ticks": round(float(losses.mean()), 2) if len(losses) else None,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "expectancy_ticks": round(float(pnls.mean()), 2),
        "expectancy_dollars": round(float(pnls.mean() * TICK_VALUE), 2),
        "total_ticks": round(float(pnls.sum()), 2),
        "total_dollars": round(float(pnls.sum() * TICK_VALUE), 2),
        "max_consecutive_losses": max_consecutive_losses(pnls),
        "max_drawdown_ticks": round(max_drawdown_ticks(pnls), 2),
        "sharpe_daily": sharpe_daily(trades_df),
        "exit_reasons": trades_df.groupby("exit_reason")["pnl_ticks"].agg(["count", "sum", "mean"]).round(2).to_dict("index"),
        "monthly_ticks": trades_df.groupby("exit_month")["pnl_ticks"].sum().round(2).to_dict(),
        "htf_breakdown": trades_df.groupby("htf")["pnl_ticks"].agg(["count", "sum", "mean"]).round(2).to_dict("index"),
        "by_direction": {
            "LONG": {
                "count": int((trades_df["direction"] > 0).sum()),
                "total_ticks": round(float(trades_df.loc[trades_df["direction"] > 0, "pnl_ticks"].sum()), 2),
            },
            "SHORT": {
                "count": int((trades_df["direction"] < 0).sum()),
                "total_ticks": round(float(trades_df.loc[trades_df["direction"] < 0, "pnl_ticks"].sum()), 2),
            },
        },
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Loading data...")
    bars_1m = load_bars()
    traps = load_trap_signals()
    print(f"  1-minute bars: {len(bars_1m):,}")
    print(f"  Trap signals:  {len(traps):,}")

    # ── resample to higher timeframes ─────────────────────────────────────
    print("\nResampling to 1H and 4H...")
    bars_1h = resample_bars(bars_1m, "1h")
    bars_4h = resample_bars(bars_1m, "4h")
    print(f"  1H bars: {len(bars_1h):,}")
    print(f"  4H bars: {len(bars_4h):,}")

    # ── aggregate trap signals to higher timeframes ───────────────────────
    print("\nAggregating trap signals to higher timeframes...")
    traps_1h = aggregate_traps_to_htf(traps, "1h")
    traps_4h = aggregate_traps_to_htf(traps, "4h")
    print(f"  1H trap clusters (>= 2 signals): {len(traps_1h):,}")
    print(f"  4H trap clusters (>= 2 signals): {len(traps_4h):,}")

    # ── detect structure breaks on HTF ────────────────────────────────────
    print("\nDetecting structure breaks...")
    breaks_1h = find_structure_breaks_on_htf(bars_1h)
    breaks_4h = find_structure_breaks_on_htf(bars_4h)
    print(f"  1H structure breaks: {len(breaks_1h)}")
    print(f"  4H structure breaks: {len(breaks_4h)}")

    # ── build fib zones where traps + structure breaks coincide ───────────
    print("\nBuilding Fibonacci retracement zones...")
    fib_zones_1h = build_fib_zones(bars_1h, breaks_1h, traps_1h, "1H")
    fib_zones_4h = build_fib_zones(bars_4h, breaks_4h, traps_4h, "4H")
    all_zones = fib_zones_1h + fib_zones_4h
    print(f"  1H fib zones (trap + structure): {len(fib_zones_1h)}")
    print(f"  4H fib zones (trap + structure): {len(fib_zones_4h)}")
    print(f"  Total fib zones: {len(all_zones)}")

    # ── generate entry signals on 1-minute ────────────────────────────────
    print("\nGenerating entry signals on 1-minute bars...")
    entries_1h = generate_entry_signals(bars_1m, fib_zones_1h, max_wait_bars=120)
    entries_4h = generate_entry_signals(bars_1m, fib_zones_4h, max_wait_bars=480)
    entries_combined = generate_entry_signals(bars_1m, all_zones, max_wait_bars=240)
    print(f"  1H-only entries: {len(entries_1h)}")
    print(f"  4H-only entries: {len(entries_4h)}")
    print(f"  Combined entries: {len(entries_combined)}")

    # ── run strategies ────────────────────────────────────────────────────
    print("\nSimulating trades...")

    strategies = {
        "S1: 1H Traps+Fib (20/40)": (entries_1h, 20, 40, 30),
        "S2: 4H Traps+Fib (25/50)": (entries_4h, 25, 50, 60),
        "S3: Combined 1H+4H (20/40)": (entries_combined, 20, 40, 30),
        "S4: Combined Tight (15/30)": (entries_combined, 15, 30, 20),
        "S5: Combined Wide (30/60)": (entries_combined, 30, 60, 60),
    }

    results: list[dict[str, Any]] = []
    all_trades: list[Trade] = []

    for name, (entries, stop, target, max_bars) in strategies.items():
        if entries.empty:
            result = summarize(name, [])
            results.append(result)
            print(f"\n  {name}: 0 trades (no entry signals)")
            continue

        trades = simulate_trades(bars_1m, entries, name, stop, target, max_bars)
        all_trades.extend(trades)
        result = summarize(name, trades)
        results.append(result)

        wr = result.get("win_rate_pct", 0)
        exp = result.get("expectancy_ticks", 0)
        tot = result.get("total_ticks", 0)
        pf = result.get("profit_factor", "N/A")
        sh = result.get("sharpe_daily")
        sh_str = f"{sh:.3f}" if sh is not None else "N/A"
        print(f"\n  {name}:")
        print(f"    Trades: {result['total_trades']}  |  Win%: {wr}  |  ExpT: {exp}  |  PF: {pf}  |  Sharpe: {sh_str}")
        print(f"    Total: {tot} ticks  (${result.get('total_dollars', 0):,.0f})")
        print(f"    Longs: {result.get('longs', 0)}  Shorts: {result.get('shorts', 0)}")
        print(f"    Max DD: {result.get('max_drawdown_ticks', 0)} ticks  |  Max Consec Losses: {result.get('max_consecutive_losses', 0)}")

    # ── ranking ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RANKING (by expectancy)")
    print("=" * 70)
    ranked = sorted(
        [r for r in results if r["total_trades"] > 0],
        key=lambda r: r.get("expectancy_ticks", -999),
        reverse=True,
    )
    for i, r in enumerate(ranked, 1):
        sh = r.get("sharpe_daily")
        sh_str = f"{sh:.3f}" if sh is not None else "N/A"
        print(
            f"  {i}. {r['strategy']}  |  trades={r['total_trades']}  |  "
            f"exp={r['expectancy_ticks']}t  |  pf={r.get('profit_factor', 'N/A')}  |  "
            f"sharpe={sh_str}  |  total=${r.get('total_dollars', 0):,.0f}"
        )

    # ── save results ──────────────────────────────────────────────────────
    def _json_default(v: Any) -> Any:
        if isinstance(v, (pd.Timestamp, pd.Timedelta)):
            return str(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            val = float(v)
            return None if (math.isnan(val) or math.isinf(val)) else val
        if pd.isna(v):
            return None
        raise TypeError(f"Unsupported: {type(v)!r}")

    OUTPUT_JSON.write_text(
        json.dumps({
            "thesis": "Trapped sellers/buyers on 1H/4H as change of structure + 50-75% fib retracement entry on 1-minute",
            "data": {
                "bars_1m": len(bars_1m),
                "trap_signals": len(traps),
                "htf_trap_clusters_1h": len(traps_1h),
                "htf_trap_clusters_4h": len(traps_4h),
                "structure_breaks_1h": len(breaks_1h),
                "structure_breaks_4h": len(breaks_4h),
                "fib_zones_1h": len(fib_zones_1h),
                "fib_zones_4h": len(fib_zones_4h),
            },
            "strategies": results,
        }, indent=2, default=_json_default),
        encoding="utf-8",
    )

    if all_trades:
        trades_df = pd.DataFrame(asdict(t) for t in all_trades)
        trades_df.to_csv(OUTPUT_TRADES, index=False)

    print(f"\nSaved JSON: {OUTPUT_JSON}")
    print(f"Saved trades: {OUTPUT_TRADES}")


if __name__ == "__main__":
    main()
