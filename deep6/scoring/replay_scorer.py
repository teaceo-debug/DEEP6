"""Phase 18 parity harness: read scored-bar NDJSON from stdin, emit scored JSON lines on stdout.

Usage: python3 -m deep6.scoring.replay_scorer  < input.ndjson > output.jsonl

Each input line must be a JSON object with "type":"scored_bar" and fields:
  barIdx         (int)    bar index
  barsSinceOpen  (int)    bar index within RTH session (0 = 9:30 open)
  barDelta       (int)    net delta for the bar
  barClose       (float)  bar close price
  zoneScore      (float)  active zone score 0-100 (0 = no zone)
  zoneDistTicks  (float)  distance from close to nearest zone edge in ticks
  signals        (list)   list of signal dicts with keys:
                          signalId (str), direction (int), strength (float),
                          price (float), detail (str)

Each output line is a JSON object:
  bar_index (int), score (float), tier (str), narrative (str)

Signal ID routing (maps wire IDs to Python scorer categories):
  ABS-*  -> narrative.absorption  (AbsorptionSignal)
  EXH-*  -> narrative.exhaustion  (ExhaustionSignal)
  TRAP-* -> narrative.imbalances  (ImbalanceSignal, imb_type=INVERSE_TRAP for direction vote)
  IMB-*  -> narrative.imbalances  (ImbalanceSignal; tier suffix -T1/-T2/-T3 maps to STACKED_T1/T2/T3)
  DELT-* -> delta_signals         (DeltaSignal; only DELT-04/05/06/08/10 vote in scorer)
  AUCT-* -> auction_signals       (AuctionSignal; only AUCT-01/02/05 vote in scorer)
  POC-*  -> poc_signals           (POCSignal; only POC-02/07/08 vote in scorer)
"""
from __future__ import annotations

import sys
import json

from deep6.engines.narrative import NarrativeResult, NarrativeType
from deep6.engines.absorption import AbsorptionSignal, AbsorptionType
from deep6.engines.exhaustion import ExhaustionSignal, ExhaustionType
from deep6.engines.imbalance import ImbalanceSignal, ImbalanceType
from deep6.engines.delta import DeltaSignal, DeltaType
from deep6.engines.auction import AuctionSignal, AuctionType
from deep6.engines.poc import POCSignal, POCType
from deep6.engines.signal_config import ScorerConfig
from deep6.scoring.scorer import score_bar


# ---------------------------------------------------------------------------
# Signal ID -> enum mapping helpers
# ---------------------------------------------------------------------------

def _delta_type_for_id(signal_id: str) -> DeltaType:
    """Map DELT-* wire ID to a DeltaType that the scorer will count as a vote.

    Only DELT-04/05/06/08/10 vote in the scorer (DeltaType.DIVERGENCE, CVD_DIVERGENCE,
    SLINGSHOT, TRAP, FLIP). Map conservatively so each ID produces a voting type.
    DELT-01/02/03 must NOT produce voting types — use RISE/DROP/TAIL which are excluded.
    """
    _MAP = {
        "DELT-01": DeltaType.RISE,          # excluded from vote in scorer
        "DELT-02": DeltaType.DROP,          # excluded
        "DELT-03": DeltaType.TAIL,          # excluded
        "DELT-04": DeltaType.DIVERGENCE,    # votes
        "DELT-05": DeltaType.CVD_DIVERGENCE, # votes
        "DELT-06": DeltaType.SLINGSHOT,     # votes
        "DELT-07": DeltaType.REVERSAL,      # excluded
        "DELT-08": DeltaType.TRAP,          # votes
        "DELT-09": DeltaType.SWEEP,         # excluded
        "DELT-10": DeltaType.FLIP,          # votes
        "DELT-11": DeltaType.AT_MIN,        # excluded
        "DELT-12": DeltaType.AT_MAX,        # excluded
        "DELT-13": DeltaType.VELOCITY,      # excluded
    }
    return _MAP.get(signal_id, DeltaType.RISE)  # default excluded


def _auction_type_for_id(signal_id: str) -> AuctionType:
    """Map AUCT-* wire ID to an AuctionType that the scorer will count.

    Only AUCT-01/02/05 vote (FINISHED_AUCTION, UNFINISHED_BUSINESS, MARKET_SWEEP).
    """
    _MAP = {
        "AUCT-01": AuctionType.FINISHED_AUCTION,    # votes
        "AUCT-02": AuctionType.UNFINISHED_BUSINESS,  # votes
        "AUCT-03": AuctionType.POOR_HIGH,           # excluded
        "AUCT-04": AuctionType.POOR_LOW,            # excluded
        "AUCT-05": AuctionType.MARKET_SWEEP,        # votes (maps to VOLUME_VOID? No: MARKET_SWEEP=6)
    }
    return _MAP.get(signal_id, AuctionType.POOR_HIGH)  # default excluded


def _poc_type_for_id(signal_id: str) -> POCType:
    """Map POC-* wire ID to a POCType that the scorer will count.

    Only POC-02/07/08 vote (EXTREME_POC_HIGH/LOW → POC-02, BULLISH_POC → POC-08, BEARISH_POC → POC-07).
    """
    _MAP = {
        "POC-01": POCType.ABOVE_POC,        # excluded
        "POC-02": POCType.EXTREME_POC_HIGH,  # votes (maps extreme POC)
        "POC-03": POCType.CONTINUOUS_POC,   # excluded
        "POC-04": POCType.POC_GAP,          # excluded
        "POC-05": POCType.BELOW_POC,        # excluded
        "POC-06": POCType.ENGULFING_VA,     # excluded
        "POC-07": POCType.BEARISH_POC,      # votes
        "POC-08": POCType.BULLISH_POC,      # votes
        "POC-09": POCType.VA_GAP,           # votes (EXTREME_POC_LOW variant)
    }
    return _MAP.get(signal_id, POCType.ABOVE_POC)  # default excluded


def _imbalance_type_for_id(signal_id: str, detail: str) -> ImbalanceType:
    """Map IMB-* wire ID to an ImbalanceType.

    Convention: IMB-T1/T2/T3 suffix maps to STACKED_T1/T2/T3 (D-02 dedup path).
    IMB without tier suffix maps to SINGLE. TRAP-* maps to INVERSE_TRAP (direction vote path).
    """
    sid = signal_id.upper()
    # Check detail string for STACKED hint
    detail_upper = (detail or "").upper()
    if "STACKED_T3" in sid or "STACKED_T3" in detail_upper or sid.endswith("-T3"):
        return ImbalanceType.STACKED_T3
    if "STACKED_T2" in sid or "STACKED_T2" in detail_upper or sid.endswith("-T2"):
        return ImbalanceType.STACKED_T2
    if "STACKED_T1" in sid or "STACKED_T1" in detail_upper or sid.endswith("-T1"):
        return ImbalanceType.STACKED_T1
    if "TRAP" in sid:
        return ImbalanceType.INVERSE_TRAP
    return ImbalanceType.SINGLE


# ---------------------------------------------------------------------------
# Wire signals -> Python scorer inputs
# ---------------------------------------------------------------------------

def _build_scorer_inputs(signals_json: list[dict]) -> tuple[
    list[AbsorptionSignal],
    list[ExhaustionSignal],
    list[ImbalanceSignal],
    list[DeltaSignal],
    list[AuctionSignal],
    list[POCSignal],
    float,   # max strength (for narrative.strength)
    str,     # label (for narrative.label)
    int,     # dominant direction (for narrative.direction)
    float,   # dominant price
]:
    """Decompose wire-format signals list into Python scorer input lists."""
    absorptions: list[AbsorptionSignal] = []
    exhaustions: list[ExhaustionSignal] = []
    imbalances: list[ImbalanceSignal] = []
    delta_sigs: list[DeltaSignal] = []
    auction_sigs: list[AuctionSignal] = []
    poc_sigs: list[POCSignal] = []

    max_strength = 0.0
    label = "QUIET"
    dom_direction = 0
    dom_price = 0.0

    for sig in signals_json:
        sid = sig.get("signalId", "")
        direction = int(sig.get("direction", 0))
        strength = float(sig.get("strength", 0.5))
        price = float(sig.get("price", 0.0))
        detail = sig.get("detail", "")

        if strength > max_strength:
            max_strength = strength
            dom_direction = direction
            dom_price = price
            label = detail if detail else sid

        if sid.startswith("ABS"):
            absorptions.append(AbsorptionSignal(
                bar_type=AbsorptionType.CLASSIC,
                direction=direction,
                price=price,
                wick="lower" if direction > 0 else "upper",
                strength=strength,
                wick_pct=30.0,
                delta_ratio=0.05,
                detail=detail,
                at_va_extreme=False,
            ))
        elif sid.startswith("EXH"):
            exhaustions.append(ExhaustionSignal(
                bar_type=ExhaustionType.EXHAUSTION_PRINT,
                direction=direction,
                price=price,
                strength=strength,
                detail=detail,
            ))
        elif sid.startswith("TRAP") or sid.startswith("IMB"):
            imb_type = _imbalance_type_for_id(sid, detail)
            imbalances.append(ImbalanceSignal(
                imb_type=imb_type,
                direction=direction,
                price=price,
                ratio=2.0,
                count=3,
                strength=strength,
                detail=detail,
            ))
        elif sid.startswith("DELT"):
            delta_type = _delta_type_for_id(sid)
            delta_sigs.append(DeltaSignal(
                delta_type=delta_type,
                direction=direction,
                strength=strength,
                value=float(sig.get("detail", "0").split("=")[-1]) if "=" in str(detail) else 100.0,
                detail=detail,
            ))
        elif sid.startswith("AUCT"):
            auction_type = _auction_type_for_id(sid)
            auction_sigs.append(AuctionSignal(
                auction_type=auction_type,
                direction=direction,
                price=price,
                strength=strength,
                detail=detail,
            ))
        elif sid.startswith("POC"):
            poc_type = _poc_type_for_id(sid)
            poc_sigs.append(POCSignal(
                poc_type=poc_type,
                direction=direction,
                price=price,
                strength=strength,
                detail=detail,
            ))

    return (absorptions, exhaustions, imbalances, delta_sigs, auction_sigs, poc_sigs,
            max_strength, label, dom_direction, dom_price)


def _build_narrative(signals_json: list[dict]) -> NarrativeResult:
    """Build a NarrativeResult from the wire-format signals list."""
    (absorptions, exhaustions, imbalances, _delta, _auction, _poc,
     max_strength, label, dom_direction, dom_price) = _build_scorer_inputs(signals_json)

    # Determine narrative type from highest-priority signal present
    if absorptions:
        bar_type = NarrativeType.ABSORPTION
        best = max(absorptions, key=lambda s: s.strength)
        direction = best.direction
        strength = best.strength
        price = best.price
        label = best.detail if best.detail else label
    elif exhaustions:
        bar_type = NarrativeType.EXHAUSTION
        best = max(exhaustions, key=lambda s: s.strength)
        direction = best.direction
        strength = best.strength
        price = best.price
        label = best.detail if best.detail else label
    elif imbalances:
        bar_type = NarrativeType.MOMENTUM
        direction = dom_direction
        strength = max_strength
        price = dom_price
    else:
        bar_type = NarrativeType.QUIET
        direction = 0
        strength = 0.0
        price = dom_price
        label = "QUIET"

    if not absorptions and not exhaustions and not imbalances and max_strength == 0.0:
        direction = 0

    return NarrativeResult(
        bar_type=bar_type,
        direction=direction,
        label=label,
        strength=strength,
        price=price,
        absorption=absorptions,
        exhaustion=exhaustions,
        imbalances=imbalances,
        all_signals_count=len(signals_json),
        confirmed_absorptions=[],
    )


def _build_delta_signals(signals_json: list[dict]) -> list[DeltaSignal]:
    result = []
    for sig in signals_json:
        sid = sig.get("signalId", "")
        if sid.startswith("DELT"):
            result.append(DeltaSignal(
                delta_type=_delta_type_for_id(sid),
                direction=int(sig.get("direction", 0)),
                strength=float(sig.get("strength", 0.5)),
                value=100.0,
                detail=sig.get("detail", ""),
            ))
    return result


def _build_auction_signals(signals_json: list[dict]) -> list[AuctionSignal]:
    result = []
    for sig in signals_json:
        sid = sig.get("signalId", "")
        if sid.startswith("AUCT"):
            result.append(AuctionSignal(
                auction_type=_auction_type_for_id(sid),
                direction=int(sig.get("direction", 0)),
                price=float(sig.get("price", 0.0)),
                strength=float(sig.get("strength", 0.5)),
                detail=sig.get("detail", ""),
            ))
    return result


def _build_poc_signals(signals_json: list[dict]) -> list[POCSignal]:
    result = []
    for sig in signals_json:
        sid = sig.get("signalId", "")
        if sid.startswith("POC"):
            result.append(POCSignal(
                poc_type=_poc_type_for_id(sid),
                direction=int(sig.get("direction", 0)),
                price=float(sig.get("price", 0.0)),
                strength=float(sig.get("strength", 0.5)),
                detail=sig.get("detail", ""),
            ))
    return result


# ---------------------------------------------------------------------------
# Zone shim for replay_scorer
# ---------------------------------------------------------------------------

class _ReplayZone:
    """Minimal zone object compatible with scorer.py _zone_bot/_zone_top/_zone_invalidated helpers.

    Zone geometry is constructed from bar_close and zone_dist_ticks to mirror the C# scorer's
    zoneDistTicks semantics:

    C# ConfluenceScorer:
      zoneScore >= 50 AND zoneDistTicks <= 0.5 → ZONE_NEAR_BONUS (+4)
      zoneScore >= 50 AND zoneDistTicks >  0.5 → ZONE_HIGH_BONUS (+8)
      zoneScore >= 30 (any dist)               → ZONE_MID_BONUS  (+6)

    Python scorer.py:
      bar_close inside zone (zbot <= bar_close <= ztop) AND zone.score >= 50 → +8
      bar_close near edge (abs(close - zbot|ztop) <= 0.5) AND zone.score >= 50 → +4
      bar_close inside zone AND zone.score >= 30                               → +6

    Mapping: if zone_dist_ticks <= 0.5, construct zone so bar_close is at the edge (not inside)
    → Python "near edge" path → matches C# ZONE_NEAR_BONUS.
    Otherwise, construct zone so bar_close is well inside → Python "inside" path → matches C# high/mid.
    """
    TICK_SIZE = 0.25

    def __init__(self, score: float, bar_close: float, zone_dist_ticks: float):
        self.score = score
        self.state = _FakeState(False)
        near_ticks = 0.5  # Python cfg.zone_near_ticks default

        if zone_dist_ticks <= near_ticks:
            # Near-edge semantics: place zone so bar_close is OUTSIDE but within zone_near_ticks.
            # Python scorer checks inside-zone first (zbot<=close<=ztop), then near-edge.
            # Set zone bottom just above bar_close by 0.1 ticks so close is outside but within 0.5.
            gap = 0.1 * self.TICK_SIZE  # small gap keeps close outside zone
            self.price_bot = bar_close + gap
            self.price_top = bar_close + gap + 10.0 * self.TICK_SIZE
        else:
            # Inside-zone semantics: bar_close is comfortably inside the zone.
            half = 5.0 * self.TICK_SIZE
            self.price_bot = bar_close - half
            self.price_top = bar_close + half


class _FakeState:
    def __init__(self, invalidated: bool):
        self.name = "INVALIDATED" if invalidated else "ACTIVE"


def _build_active_zones(bar_close: float, zone_score: float, zone_dist_ticks: float) -> list:
    """Build a synthetic active zone list for the scorer.

    When zone_score > 0, create a zone whose geometry produces the same bonus path as C# scorer's
    zoneDistTicks logic:
      zoneDistTicks <= 0.5 AND zoneScore >= 50 → near-edge path → +4 (ZONE_NEAR_BONUS)
      zoneDistTicks >  0.5 AND zoneScore >= 50 → inside path   → +8 (ZONE_HIGH_BONUS)
      zoneScore >= 30                          → mid path       → +6 (ZONE_MID_BONUS)
    """
    if zone_score <= 0:
        return []
    return [_ReplayZone(zone_score, bar_close, zone_dist_ticks)]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Read scored-bar NDJSON from stdin, emit scored JSON lines to stdout."""
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return

    cfg = ScorerConfig()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"WARN: JSON parse error: {exc}", file=sys.stderr)
            continue

        if rec.get("type") != "scored_bar":
            continue

        signals_json = rec.get("signals", [])
        bar_idx = int(rec.get("barIdx", 0))
        bars_since_open = int(rec.get("barsSinceOpen", 0))
        bar_delta = int(rec.get("barDelta", 0))
        bar_close = float(rec.get("barClose", 0.0))
        zone_score = float(rec.get("zoneScore", 0.0))
        zone_dist_ticks = float(rec.get("zoneDistTicks", 999.0))

        narrative = _build_narrative(signals_json)
        delta_signals = _build_delta_signals(signals_json)
        auction_signals = _build_auction_signals(signals_json)
        poc_signals = _build_poc_signals(signals_json)
        active_zones = _build_active_zones(bar_close, zone_score, zone_dist_ticks)

        result = score_bar(
            narrative=narrative,
            delta_signals=delta_signals,
            auction_signals=auction_signals,
            poc_signals=poc_signals,
            active_zones=active_zones,
            bar_close=bar_close,
            bar_delta=bar_delta,
            bar_index_in_session=bars_since_open,
            scorer_config=cfg,
        )

        out = {
            "bar_index": bar_idx,
            "score": round(result.total_score, 6),
            "tier": result.tier.name,
            "narrative": result.label,
        }
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
