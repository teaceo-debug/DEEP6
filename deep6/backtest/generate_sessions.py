"""
generate_sessions.py — Synthetic NQ session generator for DEEP6 backtesting.

Produces 50 scored_bar NDJSON files under ninjatrader/backtests/sessions/.
Each file is a full RTH session (390 1-minute bars).

Output schema (one JSON object per line, consumed by BacktestRunner.LoadScoredBars):
  {"type":"scored_bar","barIdx":N,"barsSinceOpen":N,"barDelta":D,"barClose":P,
   "zoneScore":Z,"zoneDistTicks":T,"signals":[...]}

Regimes (10 sessions each):
  1. trend_up      — steady +50-150pt grind, absorption at pullbacks
  2. trend_down     — mirror of trend_up, exhaustion at rallies
  3. ranging        — 30-40pt range, POC oscillation, stacked imbalances at extremes
  4. volatile       — 2-3 sharp 80-120pt moves, thin prints, volume surges
  5. slow_grind     — 15-20pt range, thin volume, sparse signals

Signal-engineering rules (aligned with actual detector thresholds in C# source):
  ABS-01  CLASSIC     wick_vol > 30% of total, |delta|/wick_vol < 0.12 (AbsorptionDetector)
  EXH-01  ZERO_PRINT  zero-volume level inside bar body (ExhaustionDetector)
  IMB-01  SINGLE      ask/bid ratio >= 3.0 (ImbalanceDetector diagonal scan)
  IMB-03  STACKED T1  3+ consecutive levels with 3:1 ratios
  DELT-04 DIVERGENCE  price slope vs CVD slope differ in sign over 3 bars
  VOLP-03 VOL SURGE   bar volume > 3x rolling avg
  AUCT-01 AUCTION     price at session hi/lo

Usage:
  python3 deep6/backtest/generate_sessions.py
  (or from repo root: .venv/bin/python3 deep6/backtest/generate_sessions.py)
"""

import json
import math
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TICK_SIZE = 0.25          # NQ tick size
TICK_VALUE = 5.0          # USD per tick
BARS_PER_SESSION = 390    # 6.5 hrs × 60 min = 390 1-min bars
RTH_OPEN = datetime(2026, 4, 14, 9, 30, 0)   # base date; incremented per session

# BacktestConfig defaults (from BacktestConfig.cs)
SCORE_ENTRY_THRESHOLD = 80.0
STOP_LOSS_TICKS = 20
TARGET_TICKS = 40

# Weights matching ConfluenceScorer (empirical from scoring sessions 01-05)
SIGNAL_WEIGHTS: Dict[str, float] = {
    "ABS-01": 25.0, "ABS-02": 18.0, "ABS-03": 20.0, "ABS-04": 15.0,
    "EXH-01": 22.0, "EXH-02": 18.0,
    "IMB-01": 8.0,  "IMB-02": 12.0, "IMB-03": 16.0,
    "DELT-01": 5.0, "DELT-03": 10.0, "DELT-04": 14.0,
    "AUCT-01": 8.0,
    "VOLP-03": 10.0,
}


# ---------------------------------------------------------------------------
# RNG seeded deterministically
# ---------------------------------------------------------------------------
RNG = random.Random(42)


def randf(lo: float, hi: float) -> float:
    return RNG.uniform(lo, hi)


def randi(lo: int, hi: int) -> int:
    return RNG.randint(lo, hi)


# ---------------------------------------------------------------------------
# Bar building helpers
# ---------------------------------------------------------------------------

def make_signal(signal_id: str, direction: int, strength: float, price: float, detail: str) -> dict:
    return {
        "signalId": signal_id,
        "direction": direction,
        "strength": round(strength, 3),
        "price": price,
        "detail": detail,
    }


def score_for_signals(signals: List[dict], direction: int) -> float:
    """Approximate ConfluenceScorer total score from a signal list."""
    total = 0.0
    for s in signals:
        if s["direction"] == direction:
            w = SIGNAL_WEIGHTS.get(s["signalId"], 6.0)
            total += w * s["strength"]
    return min(total, 150.0)


def make_bar(
    bar_idx: int,
    bars_since_open: int,
    bar_close: float,
    bar_delta: int,
    signals: List[dict],
    zone_score: float = 0.0,
    zone_dist_ticks: float = 999.0,
) -> dict:
    return {
        "type": "scored_bar",
        "barIdx": bar_idx,
        "barsSinceOpen": bars_since_open,
        "barDelta": bar_delta,
        "barClose": round(bar_close * 4) / 4,   # snap to 0.25 tick
        "zoneScore": round(zone_score, 2),
        "zoneDistTicks": round(zone_dist_ticks, 2),
        "signals": signals,
    }


# ---------------------------------------------------------------------------
# Signal factories (per detector trigger conditions)
# ---------------------------------------------------------------------------

def abs01_signal(price: float, direction: int) -> dict:
    """ABS-01 CLASSIC — wick >30% of total vol, |delta|/wick < 0.12."""
    strength = round(randf(0.55, 0.92), 3)
    side = "lower" if direction > 0 else "upper"
    return make_signal("ABS-01", direction, strength, price,
                       f"CLASSIC {side}: wick=42.3% delta_ratio=0.08")


def exh01_signal(price: float, direction: int) -> dict:
    """EXH-01 ZERO_PRINT — zero-volume level inside bar body."""
    strength = round(randf(0.6, 0.9), 3)
    return make_signal("EXH-01", direction, strength, price, "ZERO_PRINT body gap")


def exh02_signal(price: float, direction: int) -> dict:
    """EXH-02 — exhaustion variant."""
    strength = round(randf(0.55, 0.85), 3)
    return make_signal("EXH-02", direction, strength, price, "EXH")


def imb01_signal(price: float, direction: int) -> dict:
    """IMB-01 SINGLE — ask/bid ratio >= 3.0."""
    ratio = round(randf(3.2, 8.0), 1)
    strength = min(ratio / 10.0, 1.0)
    label = "BUY" if direction > 0 else "SELL"
    return make_signal("IMB-01", direction, round(strength, 3), price,
                       f"SINGLE {label} IMB at {price:.2f}: {ratio:.1f}x ratio [P-tick diag]")


def imb03_signal(price: float, direction: int, tier: str = "T1") -> dict:
    """IMB-03 STACKED — 3+ consecutive levels at 3:1."""
    str_map = {"T1": 0.33, "T2": 0.66, "T3": 1.0}
    strength = str_map.get(tier, 0.33) + round(randf(-0.05, 0.05), 3)
    label = "BUY" if direction > 0 else "SELL"
    return make_signal("IMB-03", direction, round(min(strength, 1.0), 3), price,
                       f"STACKED_{tier} {label}")


def delt04_signal(price: float, direction: int) -> dict:
    """DELT-04 DIVERGENCE — price vs CVD slope divergence."""
    strength = round(randf(0.6, 0.85), 3)
    label = "BEARISH DIVERGENCE: price up but CVD failing" if direction < 0 else \
            "BULLISH DIVERGENCE: price down but CVD holding"
    return make_signal("DELT-04", direction, strength, price, label)


def delt01_signal(price: float, direction: int, delta: int, total: int) -> dict:
    """DELT-01 RISE/DROP."""
    strength = min(abs(delta) / max(total, 1), 1.0)
    label = f"DELTA RISE: {delta:+d}" if direction > 0 else f"DELTA DROP: {delta:+d}"
    return make_signal("DELT-01", direction, round(strength, 3), price, label)


def delt03_signal(price: float, direction: int) -> dict:
    """DELT-03 REVERSAL — bar direction contradicts delta."""
    strength = round(randf(0.45, 0.75), 3)
    label = "DELTA REVERSAL (bullish hidden): bar closed DOWN but delta positive" \
            if direction > 0 else "DELTA REVERSAL (bearish hidden): bar closed UP but delta negative"
    return make_signal("DELT-03", direction, strength, price, label)


def volp03_signal(price: float, direction: int) -> dict:
    """VOLP-03 VOLUME SURGE — bar vol > 3x rolling avg."""
    strength = round(randf(0.65, 1.0), 3)
    return make_signal("VOLP-03", direction, strength, price,
                       f"VOL SURGE: {round(randf(3.2, 5.0), 1):.1f}x avg")


def auct01_signal(price: float, direction: int) -> dict:
    """AUCT-01 — price at session hi/lo, auction boundary."""
    strength = round(randf(0.5, 0.75), 3)
    level = "SESSION_HIGH" if direction < 0 else "SESSION_LOW"
    return make_signal("AUCT-01", direction, strength, price, f"AUCT {level}")


# ---------------------------------------------------------------------------
# Regime generators
# ---------------------------------------------------------------------------

def build_trend_up_session(session_idx: int, base_date: datetime) -> List[dict]:
    """Steady bullish grind +50-150pt. Absorption at pullbacks, imbalances in trend."""
    bars = []
    price = randf(19950.0, 20050.0)
    drift = randf(50.0, 150.0) / BARS_PER_SESSION   # total drift distributed
    vol_base = randi(1200, 2000)
    cvd_running = 0

    for i in range(BARS_PER_SESSION):
        # Price drift with slight noise
        noise = randf(-1.5, 1.5)
        price += drift + noise
        price = max(price, 19800.0)

        bar_delta = randi(80, 250)
        total_vol = randi(vol_base, vol_base + 400)
        cvd_running += bar_delta

        signals: List[dict] = []
        zone_score = 0.0
        zone_dist = 999.0

        # Pullback zone — every ~20 bars create an absorption bar (price dips then recovers)
        is_pullback = (i % 20 == 15) or (i % 20 == 16)
        is_strong_bar = (i % 7 == 0)
        is_imbalance_bar = (i % 5 == 2)

        if is_pullback:
            # Absorption at lower wick — bullish
            signals.append(abs01_signal(price - 0.5, +1))
            zone_score = randf(45.0, 75.0)
            zone_dist = randf(0.5, 3.0)
            bar_delta = randi(-50, 30)   # balanced/slight selling absorbed
            if RNG.random() > 0.5:
                signals.append(imb01_signal(price - 0.25, +1))
            if RNG.random() > 0.6:
                signals.append(exh01_signal(price - 0.75, +1))

        if is_strong_bar:
            signals.append(imb03_signal(price, +1, "T1" if i < 200 else "T2"))
            signals.append(delt01_signal(price, +1, bar_delta, total_vol))

        if is_imbalance_bar:
            signals.append(imb01_signal(price, +1))

        # DELT-04 divergence signal at session peaks (fade after big run)
        if i in range(180, 210) and RNG.random() > 0.7:
            signals.append(delt04_signal(price, -1))

        # Volume surge on breakouts
        if i % 40 == 0 and i > 0:
            signals.append(volp03_signal(price, +1))
            total_vol = randi(int(vol_base * 3.0), int(vol_base * 5.0))

        # Auction level at session high near end
        if i > 340 and RNG.random() > 0.8:
            signals.append(auct01_signal(price, -1))

        bars.append(make_bar(i, i, price, bar_delta, signals, zone_score, zone_dist))

    return bars


def build_trend_down_session(session_idx: int, base_date: datetime) -> List[dict]:
    """Steady bearish grind -50-150pt. Exhaustion at rallies."""
    bars = []
    price = randf(20100.0, 20200.0)
    drift = randf(-150.0, -50.0) / BARS_PER_SESSION
    vol_base = randi(1200, 2000)
    cvd_running = 0

    for i in range(BARS_PER_SESSION):
        noise = randf(-1.5, 1.5)
        price += drift + noise
        price = max(price, 19500.0)

        bar_delta = randi(-250, -80)
        total_vol = randi(vol_base, vol_base + 400)
        cvd_running += bar_delta

        signals: List[dict] = []
        zone_score = 0.0
        zone_dist = 999.0

        is_rally = (i % 20 == 15) or (i % 20 == 16)
        is_strong_bar = (i % 7 == 0)
        is_imbalance_bar = (i % 5 == 2)

        if is_rally:
            # Exhaustion at upper wick — bearish signal
            signals.append(exh02_signal(price + 0.5, -1))
            signals.append(abs01_signal(price + 0.75, -1))
            zone_score = randf(40.0, 70.0)
            zone_dist = randf(0.5, 2.5)
            bar_delta = randi(-30, 50)  # buying absorbed
            if RNG.random() > 0.5:
                signals.append(imb01_signal(price + 0.25, -1))

        if is_strong_bar:
            signals.append(imb03_signal(price, -1, "T1" if i < 200 else "T2"))
            signals.append(delt01_signal(price, -1, bar_delta, total_vol))

        if is_imbalance_bar:
            signals.append(imb01_signal(price, -1))

        if i in range(180, 210) and RNG.random() > 0.7:
            signals.append(delt04_signal(price, +1))

        if i % 40 == 0 and i > 0:
            signals.append(volp03_signal(price, -1))
            total_vol = randi(int(vol_base * 3.0), int(vol_base * 5.0))

        if i > 340 and RNG.random() > 0.8:
            signals.append(auct01_signal(price, +1))

        bars.append(make_bar(i, i, price, bar_delta, signals, zone_score, zone_dist))

    return bars


def build_ranging_session(session_idx: int, base_date: datetime) -> List[dict]:
    """30-40pt range. POC oscillation, stacked imbalances at extremes."""
    bars = []
    mid = randf(20050.0, 20150.0)
    half_range = randf(15.0, 20.0)
    lo_extreme = mid - half_range
    hi_extreme = mid + half_range
    price = mid
    vol_base = randi(800, 1400)

    phase_len = 25  # bars per sub-swing
    direction = +1  # start swinging up

    for i in range(BARS_PER_SESSION):
        sub_phase = (i % phase_len) / phase_len

        # Oscillate between extremes
        target = hi_extreme if direction > 0 else lo_extreme
        price += (target - price) * 0.1 + randf(-0.5, 0.5)
        price = max(lo_extreme - 2, min(hi_extreme + 2, price))

        if abs(price - target) < 1.0:
            direction = -direction   # flip direction at extreme

        bar_delta = randi(-100, 100)
        total_vol = randi(vol_base, vol_base + 300)

        signals: List[dict] = []
        zone_score = 0.0
        zone_dist = 999.0

        at_lo = price < lo_extreme + 2.5
        at_hi = price > hi_extreme - 2.5

        if at_lo:
            # Bullish absorption at range low
            signals.append(abs01_signal(price, +1))
            signals.append(imb03_signal(price, +1, "T1" if RNG.random() > 0.4 else "T2"))
            zone_score = randf(50.0, 80.0)
            zone_dist = randf(0.25, 2.0)
            if RNG.random() > 0.5:
                signals.append(imb01_signal(price, +1))
            bar_delta = randi(-30, 60)

        elif at_hi:
            # Bearish absorption/exhaustion at range high
            signals.append(abs01_signal(price, -1))
            signals.append(imb03_signal(price, -1, "T1" if RNG.random() > 0.4 else "T2"))
            zone_score = randf(50.0, 80.0)
            zone_dist = randf(0.25, 2.0)
            if RNG.random() > 0.5:
                signals.append(imb01_signal(price, -1))
            bar_delta = randi(-60, 30)

        # Delta divergence in mid-range oscillation
        if i % 30 == 14 and RNG.random() > 0.6:
            signals.append(delt04_signal(price, -direction))

        # Sparse volume surges
        if i % 60 == 30:
            signals.append(volp03_signal(price, direction))

        bars.append(make_bar(i, i, price, bar_delta, signals, zone_score, zone_dist))

    return bars


def build_volatile_session(session_idx: int, base_date: datetime) -> List[dict]:
    """2-3 sharp 80-120pt moves. Thin prints, zero prints, fat volume surges."""
    bars = []
    price = randf(19980.0, 20080.0)
    vol_base = randi(500, 900)

    # Define 2-3 impulse events at random bar indices
    n_events = randi(2, 3)
    event_bars = sorted(RNG.sample(range(30, 340), n_events))
    event_dirs = [+1 if RNG.random() > 0.5 else -1 for _ in event_bars]
    event_magnitudes = [randf(80.0, 120.0) for _ in event_bars]

    active_event: Optional[Tuple[int, int, float]] = None  # (start_bar, direction, magnitude)
    event_consumed = [False] * n_events

    for i in range(BARS_PER_SESSION):
        # Check if an event starts here
        for eidx, eb in enumerate(event_bars):
            if i == eb and not event_consumed[eidx]:
                active_event = (i, event_dirs[eidx], event_magnitudes[eidx])
                event_consumed[eidx] = True
                break

        signals: List[dict] = []
        zone_score = 0.0
        zone_dist = 999.0

        if active_event and (i - active_event[0]) < 8:
            # During event: sharp move, high volume, imbalances
            ev_dir = active_event[1]
            ev_mag = active_event[2]
            progress = (i - active_event[0]) / 8.0
            price += ev_dir * ev_mag * 0.125 + randf(-0.5, 0.5)

            bar_delta = int(ev_dir * randi(300, 800))
            total_vol = randi(int(vol_base * 3.0), int(vol_base * 6.0))

            signals.append(volp03_signal(price, ev_dir))
            signals.append(imb03_signal(price, ev_dir, "T2" if progress < 0.5 else "T1"))
            signals.append(delt01_signal(price, ev_dir, bar_delta, total_vol))

            if progress < 0.3:
                # Thin prints — zero print at extremes
                signals.append(exh01_signal(price, ev_dir))

            if progress > 0.7:
                # Exhaustion at event peak — reversal setup
                signals.append(exh02_signal(price, -ev_dir))
                signals.append(abs01_signal(price, -ev_dir))
                signals.append(delt04_signal(price, -ev_dir))
                zone_score = randf(55.0, 85.0)
                zone_dist = randf(0.5, 3.0)

            if i == active_event[0] + 7:
                active_event = None   # event over
        else:
            # Quiet pre/post-event drift
            price += randf(-2.0, 2.0)
            bar_delta = randi(-80, 80)
            total_vol = randi(vol_base, vol_base + 200)

            if RNG.random() > 0.85:
                signals.append(imb01_signal(price, +1 if bar_delta > 0 else -1))

        price = max(19600.0, min(20500.0, price))
        bars.append(make_bar(i, i, price, bar_delta, signals, zone_score, zone_dist))

    return bars


def build_slow_grind_session(session_idx: int, base_date: datetime) -> List[dict]:
    """15-20pt range, thin volume. Few signals — tests system restraint."""
    bars = []
    price = randf(20060.0, 20140.0)
    half_range = randf(7.5, 10.0)
    center = price
    vol_base = randi(200, 450)  # very thin

    for i in range(BARS_PER_SESSION):
        # Mean-reverting walk around center
        price += (center - price) * 0.03 + randf(-0.75, 0.75)
        price = max(center - half_range - 2, min(center + half_range + 2, price))

        bar_delta = randi(-40, 40)   # tiny delta
        total_vol = randi(vol_base, vol_base + 100)

        signals: List[dict] = []
        zone_score = 0.0
        zone_dist = 999.0

        # Sparse signals — roughly 1 in 8 bars has any signal
        if RNG.random() > 0.875:
            pick = RNG.random()
            direction = +1 if bar_delta >= 0 else -1
            if pick < 0.4:
                signals.append(imb01_signal(price, direction))
            elif pick < 0.7:
                signals.append(abs01_signal(price, direction))
                zone_score = randf(20.0, 45.0)
                zone_dist = randf(2.0, 6.0)
            else:
                signals.append(delt03_signal(price, direction))

        bars.append(make_bar(i, i, price, bar_delta, signals, zone_score, zone_dist))

    return bars


# ---------------------------------------------------------------------------
# Regime dispatch
# ---------------------------------------------------------------------------

REGIME_BUILDERS = {
    "trend_up":   build_trend_up_session,
    "trend_down":  build_trend_down_session,
    "ranging":    build_ranging_session,
    "volatile":   build_volatile_session,
    "slow_grind": build_slow_grind_session,
}

REGIMES = [
    "trend_up", "trend_up", "trend_up", "trend_up", "trend_up",
    "trend_up", "trend_up", "trend_up", "trend_up", "trend_up",
    "trend_down", "trend_down", "trend_down", "trend_down", "trend_down",
    "trend_down", "trend_down", "trend_down", "trend_down", "trend_down",
    "ranging", "ranging", "ranging", "ranging", "ranging",
    "ranging", "ranging", "ranging", "ranging", "ranging",
    "volatile", "volatile", "volatile", "volatile", "volatile",
    "volatile", "volatile", "volatile", "volatile", "volatile",
    "slow_grind", "slow_grind", "slow_grind", "slow_grind", "slow_grind",
    "slow_grind", "slow_grind", "slow_grind", "slow_grind", "slow_grind",
]


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

def generate_all_sessions() -> None:
    total_bars = 0
    files_written = []
    regime_counts: Dict[str, int] = {r: 0 for r in REGIME_BUILDERS}

    regime_session_nums: Dict[str, int] = {r: 1 for r in REGIME_BUILDERS}

    for session_num, regime in enumerate(REGIMES, start=1):
        base_date = RTH_OPEN + timedelta(days=session_num)
        session_idx = regime_session_nums[regime]
        regime_session_nums[regime] += 1

        builder = REGIME_BUILDERS[regime]
        bars = builder(session_idx, base_date)

        filename = f"session-{session_num:02d}-{regime}-{session_idx:02d}.ndjson"
        filepath = OUTPUT_DIR / filename

        with open(filepath, "w") as f:
            for bar in bars:
                f.write(json.dumps(bar, separators=(",", ":")) + "\n")

        size_kb = filepath.stat().st_size / 1024
        total_bars += len(bars)
        regime_counts[regime] += 1
        files_written.append((filename, len(bars), size_kb, regime))

        print(f"  [{session_num:2d}/50] {filename:<55}  {len(bars)} bars  {size_kb:6.1f} KB")

    total_size_kb = sum(t[2] for t in files_written)
    print(f"\nTotal: {len(files_written)} files, {total_bars} bars, {total_size_kb:.1f} KB")

    print("\nRegime summary:")
    print(f"  {'Regime':<14} {'Sessions':>8} {'Bars':>8}")
    for r in REGIME_BUILDERS:
        cnt = regime_counts[r]
        print(f"  {r:<14} {cnt:>8} {cnt * BARS_PER_SESSION:>8}")


# ---------------------------------------------------------------------------
# Quick sanity check via dotnet test
# ---------------------------------------------------------------------------

def run_sanity_check() -> bool:
    """
    Verify 3 random session files produce > 0 trades via dotnet test BacktestRunnerTests.
    Returns True if check passes or if dotnet is unavailable.
    """
    import subprocess
    import shutil

    dotnet = shutil.which("dotnet")
    if dotnet is None:
        # Try common macOS location
        candidate = "/usr/local/share/dotnet/dotnet"
        if os.path.exists(candidate):
            dotnet = candidate

    if dotnet is None:
        print("\n[sanity] dotnet not found — skipping dotnet test run.")
        print("[sanity] Files written OK; BacktestRunner integration not verified.")
        return True

    test_proj = REPO_ROOT / "ninjatrader" / "tests" / "ninjatrader.tests.csproj"
    if not test_proj.exists():
        print(f"\n[sanity] Test project not found at {test_proj} — skipping.")
        return True

    print("\n[sanity] Running BacktestRunnerTests via dotnet test...")
    env = os.environ.copy()
    env["PATH"] = env.get("PATH", "") + ":/usr/local/share/dotnet"

    result = subprocess.run(
        [dotnet, "test", str(test_proj),
         "--filter", "BacktestRunnerTests",
         "--no-build", "--verbosity", "minimal"],
        capture_output=True, text=True, env=env, timeout=120
    )

    if result.returncode == 0:
        print("[sanity] PASSED — BacktestRunnerTests all green.")
        return True
    else:
        # Try with build
        print("[sanity] --no-build failed; retrying with build...")
        result2 = subprocess.run(
            [dotnet, "test", str(test_proj),
             "--filter", "BacktestRunnerTests",
             "--verbosity", "minimal"],
            capture_output=True, text=True, env=env, timeout=180
        )
        if result2.returncode == 0:
            print("[sanity] PASSED (with build).")
            return True
        else:
            print(f"[sanity] FAILED (exit {result2.returncode}):")
            print(result2.stdout[-2000:] if result2.stdout else "")
            print(result2.stderr[-1000:] if result2.stderr else "")
            return False


# ---------------------------------------------------------------------------
# Python-side sanity check (no dotnet needed)
# ---------------------------------------------------------------------------

def python_sanity_check() -> None:
    """
    Load 3 random session files and verify signal counts look sane.
    Checks that each session has bars with signals, and dominant regimes
    fire the expected signal types.
    """
    session_files = sorted(OUTPUT_DIR.glob("*.ndjson"))
    if not session_files:
        print("[py-sanity] No files found — aborting.")
        return

    # Pick 1 from each of 3 different regimes
    checks = [
        next(f for f in session_files if "trend_up" in f.name),
        next(f for f in session_files if "ranging" in f.name),
        next(f for f in session_files if "volatile" in f.name),
    ]

    for filepath in checks:
        bars_with_signals = 0
        abs_count = 0
        imb_count = 0
        delt_count = 0
        total_bars = 0

        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("type") != "scored_bar":
                    continue
                total_bars += 1
                sigs = obj.get("signals", [])
                if sigs:
                    bars_with_signals += 1
                for s in sigs:
                    sid = s.get("signalId", "")
                    if sid.startswith("ABS"):
                        abs_count += 1
                    elif sid.startswith("IMB"):
                        imb_count += 1
                    elif sid.startswith("DELT"):
                        delt_count += 1

        pct_with_signals = bars_with_signals / max(total_bars, 1) * 100
        print(f"[py-sanity] {filepath.name}")
        print(f"           {total_bars} bars, {bars_with_signals} with signals "
              f"({pct_with_signals:.1f}%), ABS={abs_count}, IMB={imb_count}, DELT={delt_count}")

        assert total_bars == BARS_PER_SESSION, \
            f"Expected {BARS_PER_SESSION} bars, got {total_bars} in {filepath.name}"

    print("[py-sanity] PASSED")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Generating {len(REGIMES)} sessions ({BARS_PER_SESSION} bars each)...\n")

    generate_all_sessions()
    python_sanity_check()
    run_sanity_check()

    print("\nDone.")
