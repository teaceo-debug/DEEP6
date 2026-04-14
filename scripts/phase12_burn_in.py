"""Phase 12 burn-in observation script (NOT a backtest).

Loads one RTH session of NQ 1m bars, synthesizes plausible aggressor splits and
intrabar delta trajectories (REAL OHLCV + SYNTHETIC microstructure), wires up
the five Phase 12 components, and emits a distributional report to:

    .planning/phases/12-integrate-.../12-BURNIN.md

This is a sanity-check observation pass to flag parameter miscalibration before
investing in a full backtest harness. Does NOT mutate production code.
"""
from __future__ import annotations

import asyncio
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path("/Users/teaceo/DEEP6")
sys.path.insert(0, str(REPO))

from deep6.state.footprint import FootprintBar, FootprintLevel  # noqa: E402
from deep6.orderflow.vpin import VPINEngine  # noqa: E402
from deep6.orderflow.slingshot import SlingshotDetector  # noqa: E402
from deep6.orderflow.setup_tracker import SetupTracker  # noqa: E402
from deep6.orderflow.walk_forward_live import WalkForwardTracker  # noqa: E402

RNG = random.Random(20260413)

# Categories aligned with 09-02 WeightFile 8 groups
CATEGORIES = [
    "absorption", "exhaustion", "imbalance", "delta",
    "divergence", "volume_profile", "trap", "structural",
]
REGIMES = ["TREND_UP", "RANGE", "TREND_DOWN"]


# ---------------------------------------------------------------------------
# Fake ScorerResult/Slingshot shapes for SetupTracker
# ---------------------------------------------------------------------------
class FakeScorer:
    __slots__ = ("total_score", "tier", "direction")

    def __init__(self, total_score: float, tier: str, direction: str) -> None:
        self.total_score = total_score
        self.tier = tier
        self.direction = direction


# ---------------------------------------------------------------------------
# In-memory EventStore stub for WalkForwardTracker persistence
# ---------------------------------------------------------------------------
class MemoryStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def record_walk_forward_outcome(self, **kw) -> None:
        self.rows.append(kw)


# ---------------------------------------------------------------------------
# Synthesize a FootprintBar from an OHLCV row
# ---------------------------------------------------------------------------
def synth_bar(ts: float, o: float, h: float, l: float, c: float, v: int) -> FootprintBar:
    """Build a FootprintBar with plausible intrabar microstructure.

    - Aggressor split biased by body direction & body/range ratio.
    - Volume is distributed across price levels (inverse-distance from POC).
    - running_delta / max_delta / min_delta simulated via a random walk of
      trades drawn bar-wise so DELT_TAIL bit 22 firing is exercised.
    """
    v = int(max(v, 1))
    body = c - o
    rng = max(h - l, 0.25)
    bias = 0.5 + 0.4 * (body / rng) + RNG.uniform(-0.08, 0.08)
    bias = min(0.95, max(0.05, bias))
    ask_vol = int(round(v * bias))
    bid_vol = v - ask_vol

    bar = FootprintBar(timestamp=ts, open=o, high=h, low=l, close=c)

    # Distribute vol across ~5 levels around POC
    poc_tick = int(round(((o + c) / 2) / 0.25))
    n_levels = 5
    ticks = [poc_tick + (i - n_levels // 2) for i in range(n_levels)]
    weights = [1.0 / (1 + abs(t - poc_tick)) for t in ticks]
    wsum = sum(weights)
    for t, w in zip(ticks, weights):
        frac = w / wsum
        lvl_a = int(ask_vol * frac)
        lvl_b = int(bid_vol * frac)
        bar.levels[t] = FootprintLevel(bid_vol=lvl_b, ask_vol=lvl_a)
    bar.total_vol = sum(lv.ask_vol + lv.bid_vol for lv in bar.levels.values())
    bar.bar_delta = sum(lv.ask_vol - lv.bid_vol for lv in bar.levels.values())

    # Simulate intrabar path: n_ticks trades, cumulative signed sum.
    n_ticks = max(20, v // 4)
    p_buy = bias
    run = 0
    mx = 0
    mn = 0
    remaining = v
    for i in range(n_ticks):
        size = max(1, remaining // (n_ticks - i)) if i < n_ticks - 1 else remaining
        remaining -= size
        if RNG.random() < p_buy:
            run += size
        else:
            run -= size
        if run > mx:
            mx = run
        if run < mn:
            mn = run
    bar.running_delta = run  # note: final sim delta; we overwrite to match bar_delta
    # Rescale max/min so they bound the actual bar_delta realistically
    final = bar.bar_delta
    if run != 0:
        scale = abs(final) / max(abs(run), 1)
        mx = int(mx * scale)
        mn = int(mn * scale)
    # Guarantee mx >= final >= mn
    mx = max(mx, final, 0)
    mn = min(mn, final, 0)
    bar.running_delta = final
    bar.max_delta = mx
    bar.min_delta = mn
    return bar


# ---------------------------------------------------------------------------
# DELT_TAIL bit 22 firing check — mirror deep6/engines/delta.py logic
# ---------------------------------------------------------------------------
TAIL_THRESHOLD = 0.95


def delt_tail_fires(bar: FootprintBar) -> tuple[bool, bool]:
    """Return (new_rewire_fires, legacy_proxy_fires).

    legacy_proxy_fires approximates the pre-12-02 path: used bar-geometry proxy
    (|bar_delta| / bar_total approximation — close-at-high proxy) instead of
    the TRUE intrabar extreme.
    """
    delta = bar.bar_delta
    # NEW (post-rewire): TRUE intrabar extreme
    new_fires = False
    if delta > 0:
        ext = bar.max_delta if bar.max_delta > 0 else delta
        tail = delta / ext if ext > 0 else 0.0
        new_fires = tail >= TAIL_THRESHOLD
    elif delta < 0:
        ext = bar.min_delta if bar.min_delta < 0 else delta
        tail = delta / ext if ext < 0 else 0.0
        new_fires = tail >= TAIL_THRESHOLD

    # LEGACY proxy: "closed within 5% of bar H/L"
    rng = max(bar.high - bar.low, 0.25)
    if delta > 0:
        legacy = (bar.close - bar.low) / rng >= TAIL_THRESHOLD
    elif delta < 0:
        legacy = (bar.high - bar.close) / rng >= TAIL_THRESHOLD
    else:
        legacy = False
    return new_fires, legacy


# ---------------------------------------------------------------------------
# Load one RTH session
# ---------------------------------------------------------------------------
def load_rth_session() -> pd.DataFrame:
    df = pd.read_parquet(REPO / "data/ohlcv/NQ_1m_continuous.parquet")
    # Convert UTC -> ET (approx, ignoring DST intricacies for burn-in)
    df = df.tz_convert("America/New_York")
    # Pick the most recent full weekday RTH 9:30–16:00
    df = df.between_time("09:30", "15:59")
    # Last session only
    last_day = df.index[-1].date()
    session = df[df.index.date == last_day]
    if len(session) < 200:
        # fall back to second-to-last
        days = sorted(set(df.index.date))
        for d in reversed(days[:-1]):
            s = df[df.index.date == d]
            if len(s) >= 200:
                session = s
                break
    return session


# ---------------------------------------------------------------------------
# Simulated scorer — drives SetupTracker with realistic score variation
# ---------------------------------------------------------------------------
def synth_scorer(bar: FootprintBar, prev_close: float | None) -> FakeScorer:
    """Translate a bar into a plausible ScorerResult-like object.

    Score = abs(delta)/total_vol * 100 biased by body direction. Tier gated
    by thresholds. Direction = sign of (close - open).
    """
    body = bar.close - bar.open
    vol = max(bar.total_vol, 1)
    base = abs(bar.bar_delta) / vol * 100.0
    score = min(95.0, base * 1.3 + RNG.uniform(-15, 15))
    score = max(0.0, score)
    if score >= 80:
        tier = "TYPE_A"
    elif score >= 55:
        tier = "TYPE_B"
    elif score >= 35:
        tier = "TYPE_C"
    else:
        tier = "NONE"
    if body > 0.5:
        direction = "LONG"
    elif body < -0.5:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"
    return FakeScorer(score, tier, direction)


# ---------------------------------------------------------------------------
# Main burn-in
# ---------------------------------------------------------------------------
async def main() -> None:
    session = load_rth_session()
    print(f"Loaded {len(session)} RTH 1m bars for {session.index[0].date()}")

    # Components
    vpin = VPINEngine(bucket_volume=1000, warmup_buckets=10)
    sling = SlingshotDetector()
    tracker = SetupTracker(timeframe="1m", cooldown_bars=5)
    store = MemoryStore()
    wf = WalkForwardTracker(
        store=store,
        horizons=(5, 10, 20),
        sharpe_window=50,                 # reduced from 200 for single-session burn-in
        disable_sharpe_threshold=0.0,
        recovery_sharpe_threshold=0.3,
        recovery_window=25,
        neutral_threshold_ticks=0.5,
        session_close_buffer_bars=20,
    )

    # Collectors
    vpin_mods: list[float] = []
    vpin_pcts: list[float] = []
    vpin_regimes = Counter()
    sling_fires_by_variant = Counter()
    sling_fires_total = 0
    state_counts = Counter()
    soak_bars_when_triggered: list[int] = []
    delt_new_fires = 0
    delt_legacy_fires = 0
    delt_new_only = 0
    delt_legacy_only = 0

    bars_list: list[FootprintBar] = []
    prev_close: float | None = None
    session_id = str(session.index[0].date())
    total_bars = len(session)

    for i, (ts, row) in enumerate(session.iterrows()):
        bar = synth_bar(
            ts=ts.timestamp(),
            o=float(row.Open), h=float(row.High), l=float(row.Low),
            c=float(row.Close), v=int(row.Volume),
        )
        bars_list.append(bar)

        # --- VPIN ---
        vpin.update_from_bar(bar)
        mod = vpin.get_confidence_modifier()
        pct = vpin.get_percentile()
        vpin_mods.append(mod)
        vpin_pcts.append(pct)
        vpin_regimes[vpin.get_flow_regime().value] += 1

        # --- Slingshot ---
        sling.update_history(bar.bar_delta)
        result = sling.detect(bars_list[-4:], gex_distance_ticks=None)
        if result.fired:
            sling_fires_total += 1
            sling_fires_by_variant[result.variant] += 1

        # --- DELT_TAIL firing ---
        new_fire, legacy_fire = delt_tail_fires(bar)
        if new_fire:
            delt_new_fires += 1
        if legacy_fire:
            delt_legacy_fires += 1
        if new_fire and not legacy_fire:
            delt_new_only += 1
        if legacy_fire and not new_fire:
            delt_legacy_only += 1

        # --- SetupTracker ---
        scorer = synth_scorer(bar, prev_close)
        tracker.update(scorer, result, current_bar_index=i)
        state_counts[tracker.state] += 1
        if tracker.state == "TRIGGERED" and tracker.active_setup:
            soak_bars_when_triggered.append(tracker.active_setup.soak_bars)
        # Simulate entries — if triggered, close after 4 bars to free state
        if tracker.state == "MANAGING" and tracker.active_setup and tracker.active_setup.bars_managing >= 4:
            tracker.close_trade(tracker.active_setup.setup_id, outcome="CLOSED")

        # --- WalkForward: emit one synthetic signal per bar into a rotating category/regime ---
        cat = CATEGORIES[i % len(CATEGORIES)]
        reg = REGIMES[(i // 7) % len(REGIMES)]
        direction = "LONG" if bar.bar_delta >= 0 else "SHORT"
        bars_until_close = max(0, total_bars - i - 1)
        await wf.record_signal(
            category=cat, regime=reg, direction=direction,
            entry_price=bar.close, bar_index=i, session_id=session_id,
            signal_event_id=i, bars_until_rth_close=bars_until_close,
        )
        await wf.update_price(
            close_price=bar.close, bar_index=i, session_id=session_id,
            bars_until_rth_close=bars_until_close,
        )
        prev_close = bar.close

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    def histo(vals: list[float], edges: list[float]) -> list[tuple[str, int]]:
        buckets = [0] * (len(edges) - 1)
        for v in vals:
            for i in range(len(edges) - 1):
                if edges[i] <= v < edges[i + 1]:
                    buckets[i] += 1
                    break
            else:
                if v >= edges[-1]:
                    buckets[-1] += 1
        return [(f"[{edges[i]:.2f}, {edges[i+1]:.2f})", buckets[i]) for i in range(len(buckets))]

    vpin_hist = histo(vpin_mods, [0.2, 0.4, 0.6, 0.8, 0.95, 1.05, 1.2, 1.21])

    # WF Sharpe convergence
    wf_resolved = len(store.rows)
    wf_by_cell = Counter()
    wf_sharpes: dict[tuple[str, str], float] = {}
    pnls = defaultdict(list)
    for r in store.rows:
        if r["outcome_label"] == "EXPIRED":
            continue
        pnls[(r["regime"], r["category"])].append(r["pnl_ticks"])
        wf_by_cell[(r["regime"], r["category"])] += 1
    for key, vs in pnls.items():
        if len(vs) >= 10:
            m = statistics.mean(vs)
            s = statistics.pstdev(vs) or 1e-9
            wf_sharpes[key] = m / s
    disabled = {k: v for k, v in wf._disabled.items() if v}

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    out = []
    out.append("# Phase 12 Burn-In Observation Report\n")
    out.append(f"**Session:** {session_id}  ")
    out.append(f"**Bars:** {total_bars} (1m RTH)  ")
    out.append("**Data:** REAL NQ 1m OHLCV from `data/ohlcv/NQ_1m_continuous.parquet`  ")
    out.append("**Microstructure:** SYNTHETIC (aggressor split biased by body direction; ")
    out.append("intrabar delta simulated as biased random walk). Not suitable for P&L claims — ")
    out.append("validates firing-rate calibration only.\n")

    out.append("## 1. VPIN confidence modifier distribution\n")
    out.append(f"min={min(vpin_mods):.3f}  max={max(vpin_mods):.3f}  ")
    out.append(f"mean={statistics.mean(vpin_mods):.3f}  median={statistics.median(vpin_mods):.3f}  ")
    out.append(f"stdev={statistics.pstdev(vpin_mods):.3f}\n")
    out.append("Histogram:")
    for label, n in vpin_hist:
        out.append(f"  - `{label}` : {n}  ({100*n/len(vpin_mods):.1f}%)")
    out.append(f"\nFlow regime occupancy: {dict(vpin_regimes)}")
    out.append(f"% of bars at neutral [0.95, 1.05): "
               f"{100*sum(1 for m in vpin_mods if 0.95<=m<1.05)/len(vpin_mods):.1f}%\n")

    out.append("## 2. TRAP_SHOT slingshot cadence\n")
    out.append(f"Total fires this session: **{sling_fires_total}**")
    out.append(f"Per-variant: {dict(sling_fires_by_variant)}")
    out.append(f"z_threshold={sling.z_threshold}  min_history_bars={sling.min_history_bars}")
    fpm = sling_fires_total / max(total_bars, 1)
    out.append(f"Fires per bar: {fpm:.4f}  (≈ {fpm*60:.2f}/hour)\n")

    out.append("## 3. SetupTracker state distribution\n")
    for s in ("SCANNING", "DEVELOPING", "TRIGGERED", "MANAGING", "COOLDOWN"):
        n = state_counts.get(s, 0)
        out.append(f"  - **{s:11s}** : {n:4d}  ({100*n/total_bars:.1f}%)")
    if soak_bars_when_triggered:
        out.append(f"\nsoak_bars at TRIGGERED: "
                   f"mean={statistics.mean(soak_bars_when_triggered):.1f} "
                   f"min={min(soak_bars_when_triggered)} "
                   f"max={max(soak_bars_when_triggered)} "
                   f"n={len(soak_bars_when_triggered)}")
    else:
        out.append("\nNo TRIGGERED transitions observed.")
    out.append("")

    out.append("## 4. Walk-forward tracker convergence\n")
    out.append(f"Total signals recorded: {total_bars}")
    out.append(f"Outcomes resolved: {wf_resolved}  (across 3 horizons = {total_bars*3} pending emissions)")
    expired = sum(1 for r in store.rows if r['outcome_label'] == 'EXPIRED')
    out.append(f"EXPIRED: {expired}  CORRECT: {sum(1 for r in store.rows if r['outcome_label']=='CORRECT')}  "
               f"INCORRECT: {sum(1 for r in store.rows if r['outcome_label']=='INCORRECT')}  "
               f"NEUTRAL: {sum(1 for r in store.rows if r['outcome_label']=='NEUTRAL')}")
    out.append(f"Cells with ≥50 samples (sharpe_window): {sum(1 for v in pnls.values() if len(v)>=50)}")
    out.append(f"Auto-disabled cells: {len(disabled)}")
    if wf_sharpes:
        ranked = sorted(wf_sharpes.items(), key=lambda kv: kv[1])
        out.append("Sample per-cell Sharpe (bottom 3 / top 3):")
        for k, s in ranked[:3] + ranked[-3:]:
            out.append(f"  - {k[0]}/{k[1]}: sharpe={s:.3f}  (n={len(pnls[k])})")
    out.append("")

    out.append("## 5. DELT_TAIL bit 22 firing — pre/post rewire\n")
    out.append(f"NEW (intrabar-extreme)        fires: {delt_new_fires}  "
               f"({100*delt_new_fires/total_bars:.1f}% of bars)")
    out.append(f"LEGACY (bar-geometry proxy)   fires: {delt_legacy_fires}  "
               f"({100*delt_legacy_fires/total_bars:.1f}% of bars)")
    out.append(f"NEW-only (rewire captured new): {delt_new_only}")
    out.append(f"LEGACY-only (rewire suppressed): {delt_legacy_only}")
    out.append("")

    out.append("## Parameter calibration flags\n")
    flags = []
    neutral_frac = sum(1 for m in vpin_mods if 0.95 <= m < 1.05) / len(vpin_mods)
    if neutral_frac > 0.8:
        flags.append(f"- **VPIN clusters at neutral** ({100*neutral_frac:.0f}% in [0.95,1.05)) — "
                     "warmup_buckets=10 may be too deep for low-volume sessions; "
                     "consider warmup_buckets=5 or smaller bucket_volume (500 vs 1000).")
    if sling_fires_total == 0:
        flags.append("- **TRAP_SHOT never fired** — z_threshold=2.0 too strict on synthetic microstructure; "
                     "try z_threshold=1.5 and re-check on real footprint data.")
    if state_counts.get("TRIGGERED", 0) + state_counts.get("MANAGING", 0) == 0:
        flags.append("- **SetupTracker never left DEVELOPING → TRIGGERED** — SCORE_MIN_TIER_A_CROSS=80 "
                     "+ soak_bars≥10 + TYPE_A tier is a narrow triple-gate on single-session data. "
                     "Verify synthetic scorer produces Tier-A bars (threshold 80).")
    if not disabled and wf_resolved > 500:
        flags.append("- WalkForward auto-disable not exercised within one session (expected with "
                     "sharpe_window=50 and ~20 samples/cell); needs multi-session burn-in.")
    if delt_new_fires < delt_legacy_fires * 0.5:
        flags.append(f"- **DELT_TAIL rewire fires notably less** than legacy proxy "
                     f"({delt_new_fires} vs {delt_legacy_fires}). Intrabar extreme is stricter than "
                     "close-at-H/L proxy — this is EXPECTED and desired (fewer false positives).")
    elif delt_new_fires > delt_legacy_fires * 2:
        flags.append(f"- DELT_TAIL rewire fires more than 2× legacy — synthetic intrabar path may "
                     f"under-represent max_delta; real DOM replay needed for true firing rate.")

    if not flags:
        flags.append("- No miscalibrations flagged by this burn-in.")
    out.extend(flags)
    out.append("")

    out.append("## Recommended next steps\n")
    out.append("1. Re-run on Databento MBO replay (real intrabar trade stream) — will give TRUE "
               "max_delta / min_delta rather than simulated, finalizing DELT_TAIL rewire firing rate.")
    out.append("2. Sweep VPIN `(bucket_volume, warmup_buckets)` ∈ {(500,5),(1000,10),(2000,15)} "
               "across 10 sessions; pick the config where modifier histogram is widest.")
    out.append("3. Sweep SlingshotDetector `z_threshold` ∈ {1.5, 1.75, 2.0, 2.25} — target is "
               "1–3 fires/session on average real RTH data.")
    out.append("4. Verify SetupTracker SCORE_MIN_TIER_A_CROSS=80 using real ScorerResult stream; "
               "this burn-in uses a synthetic scorer and cannot validate the threshold.")
    out.append("5. Run WalkForwardTracker across 5+ trading days to exercise the 50-sample "
               "auto-disable path.\n")

    report = "\n".join(out)
    out_path = REPO / ".planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-BURNIN.md"
    out_path.write_text(report)
    print(f"\nReport written: {out_path}\n")
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
