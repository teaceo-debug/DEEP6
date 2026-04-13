"""Signal configuration dataclasses for absorption, exhaustion, imbalance, and delta engines.

All tunable thresholds live here so Phase 7 vectorbt parameter sweeps
can inject custom config objects without touching engine logic.

Per D-01: Current defaults are kept exactly as-is (no hand-tuning until Phase 7).
Per D-02: No magic numbers in engine function bodies — all come from config.
Per T-02-01: frozen=True prevents mutation after creation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AbsorptionConfig:
    """Configuration for detect_absorption() — all tunable thresholds.

    Fields correspond to the original detect_absorption() kwargs.
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    """
    # ABS-01: Classic absorption — wick volume + balanced delta
    absorb_wick_min: float = 30.0    # Min wick volume % of total for classic
    absorb_delta_max: float = 0.12   # Max |delta|/volume ratio (balanced = absorption)

    # ABS-02: Passive absorption — volume concentrates at extreme
    passive_extreme_pct: float = 0.20  # Top/bottom fraction of range to check
    passive_vol_pct: float = 0.60      # Min fraction of total vol in extreme zone

    # ABS-03: Stopping volume — POC in wick + high absolute volume
    stop_vol_mult: float = 2.0   # Volume must exceed this × vol_ema

    # ABS-04: Effort vs result — high volume + narrow range
    evr_vol_mult: float = 1.5    # Volume must exceed this × vol_ema
    evr_range_cap: float = 0.30  # Max bar range as fraction of ATR

    # ABS-07 / D-05: VA extremes conviction bonus — absorption near VAH/VAL
    va_extreme_ticks: int = 2          # Ticks within VAH/VAL to qualify as "at VA extreme"
    va_extreme_strength_bonus: float = 0.15  # Additive strength bonus when at VA extreme

    # ABS-06 / D-06 / D-07: Absorption confirmation — defense window tracking
    confirmation_window_bars: int = 3    # Bars to watch for zone defense after signal fires
    confirmation_score_bonus: float = 2.0  # Score upgrade when defense confirmed (for scorer.py)
    confirmation_breach_ticks: int = 2   # Max ticks price can breach zone before defense fails


@dataclass(frozen=True)
class ExhaustionConfig:
    """Configuration for detect_exhaustion() — all tunable thresholds.

    Fields correspond to the original detect_exhaustion() kwargs plus
    the new delta trajectory gate parameters (EXH-07).
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    """
    # EXH-03: Thin print — fast move through price level
    thin_pct: float = 0.05   # Max volume fraction of bar max for thin print

    # EXH-04: Fat print — strong acceptance level
    fat_mult: float = 2.0    # Min volume multiple of bar average

    # EXH-02: Exhaustion print — single-side volume at extreme
    exhaust_wick_min: float = 35.0  # Min wick volume % for exhaustion print

    # EXH-06: Bid/ask fade — comparing extremes to prior bar
    fade_threshold: float = 0.60  # Ask/bid fade ratio threshold

    # EXH-08 / D-11: Cooldown — suppress same sub-type after firing
    cooldown_bars: int = 5   # Bars to suppress same sub-type

    # EXH-07 / D-08: Delta trajectory gate — universal filter for exhaustion variants 2-6
    delta_gate_min_ratio: float = 0.10  # Min |delta|/volume for gate to activate
    delta_gate_enabled: bool = True     # Master switch for the delta trajectory gate


@dataclass(frozen=True)
class ImbalanceConfig:
    """Configuration for detect_imbalances() — all tunable thresholds.

    Per D-01: defaults match original hardcoded values in imbalance.py kwargs.
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    """
    # IMB-01: Single imbalance — diagonal ask[P] vs bid[P-1] ratio
    ratio_threshold: float = 3.0          # Min ask[P]/bid[P-1] for single imbalance
    # IMB-06: Oversized — ratio at which SINGLE is promoted to OVERSIZED
    oversized_threshold: float = 10.0     # Ratio for oversized classification
    # IMB-03: Stacked — consecutive levels for T1/T2/T3 tiers
    stacked_t1: int = 3                   # Consecutive levels for T1
    stacked_t2: int = 5                   # Consecutive levels for T2
    stacked_t3: int = 7                   # Consecutive levels for T3
    # IMB-02: Multiple — same price imbalance accumulation
    multiple_min_count: int = 3           # Min imbalances at same price tick for MULTIPLE
    # IMB-07: Consecutive — same level across multiple bars
    consecutive_min_bars: int = 2         # Min bars for consecutive detection (currently 2=prior+current)
    # IMB-05: Inverse trap
    inverse_min_imbalances: int = 3       # Min opposite-dir imbalances to qualify as trap
    # Stacked run gap tolerance
    stacked_gap_tolerance: int = 2        # Allow N tick gap in stacked runs


@dataclass(frozen=True)
class DeltaConfig:
    """Configuration for DeltaEngine — all tunable thresholds.

    Per D-01: defaults match original hardcoded values in delta.py.
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    """
    lookback: int = 20                         # Rolling window size for histories
    # DELT-02: Tail — delta at extreme
    tail_threshold: float = 0.95               # Delta ratio (|delta|/vol) for tail signal
    # DELT-04: Divergence — price/CVD lookback
    divergence_lookback: int = 5               # Bars for divergence check
    # DELT-06: Trap — prior bar delta ratio threshold
    trap_delta_ratio: float = 0.3              # Min |delta|/vol for trap qualification
    # DELT-08: Slingshot — compressed then explosive
    slingshot_quiet_ratio: float = 0.1         # Max |delta|/vol for compressed bar
    slingshot_explosive_ratio: float = 0.4     # Min |delta|/vol for explosive bar
    slingshot_quiet_bars: int = 2              # Min quiet bars (out of 3) before explosion
    # DELT-10: CVD multi-bar divergence
    cvd_divergence_min_bars: int = 10          # Min bars for CVD regression
    cvd_slope_divergence_factor: float = 0.3   # Slope divergence threshold multiplier
    # DELT-11: Velocity — CVD acceleration
    velocity_accel_ratio: float = 0.3          # Min |accel|/vol for velocity signal
    # DELT-07: Sweep — rapid delta across multiple levels
    sweep_min_levels: int = 5                  # Min price levels in bar for sweep detection
    sweep_vol_increase_ratio: float = 1.5      # Vol increase ratio (second half / first half)
    # DELT-03: Reversal approximation — bar-level delta/direction mismatch
    reversal_min_delta_ratio: float = 0.15     # Min |delta|/vol for reversal signal to fire
