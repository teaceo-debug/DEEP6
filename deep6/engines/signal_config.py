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


@dataclass(frozen=True)
class AuctionConfig:
    """Configuration for AuctionEngine — all tunable thresholds.

    Per D-01: defaults match original hardcoded values in auction.py.
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    """
    # AUCT-03: Poor high/low — single-print or low-volume extreme
    poor_extreme_vol_ratio: float = 0.3    # Max vol/avg_vol for poor high/low
    # AUCT-04: Volume void — LVN gap within bar
    void_vol_ratio: float = 0.05           # Max vol/max_vol for volume void level
    void_min_levels: int = 3               # Min thin levels for void signal
    # AUCT-05: Market sweep — rapid traversal with increasing volume
    sweep_vol_increase: float = 1.5        # Min second-half/first-half vol ratio for sweep
    sweep_min_levels: int = 10             # Min price levels for sweep detection
    # E9 FSM thresholds
    balance_count_threshold: int = 3       # Bars before BALANCED state
    breakout_range_threshold: float = 2.0  # Range multiplier for BREAKOUT vs EXPLORING


@dataclass(frozen=True)
class POCConfig:
    """Configuration for POCEngine — all tunable thresholds.

    Per D-01: extract from hardcoded constructor defaults.
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    """
    va_pct: float = 0.70                    # POC-01..08 Value Area coverage fraction
    poc_gap_ticks: int = 8                  # POC-04 gap threshold in ticks
    continuous_streak_min: int = 3          # POC-03 consecutive bars to fire
    extreme_top_pct: float = 0.15           # POC-02 top-of-range boundary fraction
    extreme_bot_pct: float = 0.15           # POC-02 bottom-of-range boundary fraction
    bullish_poc_position_max: float = 0.35  # POC-08 POC position (low) for bullish
    bearish_poc_position_min: float = 0.65  # POC-08 POC position (high) for bearish
    migration_window: int = 5               # VPRO-08 bars for velocity calculation


@dataclass(frozen=True)
class VolumeProfileConfig:
    """Configuration for SessionProfile — all tunable thresholds.

    Per D-01/D-02: LVN=30%, HVN=170% per requirements; scoring weights per VPRO-05.
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    """
    lvn_threshold: float = 0.30    # VPRO-02 LVN: bins < 30% of session average
    hvn_threshold: float = 1.70    # VPRO-03 HVN: bins > 170% of session average
    min_zone_ticks: int = 2        # VPRO-01 minimum zone width in ticks
    max_zones: int = 80            # cap on simultaneously active zones
    w_type: float = 0.35           # VPRO-05 zone type weight
    w_recency: float = 0.25        # VPRO-05 recency weight
    w_touches: float = 0.25        # VPRO-05 touch count weight
    w_defense: float = 0.15        # VPRO-05 defense weight
    zone_decay_rate: float = 0.005  # per-bar score decay (~140 bar half-life)
    session_decay_weight: float = 0.70  # VPRO-07 prior session bins decay factor (0.7 = 30% fade)


@dataclass(frozen=True)
class ScorerConfig:
    """Configuration for score_bar() — all scoring thresholds.

    Per D-11: centralizes scorer thresholds for Phase 7 vectorbt sweeps.
    frozen=True prevents mutation between sweep trials.
    """
    # Tier thresholds (SCOR-04)
    type_a_min: float = 80.0
    type_b_min: float = 65.0
    type_c_min: float = 50.0
    min_categories: int = 3

    # Confluence multiplier threshold (SCOR-02)
    confluence_threshold: int = 5     # cat_count >= this triggers 1.25x multiplier

    # Zone bonus thresholds (SCOR-03)
    zone_high_min: float = 50.0       # zone.score >= this → +8.0 bonus
    zone_mid_min: float = 30.0        # zone.score >= this → +6.0 bonus
    zone_high_bonus: float = 8.0
    zone_mid_bonus: float = 6.0
    zone_near_bonus: float = 4.0      # within zone_near_ticks of zone edge
    zone_near_ticks: float = 0.50     # NQ tick proximity threshold


@dataclass(frozen=True)
class TrapConfig:
    """Configuration for TrapEngine — TRAP-02..05 thresholds.

    TRAP-01 (INVERSE_TRAP) lives in imbalance.py and uses ImbalanceConfig.
    Phase 7 vectorbt sweeps will vary these to find optimal values.
    Per T-02-01: frozen=True prevents mutation after creation.
    """
    # TRAP-02: Delta trap — prior bar must have strong directional delta
    trap_delta_ratio: float = 0.25       # Min |delta|/vol for prior bar to qualify

    # TRAP-03: False breakout trap — volume must exceed this multiple of vol_ema
    false_breakout_vol_mult: float = 1.8  # Volume multiple above vol_ema

    # TRAP-04: High volume rejection trap
    hvr_vol_mult: float = 2.5            # Volume multiple above vol_ema
    hvr_wick_min: float = 0.35           # Min wick volume fraction

    # TRAP-05: CVD trap — slope of CVD window must exceed this to qualify as trending
    cvd_trap_lookback: int = 8           # Bars for CVD slope calculation
    cvd_trap_min_slope: float = 0.05     # Min |slope| to qualify as trending CVD


@dataclass(frozen=True)
class VolPatternConfig:
    """Configuration for VolPatternEngine — VOLP-01..06 thresholds.

    Phase 7 vectorbt sweeps will vary these to find optimal values.
    Per T-02-01: frozen=True prevents mutation after creation.
    """
    # VOLP-01: Volume sequencing — each bar >= prior * this ratio
    vol_seq_step_ratio: float = 1.15    # Each bar >= prior * this ratio
    vol_seq_min_bars: int = 3           # Min bars in sequence

    # VOLP-02: Volume bubble — single level vol > avg_level_vol * this
    bubble_mult: float = 4.0            # Level vol > avg_level_vol * this

    # VOLP-03: Volume surge — bar vol > vol_ema * this
    surge_mult: float = 3.0             # Bar vol > vol_ema * this
    surge_delta_min_ratio: float = 0.15 # Min |delta|/vol for directional surge

    # VOLP-04: POC momentum wave — consecutive bars of POC migration
    poc_wave_bars: int = 3              # Consecutive bars of POC migration

    # VOLP-05: Delta velocity spike
    delta_velocity_mult: float = 0.6   # |velocity| > vol_ema * this

    # VOLP-06: Big delta per level — min |net_delta| at single level (contracts)
    big_delta_level_threshold: int = 80  # Min |net_delta| at single level (contracts)


@dataclass(frozen=True)
class TrespassConfig:
    """Configuration for TrespassEngine — E2 weighted DOM queue imbalance.

    Per D-01: Weight decay is 1/(i+1) — computed at engine init, not configurable.
    Per D-02: Heuristic thresholds until logistic regression model is trained (Phase 7).
    Per T-02-01: frozen=True prevents mutation after creation.
    """
    trespass_depth: int = 10              # Top N levels to consider (of 40)
    bull_ratio_threshold: float = 1.2    # imbalance_ratio > this = bullish
    bear_ratio_threshold: float = 0.8    # imbalance_ratio < this = bearish


@dataclass(frozen=True)
class CounterSpoofConfig:
    """Configuration for CounterSpoofEngine — E3 Wasserstein-1 DOM distribution monitor.

    Per D-04: E3 samples every 100ms, NOT every callback.
    Per D-05: W1 spike > w1_anomaly_sigma * std from rolling mean = anomaly.
    Per D-06: Large order cancel: level > spoof_large_order drops to < spoof_cancel_threshold
              within spoof_cancel_window_ms without a trade = potential spoof.
    Per D-07: Alert-only — informational, not a trade signal.
    Per T-02-01: frozen=True prevents mutation after creation.
    """
    spoof_history_len: int = 20           # Max snapshots in rolling window
    spoof_large_order: float = 50.0       # Min size to track as "large" (contracts)
    spoof_cancel_threshold: float = 10.0  # Size drop to < this = potential cancel
    spoof_cancel_window_ms: float = 200.0  # Time window for cancel detection (ms)
    w1_anomaly_sigma: float = 3.0         # Standard deviations for W1 spike
    w1_min_samples: int = 5               # Min W1 history before anomaly fires


@dataclass(frozen=True)
class GexConfig:
    """Configuration for GexEngine — all tunable thresholds.

    Per D-04: staleness at 15 min default (GEX-06).
    Phase 7 vectorbt sweeps can vary near_wall_pct and gex_normalize_divisor.
    """
    staleness_seconds: float = 900.0     # GEX-06 stale threshold (15 minutes)
    underlying: str = "QQQ"              # GEX-01 proxy ticker for NQ (QQQ tracks NDX)
    near_wall_pct: float = 0.005         # GEX-05 within 0.5% of wall = "near"
    nq_to_qqq_divisor: float = 40.0     # NQ price ÷ 40 ≈ QQQ price
    gex_normalize_divisor: float = 1e9  # GEX-05 strength normalization divisor


@dataclass(frozen=True)
class KronosConfig:
    """Configuration for KronosSubprocessBridge (E10 bias engine).

    Kronos-small runs in a dedicated subprocess. These fields control inference
    cadence, confidence decay, and model selection.

    Per D-07: all fields correspond to KronosEngine kwargs; defaults are unchanged
    from the original implementation.
    Per T-02-01: frozen=True prevents mutation after creation.
    """
    # Model identity
    model_name: str = "NeoQuasar/Kronos-small"
    tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base"

    # KRON-02: Inference cadence — re-infer every N bars
    inference_interval: int = 5

    # KRON-02: Stochastic sampling — 20 samples for confidence scoring
    num_samples: int = 20

    # KRON-01: Context window — use last N bars for inference
    lookback: int = 100

    # KRON-01: Prediction horizon — predict N bars ahead
    pred_len: int = 5

    # KRON-03: Confidence decay — 0.95/bar between inferences
    decay_factor: float = 0.95

    # Device selection: "auto" probes mps → cuda → cpu; or explicit "cpu"/"mps"/"cuda"
    device: str = "auto"
