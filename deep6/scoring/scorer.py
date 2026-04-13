"""Two-layer confluence scorer — SCOR-01..06.

Layer 1: Engine-level agreement ratio (how many engines agree on direction)
Layer 2: Category-level confluence multiplier (how many signal categories agree)

When 5+ categories agree → 1.25× multiplier (SCOR-02)
Zone bonus: zones scoring ≥50 add +6 to +8 points (SCOR-03)

TypeA: absorption/exhaustion + zone confluence + 5+ categories = highest conviction
TypeB: 4+ categories + zone = tradeable
TypeC: 3+ categories = alert only
Quiet: fewer than 3 categories
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from deep6.engines.narrative import NarrativeResult, NarrativeType
from deep6.engines.delta import DeltaSignal
from deep6.engines.auction import AuctionSignal
from deep6.engines.poc import POCSignal
from deep6.engines.volume_profile import VolumeZone, ZoneState
from deep6.engines.gex import GexSignal, GexRegime
from deep6.engines.signal_config import ScorerConfig, AbsorptionConfig


class SignalTier(IntEnum):
    QUIET = 0
    TYPE_C = 1
    TYPE_B = 2
    TYPE_A = 3


@dataclass
class ScorerResult:
    """Output of the two-layer scorer for one bar."""
    total_score: float          # 0-100
    tier: SignalTier
    direction: int              # +1 bull, -1 bear, 0 neutral
    engine_agreement: float     # 0-1 ratio of engines agreeing on direction
    category_count: int         # how many of 8 categories agree
    confluence_mult: float      # 1.0 or 1.25
    zone_bonus: float           # 0, 6, or 8
    narrative: NarrativeType
    label: str                  # human-readable
    categories_firing: list[str] = field(default_factory=list)


# Category weights — how much each category contributes to the base score
# Optimized from backtest analysis (Apr 7-11, 4590 bars):
#   - POC reduced from 7→3: combos with POC systematically underperform
#     (35% win with POC vs 73% without in absorption+trapped combos)
#   - Trapped raised from 10→14: trapped+absorption combo is highest alpha
#   - Delta raised from 10→13: delta agreement is critical quality filter
CATEGORY_WEIGHTS = {
    "absorption": 25.0,    # Highest weight — core alpha
    "exhaustion": 18.0,
    "trapped": 14.0,       # Was 10 — trapped+absorption is highest alpha combo
    "delta": 13.0,         # Was 10 — delta agreement is critical for signal quality
    "imbalance": 12.0,
    "volume_profile": 10.0,
    "auction": 8.0,
    "poc": 3.0,            # Was 7 — POC fires too liberally, adds noise to combos
}


def score_bar(
    narrative: NarrativeResult,
    delta_signals: list[DeltaSignal],
    auction_signals: list[AuctionSignal],
    poc_signals: list[POCSignal],
    active_zones: list[VolumeZone],
    bar_close: float,
    type_a_min: float = 80.0,
    type_b_min: float = 65.0,
    type_c_min: float = 50.0,
    min_categories: int = 3,
    scorer_config: ScorerConfig | None = None,
    abs_config: AbsorptionConfig | None = None,
    bar_delta: int = 0,
    bar_index_in_session: int = -1,
    gex_signal: GexSignal | None = None,
) -> ScorerResult:
    """Score a bar using two-layer confluence.

    D-01: confirmation_score_bonus applied per confirmed_absorptions entry.
    D-02: stacked imbalance dedup uses highest tier only per direction.
    D-11: scorer_config centralizes all thresholds for Phase 7 vectorbt sweeps.

    Optimization findings applied:
    - Delta-direction agreement gate: TYPE_A/B require bar delta to agree with
      signal direction (75% win when agrees vs 33% when disagrees)
    - IB multiplier: signals in first 60 bars (Initial Balance) get 1.15x score
      boost (100% TYPE_A win rate during IB vs 36% outside)
    - TYPE_C minimum categories raised to 4 (was 3) to reduce noise
    - Minimum signal strength gate: narrative strength must be >= 0.3 for TYPE_B/C

    Args:
        narrative: NarrativeResult from narrative cascade
        delta_signals: DeltaSignal list from delta engine
        auction_signals: AuctionSignal list from auction engine
        poc_signals: POCSignal list from POC engine
        active_zones: Active VolumeZones near current price
        bar_close: Current bar close price
        type_a_min: Score threshold for TypeA (default 80) — legacy kwarg
        type_b_min: Score threshold for TypeB (default 65) — legacy kwarg
        type_c_min: Score threshold for TypeC (default 50) — legacy kwarg
        min_categories: Minimum categories for any signal tier — legacy kwarg
        scorer_config: ScorerConfig with all thresholds; takes precedence over legacy kwargs
        abs_config: AbsorptionConfig for confirmation_score_bonus; defaults to AbsorptionConfig()
        bar_delta: Current bar's net delta (positive=buyers, negative=sellers)
        bar_index_in_session: Bar index within RTH session (0=first bar at 9:30)
    """
    # Resolve configs — scorer_config takes precedence over legacy kwargs when provided
    cfg = scorer_config or ScorerConfig(
        type_a_min=type_a_min,
        type_b_min=type_b_min,
        type_c_min=type_c_min,
        min_categories=min_categories,
    )
    _abs_cfg = abs_config or AbsorptionConfig()

    # --- Layer 1: Determine direction from all signals ---
    bull_votes = 0
    bear_votes = 0
    total_votes = 0

    # Count directional votes per category
    categories_bull: set[str] = set()
    categories_bear: set[str] = set()

    # Absorption
    for sig in narrative.absorption:
        total_votes += 1
        if sig.direction > 0:
            bull_votes += 1
            categories_bull.add("absorption")
        elif sig.direction < 0:
            bear_votes += 1
            categories_bear.add("absorption")

    # Exhaustion
    for sig in narrative.exhaustion:
        total_votes += 1
        if sig.direction > 0:
            bull_votes += 1
            categories_bull.add("exhaustion")
        elif sig.direction < 0:
            bear_votes += 1
            categories_bear.add("exhaustion")

    # Imbalance — trapped traders counted separately; stacked dedup uses highest tier (D-02)
    stacked_bull_tier = 0   # 1=T1, 2=T2, 3=T3
    stacked_bear_tier = 0
    for sig in narrative.imbalances:
        if "TRAP" in sig.imb_type.name:
            total_votes += 1
            if sig.direction > 0:
                bull_votes += 1
                categories_bull.add("trapped")
            elif sig.direction < 0:
                bear_votes += 1
                categories_bear.add("trapped")
        elif "STACKED_T3" in sig.imb_type.name:
            if sig.direction > 0:
                stacked_bull_tier = max(stacked_bull_tier, 3)
            elif sig.direction < 0:
                stacked_bear_tier = max(stacked_bear_tier, 3)
        elif "STACKED_T2" in sig.imb_type.name:
            if sig.direction > 0:
                stacked_bull_tier = max(stacked_bull_tier, 2)
            elif sig.direction < 0:
                stacked_bear_tier = max(stacked_bear_tier, 2)
        elif "STACKED_T1" in sig.imb_type.name:
            if sig.direction > 0:
                stacked_bull_tier = max(stacked_bull_tier, 1)
            elif sig.direction < 0:
                stacked_bear_tier = max(stacked_bear_tier, 1)
    # D-02: one imbalance vote per direction — highest tier only
    if stacked_bull_tier > 0:
        total_votes += 1
        bull_votes += 1
        categories_bull.add("imbalance")
    if stacked_bear_tier > 0:
        total_votes += 1
        bear_votes += 1
        categories_bear.add("imbalance")

    # Delta
    for sig in delta_signals:
        if sig.delta_type in (
            sig.delta_type.DIVERGENCE, sig.delta_type.CVD_DIVERGENCE,
            sig.delta_type.SLINGSHOT, sig.delta_type.TRAP, sig.delta_type.FLIP,
        ):
            total_votes += 1
            if sig.direction > 0:
                bull_votes += 1
                categories_bull.add("delta")
            elif sig.direction < 0:
                bear_votes += 1
                categories_bear.add("delta")

    # Auction
    for sig in auction_signals:
        if sig.auction_type in (
            sig.auction_type.FINISHED_AUCTION,
            sig.auction_type.UNFINISHED_BUSINESS,
            sig.auction_type.MARKET_SWEEP,
        ):
            total_votes += 1
            if sig.direction > 0:
                bull_votes += 1
                categories_bull.add("auction")
            elif sig.direction < 0:
                bear_votes += 1
                categories_bear.add("auction")

    # POC
    for sig in poc_signals:
        if sig.poc_type in (
            sig.poc_type.EXTREME_POC_HIGH, sig.poc_type.EXTREME_POC_LOW,
            sig.poc_type.BULLISH_POC, sig.poc_type.BEARISH_POC,
            sig.poc_type.VA_GAP,
        ):
            total_votes += 1
            if sig.direction > 0:
                bull_votes += 1
                categories_bull.add("poc")
            elif sig.direction < 0:
                bear_votes += 1
                categories_bear.add("poc")

    # Determine dominant direction
    if bull_votes > bear_votes:
        direction = +1
        agreement = bull_votes / total_votes if total_votes > 0 else 0
        categories_agreeing = categories_bull
    elif bear_votes > bull_votes:
        direction = -1
        agreement = bear_votes / total_votes if total_votes > 0 else 0
        categories_agreeing = categories_bear
    else:
        direction = 0
        agreement = 0.0
        categories_agreeing = set()

    # --- Delta-direction agreement gate ---
    # Analysis: TYPE_A with delta agreeing = 75% win / +8.7 avg P&L
    #           TYPE_A with delta disagreeing = 33% win / -1.2 avg P&L
    # Bar delta must agree with signal direction for TYPE_A/B promotion.
    delta_agrees = True
    if bar_delta != 0 and direction != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            delta_agrees = False

    # --- IB (Initial Balance) multiplier ---
    # Analysis: TYPE_A in IB = 100% win / +21.6 avg P&L
    #           TYPE_A outside IB = 36% win / -1.7 avg P&L
    # First 60 bars of session get a score boost.
    ib_mult = 1.15 if 0 <= bar_index_in_session < 60 else 1.0

    # --- GEX regime modifier ---
    # Above gamma flip: dealers long gamma → stabilize price → absorption works
    # Below gamma flip: dealers short gamma → amplify moves → absorption fails
    gex_abs_mult = 1.0
    gex_near_wall_bonus = 0.0
    if gex_signal is not None and gex_signal.regime != GexRegime.NEUTRAL:
        if gex_signal.regime == GexRegime.POSITIVE_DAMPENING:
            gex_abs_mult = 1.3   # Boost absorption/exhaustion in positive gamma
        elif gex_signal.regime == GexRegime.NEGATIVE_AMPLIFYING:
            gex_abs_mult = 0.7   # Suppress absorption in negative gamma
        # Near wall bonus
        if gex_signal.near_call_wall or gex_signal.near_put_wall:
            gex_near_wall_bonus = 3.0

    # --- Layer 2: Category confluence ---
    cat_count = len(categories_agreeing)

    # Volume profile zone proximity adds a category (SCOR-03)
    zone_bonus = 0.0
    for zone in active_zones:
        if zone.state == ZoneState.INVALIDATED:
            continue
        if zone.bot_price <= bar_close <= zone.top_price:
            if zone.score >= cfg.zone_high_min:
                zone_bonus = cfg.zone_high_bonus
                categories_agreeing.add("volume_profile")
            elif zone.score >= cfg.zone_mid_min:
                zone_bonus = cfg.zone_mid_bonus
                categories_agreeing.add("volume_profile")
            break
        # Within zone_near_ticks of zone edge
        if (abs(bar_close - zone.bot_price) <= cfg.zone_near_ticks
                or abs(bar_close - zone.top_price) <= cfg.zone_near_ticks):
            if zone.score >= cfg.zone_high_min:
                zone_bonus = cfg.zone_near_bonus
                categories_agreeing.add("volume_profile")
            break

    cat_count = len(categories_agreeing)

    # Confluence multiplier (SCOR-02)
    confluence_mult = 1.25 if cat_count >= cfg.confluence_threshold else 1.0

    # --- Compute base score ---
    base_score = 0.0
    for cat in categories_agreeing:
        weight = CATEGORY_WEIGHTS.get(cat, 5.0)
        # GEX regime modifies absorption/exhaustion weight
        if cat in ("absorption", "exhaustion"):
            weight *= gex_abs_mult
        base_score += weight

    # Apply multiplier, zone bonus, GEX wall bonus, and IB boost
    total_score = min((base_score * confluence_mult + zone_bonus + gex_near_wall_bonus) * agreement * ib_mult, 100.0)

    # D-01 (ABS-06): Apply confirmation bonus for each confirmed absorption
    if narrative.confirmed_absorptions:
        confirmed_bonus = len(narrative.confirmed_absorptions) * _abs_cfg.confirmation_score_bonus
        total_score = min(total_score + confirmed_bonus, 100.0)

    # --- Classify tier (SCOR-04) ---
    has_absorption = "absorption" in categories_agreeing
    has_exhaustion = "exhaustion" in categories_agreeing
    has_zone = zone_bonus > 0
    min_strength = narrative.strength >= 0.3

    if (total_score >= cfg.type_a_min
            and (has_absorption or has_exhaustion)
            and has_zone
            and cat_count >= 5
            and delta_agrees):
        tier = SignalTier.TYPE_A
    elif (total_score >= cfg.type_b_min
            and cat_count >= 4
            and delta_agrees
            and min_strength):
        tier = SignalTier.TYPE_B
    elif total_score >= cfg.type_c_min and cat_count >= 4 and min_strength:
        tier = SignalTier.TYPE_C
    else:
        tier = SignalTier.QUIET

    # --- Build label (SCOR-06) ---
    if tier == SignalTier.TYPE_A:
        dir_str = "LONG" if direction > 0 else "SHORT"
        label = f"TYPE A — TRIPLE CONFLUENCE {dir_str} ({cat_count} categories, score {total_score:.0f})"
    elif tier == SignalTier.TYPE_B:
        dir_str = "LONG" if direction > 0 else "SHORT"
        label = f"TYPE B — DOUBLE CONFLUENCE {dir_str} ({cat_count} categories, score {total_score:.0f})"
    elif tier == SignalTier.TYPE_C:
        label = f"TYPE C — SIGNAL ({cat_count} categories, score {total_score:.0f})"
    else:
        label = narrative.label

    return ScorerResult(
        total_score=total_score,
        tier=tier,
        direction=direction,
        engine_agreement=agreement,
        category_count=cat_count,
        confluence_mult=confluence_mult,
        zone_bonus=zone_bonus,
        narrative=narrative.bar_type,
        label=label,
        categories_firing=sorted(categories_agreeing),
    )
