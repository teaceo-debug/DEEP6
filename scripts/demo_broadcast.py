"""Looping demo broadcaster for DEEP6 dashboard validation.

Streams realistic NQ-futures-like market activity indefinitely to the backend's
/api/live/test-broadcast endpoint.  Every tick fires a status heartbeat; bars,
tape prints, scores, and signals follow a realistic cadence driven by a random-
walk price model with configurable speed and duration.

Usage (quickstart — streams until Ctrl-C):
    python scripts/demo_broadcast.py

Options:
    --url http://localhost:8000   Backend base URL
    --rate 1.0                   Speed multiplier (2.0 = 2× faster)
    --duration 0                 Seconds to run; 0 = run forever
    --seed 42                    RNG seed for reproducible runs; -1 = random

Dependencies: stdlib only (urllib, json, time, random, argparse, math, sys).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TICK_SIZE = 0.25           # NQ minimum price increment
NQ_START  = 19_483.50      # Starting mid-price
NQ_LO     = 19_400.00      # Hard floor (keeps price realistic)
NQ_HI     = 19_560.00      # Hard ceiling

SESSION_ID = "demo-loop-2026-04-14"

# All 8 scoring categories the engine knows about
ALL_CATEGORIES = [
    "absorption",
    "exhaustion",
    "imbalance",
    "delta",
    "auction",
    "volume",
    "trap",
    "ml_context",
]

# Signal narratives cycle round-robin so the feed looks varied
NARRATIVES = [
    "ABSORBED @VAH",
    "EXHAUSTED @LVN",
    "TRAPPED @19478.00",
    "REVERSAL @POC",
    "ICEBERG @19482.25",
    "SWEEP @HVN",
    "DELTA FLIP @19490.00",
    "REJECTION @HOD",
    "STACKED IMBALANCE @19475.50",
    "STOP RUN @LOD",
]

GEX_REGIMES = ["POS_GAMMA", "NEUTRAL", "NEG_GAMMA"]

# ---------------------------------------------------------------------------
# Tiny HTTP helper — no external deps
# ---------------------------------------------------------------------------

def post(base_url: str, payload: dict) -> bool:
    """POST payload to /api/live/test-broadcast.

    Returns True on 2xx, False on any error (logs a one-line warning).
    Never raises — caller loop continues regardless.
    """
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url}/api/live/test-broadcast",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        # Read response body for 422 (schema rejection) to surface actual error detail.
        try:
            body = exc.read().decode(errors="replace")[:300]
        except Exception:  # noqa: BLE001
            body = ""
        print(f"\n[WARN] HTTP {exc.code} {exc.reason} — {body}",
              flush=True)
        return False
    except urllib.error.URLError as exc:
        print(f"\n[WARN] HTTP error: {exc.reason} — backend down? retrying next tick",
              flush=True)
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"\n[WARN] Unexpected error: {exc}", flush=True)
        return False


# ---------------------------------------------------------------------------
# Price model — smoothed random walk bounded to NQ range
# ---------------------------------------------------------------------------

class PriceModel:
    """Autocorrelated Gaussian random walk for NQ price ticks.

    Each call to .tick() advances by a small normally-distributed step.
    Price is clamped to [NQ_LO, NQ_HI] with a soft-wall reflection near bounds
    so it never sticks at the edges.
    """

    def __init__(self, start: float = NQ_START) -> None:
        self.price = start
        self._drift = 0.0      # autocorrelated component (mean-reversion tendency)

    def tick(self) -> float:
        """Advance price by one tick, return new price."""
        # Soft mean-reversion push toward center when near bounds
        mid = (NQ_LO + NQ_HI) / 2.0
        reversion = (mid - self.price) * 0.002   # gentle pull back to center

        # Autocorrelated noise: drift decays 80% per tick + new shock
        self._drift = self._drift * 0.80 + random.gauss(0, 0.25)
        raw = self.price + self._drift + reversion

        # Reflect off hard walls
        if raw < NQ_LO:
            raw = NQ_LO + (NQ_LO - raw)
            self._drift = abs(self._drift)  # reverse drift
        elif raw > NQ_HI:
            raw = NQ_HI - (raw - NQ_HI)
            self._drift = -abs(self._drift)

        # Snap to nearest tick
        self.price = round(round(raw / TICK_SIZE) * TICK_SIZE, 2)
        return self.price


# ---------------------------------------------------------------------------
# Score model — smooth oscillator with TYPE_A spike logic
# ---------------------------------------------------------------------------

class ScoreModel:
    """Smoothly oscillating confluence score (30-95) with TYPE_A spikes.

    score = smoothed base + sine wave component so the dashboard KPI card
    never looks like white noise.
    """

    def __init__(self) -> None:
        self.score = 55.0
        self._target = 55.0
        self._phase  = 0.0          # sine oscillation phase (radians)
        self._spike_until = 0.0     # epoch time when spike expires
        self._spike_value = 0.0
        self._kronos_bias = 60.0
        self._kronos_dir  = "NEUTRAL"
        self._kronos_next_update = 0.0
        self._gex_regime = "NEUTRAL"
        self.last_signal_tier: str = ""  # updated whenever a signal fires

    def apply_type_a_spike(self) -> None:
        """Triggered when a TYPE_A signal fires — boosts score to 85-95."""
        self._spike_value = random.uniform(85.0, 95.0)
        self._spike_until = time.time() + 10.0

    def update(self) -> None:
        """Advance internal state — call once per tick."""
        self._phase += 0.12   # ~52-tick period (≈ 52s at 1s base rate)
        # Slow random walk of the target score
        self._target += random.gauss(0, 0.4)
        self._target = max(32.0, min(88.0, self._target))
        # Smooth toward target
        self.score += (self._target - self.score) * 0.12
        # Add sine ripple
        self.score += math.sin(self._phase) * 3.5
        self.score = max(28.0, min(92.0, self.score))

        # Override if spike is active
        if time.time() < self._spike_until:
            elapsed = self._spike_until - time.time()
            decay = elapsed / 10.0              # decays linearly to 0 over 10s
            self.score = self._spike_value * decay + self.score * (1 - decay)

        # Kronos update every 15-20s
        now = time.time()
        if now >= self._kronos_next_update:
            self._kronos_bias = random.uniform(35.0, 85.0)
            self._kronos_dir  = random.choice(["LONG", "SHORT", "NEUTRAL"])
            self._gex_regime  = random.choices(
                GEX_REGIMES, weights=[0.50, 0.35, 0.15]
            )[0]
            self._kronos_next_update = now + random.uniform(15, 20)

    def tier(self) -> str:
        s = self.score
        if s >= 80:
            return "TYPE_A"
        if s >= 60:
            return "TYPE_B"
        if s >= 40:
            return "TYPE_C"
        return "QUIET"

    def direction(self) -> int:
        """Derive directional bias from Kronos direction."""
        return {"LONG": 1, "SHORT": -1, "NEUTRAL": 0}.get(self._kronos_dir, 0)

    def category_scores(self) -> dict[str, float]:
        """8 correlated category scores that loosely track total_score."""
        base = self.score
        return {
            "absorption":  min(100, max(0, base * random.uniform(0.85, 1.15))),
            "exhaustion":  min(100, max(0, base * random.uniform(0.75, 1.10))),
            "imbalance":   min(100, max(0, base * random.uniform(0.70, 1.05))),
            "delta":       min(100, max(0, base * random.uniform(0.65, 1.10))),
            "auction":     min(100, max(0, base * random.uniform(0.60, 1.00))),
            "volume":      min(100, max(0, base * random.uniform(0.60, 1.05))),
            "trap":        min(100, max(0, base * random.uniform(0.50, 0.95))),
            "ml_context":  min(100, max(0, base * random.uniform(0.40, 0.90))),
        }

    def categories_firing(self, tier: str) -> list[str]:
        """Return a subset of categories that are 'firing' for this tier."""
        n = {"TYPE_A": 7, "TYPE_B": 5, "TYPE_C": 3}.get(tier, 1)
        return random.sample(ALL_CATEGORIES, k=min(n, len(ALL_CATEGORIES)))


# ---------------------------------------------------------------------------
# Bar builder — footprint levels with realistic volume distribution
# ---------------------------------------------------------------------------

def build_bar(
    session_id: str,
    bar_index: int,
    bar_open: float,
    bar_close: float,
    bar_high: float,
    bar_low: float,
    bar_ts: float,
    running_delta: int,
) -> dict:
    """Construct a LiveBarMessage payload with 30-row footprint ladder."""

    center = (bar_high + bar_low) / 2.0
    center_tick = int(round(center / TICK_SIZE))

    # Determine if this bar is "one-sided" (30% of bars are aggressively biased)
    one_sided = random.random() < 0.30
    bias_side = random.choice(["ask", "bid"])  # which side is heavy

    # POC sits near the midpoint of the bar body (biased toward close)
    poc_offset = random.randint(-3, 3)
    poc_tick   = center_tick + poc_offset
    poc_price  = round(poc_tick * TICK_SIZE, 2)

    total_vol  = random.randint(1500, 3500)
    # 31 rows: offsets -15 … +15 (inclusive), Gaussian weight centred at row 15
    NUM_ROWS = 31
    row_weights = [
        math.exp(-0.5 * ((i - 15) / 6.0) ** 2) for i in range(NUM_ROWS)
    ]
    w_sum = sum(row_weights)

    levels: dict[str, dict] = {}
    cumulative_bid = 0
    cumulative_ask = 0

    for i, offset in enumerate(range(-15, 16)):  # 31 iterations, matches NUM_ROWS
        tick = center_tick + offset
        weight = row_weights[i] / w_sum
        row_vol = max(1, int(total_vol * weight * random.uniform(0.7, 1.3)))

        if tick == poc_tick:
            # POC row gets extra volume
            row_vol = int(row_vol * random.uniform(1.8, 2.8))

        if one_sided and bias_side == "ask":
            # Aggressive sellers: ask_vol >> bid_vol
            factor = random.uniform(2.0, 4.0)
            ask_vol = int(row_vol * factor / (1 + factor))
            bid_vol = row_vol - ask_vol
        elif one_sided and bias_side == "bid":
            # Aggressive buyers: bid_vol >> ask_vol
            factor = random.uniform(2.0, 4.0)
            bid_vol = int(row_vol * factor / (1 + factor))
            ask_vol = row_vol - bid_vol
        else:
            # Balanced — slight random skew
            split = random.uniform(0.38, 0.62)
            bid_vol = max(1, int(row_vol * split))
            ask_vol = max(1, row_vol - bid_vol)

        levels[str(tick)] = {"bid_vol": bid_vol, "ask_vol": ask_vol}
        cumulative_bid += bid_vol
        cumulative_ask += ask_vol

    bar_delta = cumulative_ask - cumulative_bid
    bar_range = bar_high - bar_low

    bar_payload = {
        "session_id": session_id,
        "bar_index":  bar_index,
        "ts":         bar_ts,
        "open":       bar_open,
        "high":       bar_high,
        "low":        bar_low,
        "close":      bar_close,
        "total_vol":  total_vol,
        "bar_delta":  bar_delta,
        "cvd":        running_delta + bar_delta,
        "poc_price":  poc_price,
        "bar_range":  round(bar_range, 2),
        "running_delta": running_delta,
        "max_delta":  abs(bar_delta) + random.randint(10, 60),
        "min_delta":  -(abs(bar_delta) + random.randint(10, 60)),
        "levels":     levels,
    }
    return {
        "type":       "bar",
        "session_id": session_id,
        "bar_index":  bar_index,
        "bar":        bar_payload,
    }


# ---------------------------------------------------------------------------
# Signal scheduler — Poisson-like inter-arrival for each tier
# ---------------------------------------------------------------------------

class SignalScheduler:
    """Tracks when the next signal of each tier should fire."""

    def __init__(self) -> None:
        now = time.time()
        # Mean inter-arrival (seconds) for each tier
        self._next: dict[str, float] = {
            "TYPE_C": now + random.uniform(8, 15),
            "TYPE_B": now + random.uniform(30, 60),
            "TYPE_A": now + random.uniform(90, 180),
        }
        self._narrative_idx = 0

    def due(self) -> list[str]:
        """Return list of tier strings whose timers have fired."""
        now = time.time()
        fired = []
        for tier, t in self._next.items():
            if now >= t:
                fired.append(tier)
        return fired

    def reset(self, tier: str) -> None:
        """Schedule next occurrence for the given tier."""
        intervals = {
            "TYPE_C": (8, 15),
            "TYPE_B": (30, 60),
            "TYPE_A": (90, 180),
        }
        lo, hi = intervals[tier]
        self._next[tier] = time.time() + random.uniform(lo, hi)

    def next_narrative(self) -> str:
        """Round-robin through NARRATIVES list."""
        n = NARRATIVES[self._narrative_idx % len(NARRATIVES)]
        self._narrative_idx += 1
        return n


# ---------------------------------------------------------------------------
# Counters for summary report on exit
# ---------------------------------------------------------------------------

class Stats:
    def __init__(self) -> None:
        self.ticks     = 0
        self.bars      = 0
        self.signals   = 0
        self.scores    = 0
        self.tape      = 0
        self.status    = 0
        self.errors    = 0
        self.start     = time.time()

    def elapsed(self) -> float:
        return time.time() - self.start

    def summary(self) -> str:
        t = self.elapsed()
        return (
            f"\n{'='*56}\n"
            f"  DEEP6 Demo Broadcaster — session summary\n"
            f"{'='*56}\n"
            f"  Duration : {t:.1f}s\n"
            f"  Ticks    : {self.ticks}\n"
            f"  Status   : {self.status}\n"
            f"  Bars     : {self.bars}\n"
            f"  Tape     : {self.tape}\n"
            f"  Scores   : {self.scores}\n"
            f"  Signals  : {self.signals}\n"
            f"  Errors   : {self.errors}\n"
            f"{'='*56}"
        )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Looping DEEP6 demo broadcaster — streams NQ market activity."
    )
    parser.add_argument("--url",      default="http://localhost:8000",
                        help="Backend base URL (default: http://localhost:8000)")
    parser.add_argument("--rate",     type=float, default=1.0,
                        help="Speed multiplier (2.0 = 2× faster, default: 1.0)")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Seconds to run; 0 = run forever (default: 0)")
    parser.add_argument("--seed",     type=int, default=42,
                        help="RNG seed; -1 = random (default: 42)")
    args = parser.parse_args()

    if args.seed >= 0:
        random.seed(args.seed)

    # Effective tick period (seconds) — divided by rate multiplier
    tick_period = 1.0 / max(0.01, args.rate)

    price_model  = PriceModel(NQ_START)
    score_model  = ScoreModel()
    scheduler    = SignalScheduler()
    stats        = Stats()

    # Session start — set once, included in every status message
    session_start_ts = time.time()

    # Bar state
    bar_index    = 0
    bar_open     = NQ_START
    bar_high     = NQ_START
    bar_low      = NQ_START
    bar_ts       = time.time()
    running_delta = 0

    # Interval counters (elapsed ticks since last event)
    ticks_since_bar   = 0
    ticks_since_tape  = 0
    ticks_since_score = 0

    # Intervals (in ticks) for each recurring event
    BAR_INTERVAL   = 3   # fire a bar every 3 ticks
    TAPE_INTERVAL  = 2   # fire a tape print every 2 ticks
    SCORE_INTERVAL = 5   # fire a score update every 5 ticks

    pnl   = round(random.uniform(-500, 1200), 2)

    print(f"DEEP6 Demo Broadcaster starting — {args.url}")
    print(f"  rate={args.rate}x  duration={'∞' if args.duration == 0 else f'{args.duration}s'}  "
          f"seed={args.seed}  tick={tick_period:.2f}s")
    print("  Press Ctrl-C to stop.\n", flush=True)

    end_time = (time.time() + args.duration) if args.duration > 0 else None
    last_newline_tick = 0   # for readability newlines every 30 ticks

    try:
        while True:
            tick_start = time.time()

            # --- Check duration limit ---
            if end_time and tick_start >= end_time:
                print("\n[INFO] Duration limit reached, stopping.")
                break

            # --- Advance price model ---
            price = price_model.tick()
            score_model.update()

            # --- Update bar high/low ---
            bar_high = max(bar_high, price)
            bar_low  = min(bar_low, price)

            stats.ticks += 1
            ticks_since_bar   += 1
            ticks_since_tape  += 1
            ticks_since_score += 1

            # ---------------------------------------------------------------
            # 1. STATUS message — every tick (keeps connected indicator green)
            #    Now includes full observability fields so the dashboard can
            #    display session elapsed time, bar/signal counters, and uptime.
            # ---------------------------------------------------------------
            pnl += random.gauss(0, 1.5)          # P&L drifts realistically
            pnl  = round(pnl, 2)
            ok = post(args.url, {
                "type":                    "status",
                "connected":               True,
                "pnl":                     pnl,
                "circuit_breaker_active":  False,
                "feed_stale":              False,
                "ts":                      tick_start,
                # --- observability fields (Phase 11.3-r3) ---
                "session_start_ts":        session_start_ts,
                "bars_received":           stats.bars,
                "signals_fired":           stats.signals,
                "last_signal_tier":        score_model.last_signal_tier,
                "uptime_seconds":          int(tick_start - session_start_ts),
                "active_clients":          0,  # demo doesn't know client count
            })
            if ok:
                stats.status += 1
            else:
                stats.errors += 1

            # ---------------------------------------------------------------
            # 2. TAPE (trade print) — every TAPE_INTERVAL ticks
            # ---------------------------------------------------------------
            if ticks_since_tape >= TAPE_INTERVAL:
                ticks_since_tape = 0
                tape_price = price + random.choice([-0.25, 0, 0.25])
                tape_size  = random.randint(1, 200)

                # Weight side by bar delta direction: positive delta = more ASK prints
                bar_delta_so_far = running_delta
                ask_weight = 0.60 if bar_delta_so_far > 0 else 0.40
                tape_side = random.choices(["ASK", "BID"], weights=[ask_weight, 1 - ask_weight])[0]

                # Marker logic (20% of prints get a marker)
                tape_marker = ""
                if random.random() < 0.20:
                    if tape_size >= 100:
                        tape_marker = "SWEEP"
                    elif random.random() < 0.40:
                        tape_marker = "ICEBERG"
                    else:
                        tape_marker = "KRONOS"

                ok = post(args.url, {
                    "type":  "tape",
                    "event": {
                        "ts":     tick_start,
                        "price":  tape_price,
                        "size":   tape_size,
                        "side":   tape_side,
                        "marker": tape_marker,
                    },
                })
                if ok:
                    stats.tape += 1
                else:
                    stats.errors += 1

            # ---------------------------------------------------------------
            # 3. BAR — every BAR_INTERVAL ticks
            # ---------------------------------------------------------------
            if ticks_since_bar >= BAR_INTERVAL:
                ticks_since_bar = 0
                bar_close = price
                bar_payload = build_bar(
                    session_id=SESSION_ID,
                    bar_index=bar_index,
                    bar_open=bar_open,
                    bar_close=bar_close,
                    bar_high=bar_high,
                    bar_low=bar_low,
                    bar_ts=tick_start,
                    running_delta=running_delta,
                )
                # Update running delta from bar payload
                running_delta = bar_payload["bar"]["cvd"]

                ok = post(args.url, bar_payload)
                if ok:
                    stats.bars += 1
                else:
                    stats.errors += 1

                # Advance to next bar
                bar_index += 1
                bar_open  = price
                bar_high  = price
                bar_low   = price
                bar_ts    = tick_start

            # ---------------------------------------------------------------
            # 4. SCORE — every SCORE_INTERVAL ticks
            # ---------------------------------------------------------------
            if ticks_since_score >= SCORE_INTERVAL:
                ticks_since_score = 0
                tier = score_model.tier()
                ok = post(args.url, {
                    "type":              "score",
                    "total_score":       round(score_model.score, 1),
                    "tier":              tier,
                    "direction":         score_model.direction(),
                    "categories_firing": score_model.categories_firing(tier),
                    "category_scores":   {k: round(v, 1) for k, v in
                                         score_model.category_scores().items()},
                    "kronos_bias":       round(score_model._kronos_bias, 1),
                    "kronos_direction":  score_model._kronos_dir,
                    "gex_regime":        score_model._gex_regime,
                })
                if ok:
                    stats.scores += 1
                else:
                    stats.errors += 1

            # ---------------------------------------------------------------
            # 5. SIGNALS — Poisson-like cadence per tier
            # ---------------------------------------------------------------
            for tier in scheduler.due():
                scheduler.reset(tier)
                sig_score = {
                    "TYPE_A": random.uniform(82, 97),
                    "TYPE_B": random.uniform(62, 79),
                    "TYPE_C": random.uniform(40, 61),
                }[tier]
                cat_count = {"TYPE_A": 7, "TYPE_B": 5, "TYPE_C": 3}[tier]
                cats = score_model.categories_firing(tier)
                direction = score_model.direction() or random.choice([-1, 1])

                ok = post(args.url, {
                    "type":  "signal",
                    "event": {
                        "ts":                   tick_start,
                        "bar_index_in_session": bar_index,
                        "total_score":          round(sig_score, 1),
                        "tier":                 tier,
                        "direction":            direction,
                        "engine_agreement":     round(random.uniform(0.50, 0.95), 2),
                        "category_count":       cat_count,
                        "categories_firing":    cats,
                        "gex_regime":           score_model._gex_regime,
                        "kronos_bias":          round(score_model._kronos_bias, 1),
                    },
                    "narrative": scheduler.next_narrative(),
                })
                if ok:
                    stats.signals += 1
                    score_model.last_signal_tier = tier  # track for status messages
                    if tier == "TYPE_A":
                        score_model.apply_type_a_spike()
                else:
                    stats.errors += 1

            # ---------------------------------------------------------------
            # 6. Console status line
            # ---------------------------------------------------------------
            price_dir = "▲" if price_model._drift > 0 else "▼"
            msg = (f"[{time.strftime('%H:%M:%S')}] "
                   f"tick#{stats.ticks:<5d} "
                   f"price {price:>10.2f} {price_dir}  "
                   f"score {score_model.score:>5.1f}  "
                   f"bars={stats.bars:<4d} "
                   f"sigs={stats.signals:<4d} "
                   f"uptime={int(tick_start - session_start_ts)}s")
            print(msg, end="  ", flush=True)

            if stats.ticks % 30 == 0:
                print()   # newline every 30 ticks for readability
                last_newline_tick = stats.ticks

            # ---------------------------------------------------------------
            # 7. Sleep to maintain tick period (account for processing time)
            # ---------------------------------------------------------------
            elapsed = time.time() - tick_start
            sleep_time = tick_period - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass

    print(stats.summary())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
