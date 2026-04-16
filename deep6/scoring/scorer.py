"""Two-layer confluence scorer — SCOR-01..06.

Layer 1: Engine-level agreement ratio (how many engines agree on direction)
Layer 2: Category-level confluence multiplier (how many signal categories agree)

When 5+ categories agree → 1.25× multiplier (SCOR-02)
Zone bonus: zones scoring ≥50 add +6 to +8 points (SCOR-03)

TypeA: absorption/exhaustion + zone confluence + 5+ categories = highest conviction
TypeB: 4+ categories + zone = tradeable
TypeC: 3+ categories = alert only
Quiet: fewer than 3 categories

Multiplier order (phase 12-01, locked):
    base → category (confluence_mult) → zone_bonus → IB (ib_mult) → VPIN (vpin_modifier) → clip(0, 100)

IB and VPIN are SEPARATE line items — they MUST NOT be fused/multiplied into a
single coefficient applied to per-signal scores. Doing so can saturate sizing
past tier thresholds (FOOTGUN 1 in 12-01-PLAN.md). VPIN modulates the fused
total_score only, as the final stage before clip.
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
from deep6.signals.flags import SignalFlags


class SignalTier(IntEnum):
    # DISQUALIFIED is intentionally lowest (negative) — plan 15-03 / D-33.
    # Vetoes (e.g. SPOOF_DETECTED from ConfluenceRules) force the result
    # here regardless of raw score. Pre-existing code compares tiers as
    # IntEnum ordinals; DISQUALIFIED < QUIET ensures "tier >= QUIET" gates
    # (there are none today) would still exclude it.
    DISQUALIFIED = -1
    QUIET = 0
    TYPE_C = 1
    TYPE_B = 2
    TYPE_A = 3


# ---------------------------------------------------------------------------
# Zone-compat shim
# ---------------------------------------------------------------------------
# Historically active_zones was list[VolumeZone] (with .bot_price / .top_price
# / .state=ZoneState.*). Per phase 15-01, LevelBus.get_all_active() now
# returns list[Level] (with .price_bot / .price_top / .state=LevelState.*).
# These helpers read either shape via duck-typing so both pre-15 and
# post-15 callers keep working while migration completes.


def _zone_bot(z) -> float:
    return getattr(z, "price_bot", None) if getattr(z, "price_bot", None) is not None else z.bot_price


def _zone_top(z) -> float:
    return getattr(z, "price_top", None) if getattr(z, "price_top", None) is not None else z.top_price


def _zone_invalidated(z) -> bool:
    st = z.state
    # Both LevelState.INVALIDATED and ZoneState.INVALIDATED have name="INVALIDATED"
    return getattr(st, "name", str(st)) == "INVALIDATED"


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
    # Phase 15-03 / D-33: meta-flags (bits 45+) emitted by ConfluenceRules.
    # Separate from the 45 stable signal bits so popcount-based signal
    # counting is not inflated. 0 when no confluence_annotations provided.
    meta_flags: int = 0


# Category weights — R1 thesis-heavy profile (round1 meta-optimization, 2026-04-15)
# Source: ninjatrader/backtests/results/round1/META-OPTIMIZATION.md
# ABS-01 SNR=9.46 dominance → absorption boosted 25→32, exhaustion 18→24.
# Trapped zeroed (near-zero SNR per signal attribution); poc zeroed (negligible).
# Total = 100.
CATEGORY_WEIGHTS = {
    "absorption": 32.0,    # R1: was 25 — ABS-01 SNR=9.46 dominant signal
    "exhaustion": 24.0,    # R1: was 18
    "trapped": 0.0,        # R1: was 14 — zero SNR per attribution; category still counted for cat_count
    "delta": 14.0,         # R1: was 13
    "imbalance": 13.0,     # R1: was 12
    "volume_profile": 5.0, # R1: was 10 — reduced (VOLP-03 is noise)
    "auction": 12.0,       # R1: was 8
    "poc": 0.0,            # R1: was 1 — negligible contribution; category still counted for cat_count
}


def score_bar(
    narrative: NarrativeResult,
    delta_signals: list[DeltaSignal],
    auction_signals: list[AuctionSignal],
    poc_signals: list[POCSignal],
    active_zones: list[VolumeZone],
    bar_close: float,
    type_a_min: float = 80.0,
    type_b_min: float = 72.0,
    type_c_min: float = 50.0,
    min_categories: int = 3,
    scorer_config: ScorerConfig | None = None,
    abs_config: AbsorptionConfig | None = None,
    bar_delta: int = 0,
    bar_index_in_session: int = -1,
    gex_signal: GexSignal | None = None,
    vpin_modifier: float = 1.0,
    confluence_annotations=None,  # ConfluenceAnnotations | None — see 15-03 D-32
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
    gex_momentum_mult = 1.0
    gex_near_wall_bonus = 0.0
    gex_direction_conflict = False
    if gex_signal is not None and gex_signal.regime != GexRegime.NEUTRAL:
        if gex_signal.regime == GexRegime.POSITIVE_DAMPENING:
            gex_abs_mult = 1.3     # Boost absorption/exhaustion (dealers provide passive flow)
            gex_momentum_mult = 0.8  # Suppress momentum (dealers fade trends)
        elif gex_signal.regime == GexRegime.NEGATIVE_AMPLIFYING:
            gex_abs_mult = 0.7     # Suppress absorption (dealers amplify, absorption breaks)
            gex_momentum_mult = 1.3  # Boost momentum (dealers add to trends)

        # Near wall bonus — but ONLY if direction aligns with wall defense
        # At call wall: dealers SELL → only SHORT signals get bonus
        # At put wall: dealers BUY → only LONG signals get bonus
        if gex_signal.near_call_wall and direction <= 0:
            gex_near_wall_bonus = 5.0  # Strong — dealer selling creates structural ceiling
        elif gex_signal.near_put_wall and direction >= 0:
            gex_near_wall_bonus = 5.0  # Strong — dealer buying creates structural floor
        # Direction conflict: LONG at call wall or SHORT at put wall = fighting dealers
        if gex_signal.near_call_wall and direction > 0:
            gex_direction_conflict = True  # Going long into massive dealer selling
        elif gex_signal.near_put_wall and direction < 0:
            gex_direction_conflict = True  # Going short into massive dealer buying

    # --- Phase 15-03 (D-32): ConfluenceAnnotations consumption ---
    # Insertion site (CONTENT-anchored): AFTER GEX regime-modifier block,
    # BEFORE "Layer 2: Category confluence". Applies rule-derived score
    # mutations to Levels in active_zones (keyed by level.uid per C5),
    # emits meta-flag bits, and registers vetoes for tier forcing.
    meta_flags: int = 0
    forced_disqualified: bool = False
    if confluence_annotations is not None:
        # 1. Apply score mutations to any Level-shaped zone in active_zones.
        #    VolumeZone objects lack `uid` — they're skipped silently (keyed
        #    by uid means a VolumeZone can never match; by design).
        muts = confluence_annotations.score_mutations
        if muts:
            for z in active_zones:
                uid = getattr(z, "uid", None)
                if uid is None:
                    continue
                delta = muts.get(uid, 0.0)
                if delta:
                    z.score = max(0.0, min(100.0, z.score + delta))

        # 2. Emit meta-flag bits. The stored scorer ints live in
        #    ScorerResult.meta_flags — kept separate from the 45 signal
        #    bits (0-44) so popcount of signal flags is unaffected.
        if "PIN_REGIME_ACTIVE" in confluence_annotations.flags:
            meta_flags |= int(SignalFlags.PIN_REGIME_ACTIVE)
        if "REGIME_CHANGE" in confluence_annotations.flags:
            meta_flags |= int(SignalFlags.REGIME_CHANGE)

        # 3. Vetoes force DISQUALIFIED tier regardless of raw score.
        if confluence_annotations.vetoes:
            forced_disqualified = True
            if "SPOOF_DETECTED" in confluence_annotations.vetoes:
                meta_flags |= int(SignalFlags.SPOOF_VETO)

    # --- Layer 2: Category confluence ---
    cat_count = len(categories_agreeing)

    # Volume profile zone proximity adds a category (SCOR-03)
    # Duck-typed over VolumeZone (legacy) and Level (post-15-01):
    # uses _zone_bot / _zone_top / _zone_invalidated helpers.
    zone_bonus = 0.0
    for zone in active_zones:
        if _zone_invalidated(zone):
            continue
        zbot = _zone_bot(zone)
        ztop = _zone_top(zone)
        if zbot <= bar_close <= ztop:
            if zone.score >= cfg.zone_high_min:
                zone_bonus = cfg.zone_high_bonus
                categories_agreeing.add("volume_profile")
            elif zone.score >= cfg.zone_mid_min:
                zone_bonus = cfg.zone_mid_bonus
                categories_agreeing.add("volume_profile")
            break
        # Within zone_near_ticks of zone edge
        if (abs(bar_close - zbot) <= cfg.zone_near_ticks
                or abs(bar_close - ztop) <= cfg.zone_near_ticks):
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
        # TIER-1 FIX 2: POC weight overrideable via ScorerConfig for sweeps.
        if cat == "poc":
            weight = cfg.poc_weight
        # GEX regime modifies category weights based on dealer positioning
        if cat in ("absorption", "exhaustion"):
            weight *= gex_abs_mult    # Positive gamma boosts, negative suppresses
        elif cat in ("delta", "imbalance"):
            weight *= gex_momentum_mult  # Negative gamma boosts momentum signals
        base_score += weight

    # Apply multiplier, zone bonus, GEX wall bonus, and IB boost
    total_score = min((base_score * confluence_mult + zone_bonus + gex_near_wall_bonus) * agreement * ib_mult, 100.0)

    # D-01 (ABS-06): Apply confirmation bonus for each confirmed absorption
    if narrative.confirmed_absorptions:
        confirmed_bonus = len(narrative.confirmed_absorptions) * _abs_cfg.confirmation_score_bonus
        total_score = min(total_score + confirmed_bonus, 100.0)

    # --- FINAL STAGE (phase 12-01): VPIN flow-toxicity modifier ---
    # Applied to fused total_score ONLY — NOT to per-signal scores, NOT stacked
    # with ib_mult. Separate line item (locked — see FOOTGUN 1 in 12-01-PLAN.md).
    # Order here is: ... -> ib_mult (above, inside base composition)
    #                   -> VPIN (this line)
    #                   -> clip(0, 100)
    total_score *= vpin_modifier
    total_score = max(0.0, min(100.0, total_score))

    # --- Classify tier (SCOR-04) ---
    has_absorption = "absorption" in categories_agreeing
    has_exhaustion = "exhaustion" in categories_agreeing
    has_zone = zone_bonus > 0
    min_strength = narrative.strength >= 0.3

    # TIER-1 FIX 3 (v2 softened): Trap veto only when 3+ traps present
    trap_signals = sum(1 for s in narrative.imbalances if "TRAP" in s.imb_type.name)
    type_a_trap_veto = trap_signals >= 3

    # TIER-1 FIX 4 (v2 softened): Delta chase only blocks when ratio > 0.15
    # (strong chase, not just same-direction weak delta)
    type_a_delta_chase = False
    if bar_delta != 0 and direction != 0:
        # Need volume context — approximate via narrative strength & score
        # Strong chase = same direction AND |delta| > 15% of typical bar volume
        # Using conservative threshold: require delta magnitude notable
        delta_mag = abs(bar_delta)
        if delta_mag > 50:  # only meaningful chases
            if direction > 0 and bar_delta > 0:
                type_a_delta_chase = True
            elif direction < 0 and bar_delta < 0:
                type_a_delta_chase = True

    # Phase 15-03 / D-32: Confluence vetoes force DISQUALIFIED regardless
    # of raw score / tier logic below. This check fires before the normal
    # tier ladder so spoofing etc. cannot leak into TYPE_* bands.
    if forced_disqualified:
        tier = SignalTier.DISQUALIFIED
    elif gex_direction_conflict:
        # Can't be TYPE_A or TYPE_B when fighting dealer flow
        if total_score >= cfg.type_c_min and cat_count >= 4 and min_strength:
            tier = SignalTier.TYPE_C
        else:
            tier = SignalTier.QUIET
    elif (total_score >= cfg.type_a_min
            and (has_absorption or has_exhaustion)
            and has_zone
            and cat_count >= 5
            and delta_agrees
            and not type_a_trap_veto
            and not type_a_delta_chase):
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

    # TIER-1 FIX 1: Midday window block — forensic finding bars 240-330
    # (10:30-13:00 ET) accumulate -$1,622 across 25 days. Force QUIET here.
    # DISQUALIFIED takes priority — do not demote to QUIET.
    if (tier != SignalTier.DISQUALIFIED
            and bar_index_in_session >= cfg.midday_block_start
            and bar_index_in_session <= cfg.midday_block_end):
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
        meta_flags=meta_flags,
    )
