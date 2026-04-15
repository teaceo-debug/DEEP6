"""Backtest signal engine against historical NQ data via Databento.

Runs the full DEEP6 signal pipeline on historical bars and exports
results for analysis with vectorbt or manual review.

Usage:
    python scripts/backtest_signals.py --start 2026-04-09 --end 2026-04-10 --output backtest.csv
"""
import argparse
import csv
import sys
import os
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

import databento as db

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep6.state.footprint import FootprintBar
from deep6.engines.narrative import classify_bar, NarrativeType
from deep6.engines.signal_config import AbsorptionConfig, ExhaustionConfig, ScorerConfig
from deep6.backtest.triple_barrier import compute_triple_barrier, ExitReason
import numpy as np
from deep6.engines.delta import DeltaEngine
from deep6.engines.auction import AuctionEngine
from deep6.engines.poc import POCEngine
from deep6.engines.volume_profile import SessionProfile
from deep6.engines.exhaustion import reset_cooldowns
from deep6.engines.trap import TrapEngine
from deep6.engines.vol_patterns import VolPatternEngine
from deep6.orderflow.vpin import VPINEngine
from deep6.scoring.scorer import score_bar, SignalTier

# Optional engines — guarded because they need external deps / data
try:
    from deep6.engines.gex import GexEngine  # type: ignore
    _HAS_GEX = True
except Exception:  # pragma: no cover - defensive
    _HAS_GEX = False

try:
    from deep6.ml.hmm_regime import HMMRegimeDetector  # type: ignore
    _HAS_HMM = True
except Exception:  # pragma: no cover - defensive
    _HAS_HMM = False


def build_bars(data, bar_seconds: int = 60) -> list[FootprintBar]:
    """Build FootprintBars from Databento trade records."""
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


def run_backtest(bars: list[FootprintBar]) -> list[dict]:
    """Run full signal pipeline on bars, return row per bar."""
    delta_eng = DeltaEngine()
    auction_eng = AuctionEngine()
    poc_eng = POCEngine()
    profile = SessionProfile()
    trap_eng = TrapEngine()
    volpat_eng = VolPatternEngine()
    vpin_eng = VPINEngine()
    reset_cooldowns()

    # Optional: GEX engine (requires MASSIVE_API_KEY — massive.com GEX API)
    gex_eng = None
    gex_key = os.environ.get("MASSIVE_API_KEY", "") or os.environ.get("POLYGON_API_KEY", "")
    if _HAS_GEX and gex_key:
        try:
            gex_eng = GexEngine(api_key=gex_key)
        except Exception as exc:
            print(f"[warn] GEX engine init failed: {exc}")
            gex_eng = None

    # Optional: HMM regime detector — fit during warmup, predict per bar
    hmm = None
    if _HAS_HMM:
        try:
            hmm = HMMRegimeDetector()
        except Exception as exc:
            print(f"[warn] HMM init failed: {exc}")
            hmm = None

    # Config instances — default values per D-01 (no hand-tuning until Phase 7)
    abs_config = AbsorptionConfig()
    exh_config = ExhaustionConfig()

    results = []
    vol_ema = 1000.0
    # Rolling ATR(20) computed from prior bars only — no look-ahead
    atr_values: list[float] = []
    atr = 15.0  # seed until we have 20 bars

    # Caller-maintained state for Trap/VolPat engines
    cvd_history: list[int] = []
    bar_history: deque[FootprintBar] = deque(maxlen=20)
    poc_history: list[float] = []

    # Accumulate rows for HMM fit (refit periodically using prior rows only)
    hmm_rows: list[dict] = []
    HMM_WARMUP_BARS = 60
    HMM_REFIT_EVERY = 120
    current_regime_label = "ABSORPTION_FRIENDLY"

    # Pre-compute OHLC arrays for triple barrier computation
    highs_arr = np.array([b.high for b in bars])
    lows_arr = np.array([b.low for b in bars])
    closes_arr = np.array([b.close for b in bars])

    for i, bar in enumerate(bars):
        if i > 0:
            vol_ema = vol_ema * 0.95 + bar.total_vol * 0.05
        # Update rolling ATR from prior bars (no look-ahead bias)
        atr_values.append(bar.bar_range)
        if len(atr_values) >= 20:
            atr = sum(atr_values[-20:]) / 20.0
        elif len(atr_values) >= 5:
            atr = sum(atr_values) / len(atr_values)

        # Volume profile
        profile.add_bar(bar)
        if i > 0 and i % 10 == 0:
            profile.detect_zones(bar.close)
        profile.update_zones(bar, i)

        # Run engines
        narrative = classify_bar(
            bar, prior_bar=bars[i - 1] if i > 0 else None,
            bar_index=i, atr=atr, vol_ema=vol_ema,
            abs_config=abs_config, exh_config=exh_config,
        )
        delta_sigs = delta_eng.process(bar)
        auction_sigs = auction_eng.process(bar)
        poc_sigs = poc_eng.process(bar)

        # Trap / VolPattern engines (use caller-maintained state)
        prior_bar = bars[i - 1] if i > 0 else None
        trap_sigs = trap_eng.process(
            bar, prior_bar=prior_bar, vol_ema=vol_ema, cvd_history=cvd_history,
        )
        volpat_sigs = volpat_eng.process(
            bar, bar_history=list(bar_history), vol_ema=vol_ema, poc_history=poc_history,
        )

        # VPIN — update from bar, compute modifier
        vpin_eng.update_from_bar(bar)
        vpin_modifier = vpin_eng.get_confidence_modifier()
        flow_regime = vpin_eng.get_flow_regime().value

        # GEX signal — optional
        gex_signal = None
        if gex_eng is not None:
            try:
                gex_signal = gex_eng.get_signal(bar.close)
            except Exception:
                gex_signal = None

        # Score — pass bar_delta and session position for optimization gates
        active_zones = profile.get_active_zones(min_score=20)
        bar_index_in_session = i % 390  # 390 bars per RTH session
        result = score_bar(
            narrative=narrative,
            delta_signals=delta_sigs,
            auction_signals=auction_sigs,
            poc_signals=poc_sigs,
            active_zones=active_zones,
            bar_close=bar.close,
            bar_delta=bar.bar_delta,
            bar_index_in_session=bar_index_in_session,
            gex_signal=gex_signal,
            vpin_modifier=vpin_modifier,
        )

        # Future price for P&L with realistic costs
        # Slippage: 1 tick per side (0.25 pts x 2 = 0.50 pts round-trip)
        # Commission: $4.50/RT at $5/pt = 0.90 pts equivalent
        SLIPPAGE_PTS = 0.50
        COMMISSION_PTS = 0.90
        COST_PER_TRADE = SLIPPAGE_PTS + COMMISSION_PTS  # 1.40 pts total

        close_1 = bars[i + 1].close if i + 1 < len(bars) else bar.close
        close_3 = bars[i + 3].close if i + 3 < len(bars) else bar.close
        close_5 = bars[i + 5].close if i + 5 < len(bars) else bar.close

        # Raw P&L (directional)
        raw_pnl_1 = (close_1 - bar.close) * result.direction
        raw_pnl_3 = (close_3 - bar.close) * result.direction
        raw_pnl_5 = (close_5 - bar.close) * result.direction

        # Apply costs only to scored signals (QUIET has no trade)
        is_trade = result.tier != SignalTier.QUIET
        cost = COST_PER_TRADE if is_trade else 0.0

        # Triple barrier P&L (replaces fixed N-bar P&L for tradeable signals)
        tb_pnl = 0.0
        tb_r = 0.0
        tb_bars = 0
        tb_reason = ""
        tb_mfe = 0.0  # max favorable excursion (R)
        tb_mae = 0.0  # max adverse excursion (R)
        if result.tier != SignalTier.QUIET and result.direction != 0 and i + 1 < len(bars):
            try:
                trade = compute_triple_barrier(
                    highs=highs_arr, lows=lows_arr, closes=closes_arr,
                    entry_bar=i, direction=result.direction, atr=atr,
                    stop_atr_mult=0.8, target_atr_mult=1.5, max_hold_bars=15,
                )
                tb_pnl = trade.pnl_points
                tb_r = trade.r_multiple
                tb_bars = trade.bars_held
                tb_reason = trade.exit_reason.value
                tb_mfe = trade.max_favorable
                tb_mae = trade.max_adverse
            except Exception:
                pass

        # HMM regime — fit on accumulated rows, then predict
        if hmm is not None:
            if i >= HMM_WARMUP_BARS and (
                not hmm.is_fitted() or (i % HMM_REFIT_EVERY == 0)
            ):
                try:
                    hmm.fit(hmm_rows)
                except Exception as exc:
                    print(f"[warn] HMM fit failed at bar {i}: {exc}")
            if hmm.is_fitted():
                try:
                    current_regime_label = hmm.predict_current(hmm_rows[-20:]).value
                except Exception:
                    pass

        results.append({
            "bar_index": i,
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.total_vol,
            "delta": bar.bar_delta,
            "cvd": bar.cvd,
            "poc": bar.poc_price,
            "narrative": narrative.bar_type.name,
            "narrative_dir": narrative.direction,
            "narrative_strength": round(narrative.strength, 3),
            "narrative_label": narrative.label,
            "abs_count": len(narrative.absorption),
            "exh_count": len(narrative.exhaustion),
            "imb_stacked": sum(1 for s in narrative.imbalances if "STACKED" in s.imb_type.name),
            "imb_traps": sum(1 for s in narrative.imbalances if "TRAP" in s.imb_type.name),
            "delta_divergence": sum(1 for s in delta_sigs if s.delta_type.name == "DIVERGENCE"),
            "delta_slingshot": sum(1 for s in delta_sigs if s.delta_type.name == "SLINGSHOT"),
            "delta_cvd_div": sum(1 for s in delta_sigs if s.delta_type.name == "CVD_DIVERGENCE"),
            "auction_finished": sum(1 for s in auction_sigs if s.auction_type.name == "FINISHED_AUCTION"),
            "auction_unfinished": sum(1 for s in auction_sigs if s.auction_type.name == "UNFINISHED_BUSINESS"),
            "poc_extreme": sum(1 for s in poc_sigs if "EXTREME" in s.poc_type.name),
            "trap_count": len(trap_sigs),
            "volpat_count": len(volpat_sigs),
            "vpin": round(vpin_eng.get_vpin(), 4),
            "vpin_modifier": round(vpin_modifier, 3),
            "flow_regime": flow_regime,
            "gex_regime": gex_signal.regime.name if gex_signal is not None else "NONE",
            "hmm_regime": current_regime_label,
            "score": round(result.total_score, 1),
            "tier": result.tier.name,
            "direction": result.direction,
            "categories": result.category_count,
            "confluence_mult": result.confluence_mult,
            "zone_bonus": result.zone_bonus,
            "categories_list": "|".join(result.categories_firing),
            "close_1bar": close_1,
            "close_3bar": close_3,
            "close_5bar": close_5,
            "pnl_1bar": round(raw_pnl_1 - cost, 2),
            "pnl_3bar": round(raw_pnl_3 - cost, 2),
            "pnl_5bar": round(raw_pnl_5 - cost, 2),
            "pnl_tb": round(tb_pnl - cost if tb_bars > 0 else 0, 2),
            "r_multiple": round(tb_r, 3),
            "tb_bars": tb_bars,
            "tb_reason": tb_reason,
            "tb_mfe": round(tb_mfe, 3),
            "tb_mae": round(tb_mae, 3),
        })

        # Update caller-maintained state AFTER processing the bar
        cvd_history.append(bar.cvd)
        bar_history.append(bar)
        poc_history.append(bar.poc_price)

        # Feed minimal HMM-compatible row (maps from scorer result)
        if hmm is not None:
            hmm_rows.append({
                "total_score": result.total_score,
                "engine_agreement": min(result.category_count / 8.0, 1.0),
                "category_count": result.category_count,
                "direction": result.direction,
                "ts": bar.timestamp,
            })

    return results


def main():
    parser = argparse.ArgumentParser(description="DEEP6 Signal Backtest")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", default="backtest.csv", help="Output CSV path")
    parser.add_argument("--bar-seconds", type=int, default=60, help="Bar duration")
    args = parser.parse_args()

    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.environ.get("DATABENTO_API_KEY", "")

    if not api_key:
        print("Set DATABENTO_API_KEY in .env or environment")
        sys.exit(1)

    # Timezone-correct RTH window: 9:30 ET open → 16:00 ET close, converted to UTC.
    ET = ZoneInfo("America/New_York")
    UTC = ZoneInfo("UTC")
    start_et = datetime.fromisoformat(args.start).replace(
        tzinfo=ET, hour=9, minute=30, second=0, microsecond=0,
    )
    end_et = datetime.fromisoformat(args.end).replace(
        tzinfo=ET, hour=16, minute=0, second=0, microsecond=0,
    )
    start_utc = start_et.astimezone(UTC).isoformat()
    end_utc = end_et.astimezone(UTC).isoformat()

    print(f"Fetching NQ trades {args.start} to {args.end} (ET 09:30–16:00)...")
    print(f"  UTC window: {start_utc} → {end_utc}")
    client = db.Historical(key=api_key)
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="trades",
        stype_in="continuous",
        symbols=["NQ.c.0"],
        start=start_utc,
        end=end_utc,
    )

    print("Building footprint bars...")
    bars = build_bars(data, bar_seconds=args.bar_seconds)
    print(f"Built {len(bars)} bars")

    print("Running signal pipeline...")
    results = run_backtest(bars)

    # Write CSV
    if results:
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"Wrote {len(results)} rows to {args.output}")

    # Print summary
    tiers = {}
    pnl_by_tier = {}
    trap_total = 0
    volpat_total = 0
    for r in results:
        t = r["tier"]
        tiers[t] = tiers.get(t, 0) + 1
        if t not in pnl_by_tier:
            pnl_by_tier[t] = {"count": 0, "pnl_1": 0, "pnl_3": 0, "pnl_5": 0, "wins_3": 0}
        pnl_by_tier[t]["count"] += 1
        pnl_by_tier[t]["pnl_1"] += r["pnl_1bar"]
        pnl_by_tier[t]["pnl_3"] += r["pnl_3bar"]
        pnl_by_tier[t]["pnl_5"] += r["pnl_5bar"]
        if r["pnl_3bar"] > 0:
            pnl_by_tier[t]["wins_3"] += 1
        trap_total += r.get("trap_count", 0)
        volpat_total += r.get("volpat_count", 0)

    print(f"\n{'=' * 70}")
    print(f"BACKTEST RESULTS: {len(bars)} bars | {args.start} to {args.end}")
    print(f"{'=' * 70}")
    print(f"Trap signals fired: {trap_total} | VolPattern signals fired: {volpat_total}")
    print(f"{'Tier':<10} {'Count':>6} {'Pct':>6} {'P&L 1bar':>10} {'P&L 3bar':>10} {'P&L 5bar':>10} {'Win% 3bar':>10}")
    print(f"{'-' * 70}")
    for tier_name in ["TYPE_A", "TYPE_B", "TYPE_C", "QUIET"]:
        if tier_name in pnl_by_tier:
            d = pnl_by_tier[tier_name]
            n = d["count"]
            pct = n / len(results) * 100
            win_pct = d["wins_3"] / n * 100 if n > 0 else 0
            print(f"{tier_name:<10} {n:>6} {pct:>5.1f}% {d['pnl_1']:>+10.2f} "
                  f"{d['pnl_3']:>+10.2f} {d['pnl_5']:>+10.2f} {win_pct:>9.1f}%")

    # Triple barrier summary
    tb_trades = [r for r in results if r["tb_bars"] > 0 and r["tier"] != "QUIET"]
    if tb_trades:
        print(f"\n=== TRIPLE BARRIER RESULTS ===")
        for tier_name in ["TYPE_A", "TYPE_B", "TYPE_C"]:
            tier_trades = [r for r in tb_trades if r["tier"] == tier_name]
            if not tier_trades:
                continue
            n = len(tier_trades)
            total_pnl = sum(r["pnl_tb"] for r in tier_trades)
            wins = sum(1 for r in tier_trades if r["pnl_tb"] > 0)
            avg_r = sum(r["r_multiple"] for r in tier_trades) / n
            avg_bars = sum(r["tb_bars"] for r in tier_trades) / n
            # Exit reason breakdown
            reasons = {}
            for r in tier_trades:
                reasons[r["tb_reason"]] = reasons.get(r["tb_reason"], 0) + 1
            print(f"{tier_name}: n={n} win%={wins/n*100:.0f}% total_pnl={total_pnl:+.1f} avg_r={avg_r:+.2f} avg_bars={avg_bars:.1f}")
            print(f"  exits: {reasons}")

    # Top signals by P&L
    scored = [r for r in results if r["tier"] != "QUIET"]
    scored.sort(key=lambda r: r["pnl_3bar"], reverse=True)
    if scored:
        print(f"\nTOP 5 SIGNALS BY 3-BAR P&L:")
        for r in scored[:5]:
            print(f"  Bar {r['bar_index']:>3} | {r['tier']:<8} | {r['narrative_label'][:50]:<50} | "
                  f"P&L={r['pnl_3bar']:>+.2f} | cats={r['categories_list']}")

        print(f"\nBOTTOM 5 SIGNALS BY 3-BAR P&L:")
        for r in scored[-5:]:
            print(f"  Bar {r['bar_index']:>3} | {r['tier']:<8} | {r['narrative_label'][:50]:<50} | "
                  f"P&L={r['pnl_3bar']:>+.2f} | cats={r['categories_list']}")


if __name__ == "__main__":
    main()
