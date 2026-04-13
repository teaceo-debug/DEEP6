"""Signal configuration dataclasses for absorption and exhaustion engines.

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
