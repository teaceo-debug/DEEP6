"""Unified DEEP6 Daily Bias Score — all signals synthesized into one number.

Signal stack (total weight = 1.0):
    PO3 AMD Score          0.25  — Midnight Open, Judas, Weekly Open, PD zone
    ICT PD Array           0.20  — OB, FVG, IPDA, OTE confluence
    MTF Confluence         0.20  — Weekly/Daily/4H/1H/15M/5M alignment
    GEX / Options Flow     0.15  — Dealer gamma, DEX, net premium flow
    DEEP6 Order Flow       0.10  — Absorption, exhaustion, delta from footprint
    News Sentiment         0.07  — Finnhub + economic calendar
    Claude AI              0.03  — Final narrative synthesis weight boost/penalty

Output: UnifiedBiasScore with -100..+100 score, A+/A/B/C/F grade,
trade setup suggestion (entry zone, SL, TP), and full attribution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class TradeGrade(str, Enum):
    A_PLUS = "A+"   # 85%+ aligned — high conviction, full size
    A      = "A"    # 70–85% — trade at normal size
    B      = "B"    # 55–70% — trade at half size
    C      = "C"    # 40–55% — wait for more confirmation
    F      = "F"    # < 40%  — no trade, bias conflict too high


@dataclass
class SignalComponent:
    """One signal's contribution to the unified score."""
    name: str
    raw_score: float         # -100 to +100
    weight: float            # 0-1
    weighted: float          # raw_score * weight
    available: bool = True   # False if data source was unavailable
    detail: str = ""


@dataclass
class TradeSetup:
    """Suggested trade setup derived from bias and ICT levels."""
    direction: str                  # "LONG" | "SHORT" | "WAIT"
    entry_zone_high: Optional[float] = None
    entry_zone_low: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None     # PDH/PDL
    target_2: Optional[float] = None     # PWH/PWL or IPDA level
    risk_pts: Optional[float] = None
    reward_pts: Optional[float] = None
    rrr: Optional[float] = None          # reward / risk ratio
    entry_trigger: str = ""             # what to look for on the entry TF
    session_window: str = ""            # when to take the trade


@dataclass
class UnifiedBiasScore:
    """Complete bias picture from all DEEP6 signal sources."""
    # Final outputs
    score: float                    # -100 to +100
    direction: str                  # "STRONG_BULL" | "BULL" | "NEUTRAL" | "BEAR" | "STRONG_BEAR"
    confidence: float               # 0.0 to 1.0
    grade: TradeGrade               # A+ / A / B / C / F

    # Component breakdown
    components: list[SignalComponent] = field(default_factory=list)

    # Trade setup (populated by EntryModelEngine)
    setup: Optional[TradeSetup] = None

    # Context
    session_phase: str = ""         # "ACCUMULATION" | "MANIPULATION" | "DISTRIBUTION"
    judas_status: str = ""          # "BULL_CONFIRMED" | "BEAR_CONFIRMED" | ...
    macro_blackout: bool = False    # High-impact event within 30 min
    divergence_warning: str = ""    # Signal conflict description

    # AI narrative
    ai_reasoning: str = ""
    ai_key_triggers: str = ""

    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source: str = "deep6_unified_v2"


class UnifiedBiasEngine:
    """Combines all signal sources into a single bias score.

    Usage:
        engine = UnifiedBiasEngine()
        score = engine.compute(
            po3_score=75.0,           # from PO3BiasDetector
            pd_array_score=60.0,      # from PDArrayScore
            mtf_score=80.0,           # from MTFConfluenceEngine
            gex_score=40.0,           # from GEXClient
            orderflow_score=55.0,     # from DEEP6 absorption/exhaustion engines
            news_score=20.0,          # from NewsEngine
            ai_score=65.0,            # from ClaudeSynthesizer
            ...
        )
    """

    # Signal weights — must sum to 1.0
    WEIGHTS = {
        "po3":        0.25,
        "pd_array":   0.20,
        "mtf":        0.20,
        "gex":        0.15,
        "orderflow":  0.10,
        "news":       0.07,
        "ai":         0.03,
    }

    def compute(
        self,
        # Core ICT signals
        po3_score: float = 0.0,
        pd_array_score: float = 0.0,
        mtf_score: float = 0.0,

        # Institutional / options flow
        gex_score: float = 0.0,
        gex_available: bool = False,

        # DEEP6 order flow signals
        orderflow_score: float = 0.0,
        orderflow_available: bool = True,

        # Macro / news
        news_score: float = 0.0,
        news_available: bool = True,

        # Claude AI synthesis
        ai_score: float = 0.0,
        ai_available: bool = False,

        # Context for output
        session_phase: str = "",
        judas_status: str = "",
        macro_blackout: bool = False,
        ai_reasoning: str = "",
        ai_key_triggers: str = "",
        macro_confidence: float = 1.0,

        # ICT levels for trade setup (optional)
        current_price: float = 0.0,
        pd_high: float = 0.0,
        pd_low: float = 0.0,
        pw_high: float = 0.0,
        pw_low: float = 0.0,
        nearest_fvg_high: float = 0.0,
        nearest_fvg_low: float = 0.0,
        atr: float = 15.0,
    ) -> UnifiedBiasScore:
        """Compute unified bias from all available signals."""

        components: list[SignalComponent] = []
        total_weight = 0.0
        weighted_sum = 0.0

        def add(name: str, raw: float, weight: float, available: bool, detail: str = "") -> None:
            nonlocal total_weight, weighted_sum
            clamped = max(-100.0, min(100.0, raw))
            if not available:
                clamped = 0.0
            w = weight if available else 0.0
            total_weight += weight  # always count denominator
            weighted_sum += clamped * weight
            components.append(SignalComponent(
                name=name,
                raw_score=clamped,
                weight=weight,
                weighted=clamped * weight,
                available=available,
                detail=detail,
            ))

        add("PO3 AMD",       po3_score,       self.WEIGHTS["po3"],       True,               "Midnight Open / Judas / Weekly Open / PD zone")
        add("ICT PD Array",  pd_array_score,  self.WEIGHTS["pd_array"],  True,               "OB / FVG / IPDA / OTE confluence")
        add("MTF Alignment", mtf_score,       self.WEIGHTS["mtf"],       True,               "W/D/4H/1H/15M/5M bias stack")
        add("GEX/Flow",      gex_score,       self.WEIGHTS["gex"],       gex_available,      "GEX regime + DEX + net options premium")
        add("Order Flow",    orderflow_score, self.WEIGHTS["orderflow"], orderflow_available, "DEEP6 absorption / exhaustion / delta")
        add("News/Macro",    news_score,      self.WEIGHTS["news"],      news_available,     "Finnhub sentiment + economic calendar")
        add("Claude AI",     ai_score,        self.WEIGHTS["ai"],        ai_available,       "Claude API narrative synthesis")

        # Weighted average — normalize against total_weight (handles unavailable sources)
        raw = weighted_sum / total_weight if total_weight > 0 else 0.0
        score = max(-100.0, min(100.0, raw * macro_confidence))

        # Direction
        if score >= 60:
            direction = "STRONG_BULL"
        elif score >= 20:
            direction = "BULL"
        elif score <= -60:
            direction = "STRONG_BEAR"
        elif score <= -20:
            direction = "BEAR"
        else:
            direction = "NEUTRAL"

        # Confidence from alignment of available signals
        available_scores = [c.raw_score for c in components if c.available]
        confidence = _alignment_confidence(available_scores) * macro_confidence

        # Grade
        grade = _score_to_grade(confidence)

        # Divergence check
        div_warning = ""
        if available_scores:
            rng = max(available_scores) - min(available_scores)
            if rng > 120:
                div_warning = f"Extreme signal divergence ({rng:.0f}pts) — reduce size"
            elif rng > 80:
                div_warning = f"Moderate divergence ({rng:.0f}pts) — half size"

        # Trade setup
        setup = None
        if current_price > 0 and grade not in (TradeGrade.C, TradeGrade.F):
            setup = _derive_trade_setup(
                direction, score, current_price,
                pd_high, pd_low, pw_high, pw_low,
                nearest_fvg_high, nearest_fvg_low,
                atr, session_phase, judas_status,
            )

        return UnifiedBiasScore(
            score=round(score, 1),
            direction=direction,
            confidence=round(confidence, 3),
            grade=grade,
            components=components,
            setup=setup,
            session_phase=session_phase,
            judas_status=judas_status,
            macro_blackout=macro_blackout,
            divergence_warning=div_warning,
            ai_reasoning=ai_reasoning,
            ai_key_triggers=ai_key_triggers,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Trade Setup Generator
# ──────────────────────────────────────────────────────────────────────────────

def _derive_trade_setup(
    direction: str,
    score: float,
    price: float,
    pd_high: float,
    pd_low: float,
    pw_high: float,
    pw_low: float,
    fvg_high: float,
    fvg_low: float,
    atr: float,
    phase: str,
    judas_status: str,
) -> TradeSetup:
    """Derive a trade setup from bias direction and ICT levels.

    ICT entry model:
    - LONG: Enter in FVG/OB in discount zone during Distribution (NY AM)
      - Entry: inside nearest bull FVG or OTE zone
      - Stop: below manipulation low (Judas swing low)
      - Target 1: PDH, Target 2: PWH
    - SHORT: Mirror image
    """
    is_long = direction in ("BULL", "STRONG_BULL")
    is_short = direction in ("BEAR", "STRONG_BEAR")

    if not is_long and not is_short:
        return TradeSetup(direction="WAIT", entry_trigger="Await clearer bias alignment")

    # Session window for entry
    if phase == "MANIPULATION":
        window = "Wait — manipulation phase, no entry yet"
    elif phase == "DISTRIBUTION":
        window = "07:00–10:00 ET NY AM killzone — execute now"
    elif phase == "ACCUMULATION":
        window = "Wait for London open (00:00 ET)"
    else:
        window = "Wait for next Distribution phase"

    if is_long:
        # Entry: FVG zone or ATR-based zone below price
        entry_h = fvg_high if fvg_high > 0 else price - atr * 0.3
        entry_l = fvg_low  if fvg_low  > 0 else price - atr * 0.5

        # Stop: below manipulation wick / Judas swing low
        # Use 1.5x ATR below entry as default if no specific level
        stop = entry_l - atr * 0.5

        # Targets
        t1 = pd_high if pd_high > price else price + atr * 2
        t2 = pw_high if pw_high > t1    else t1 + atr * 2

        trigger = (
            "Enter long on FVG retest / OB retest in discount zone. "
            "Look for bullish 5M FVG or order block with delta flip."
        )
        if judas_status == "BULL_CONFIRMED":
            trigger = "Judas Bull confirmed — enter LONG on any pullback into FVG. High conviction."

    else:  # SHORT
        entry_h = fvg_high if fvg_high > 0 else price + atr * 0.5
        entry_l = fvg_low  if fvg_low  > 0 else price + atr * 0.3

        stop = entry_h + atr * 0.5

        t1 = pd_low  if pd_low < price else price - atr * 2
        t2 = pw_low  if pw_low < t1    else t1 - atr * 2

        trigger = (
            "Enter short on FVG retest / bear OB retest in premium zone. "
            "Look for bearish 5M FVG with delta flip negative."
        )
        if judas_status == "BEAR_CONFIRMED":
            trigger = "Judas Bear confirmed — enter SHORT on any pop into FVG. High conviction."

    risk = abs(entry_l - stop) if is_long else abs(entry_h - stop)
    reward = abs(t1 - entry_h) if is_long else abs(entry_l - t1)
    rrr = reward / risk if risk > 0 else 0.0

    return TradeSetup(
        direction="LONG" if is_long else "SHORT",
        entry_zone_high=round(entry_h, 2),
        entry_zone_low=round(entry_l, 2),
        stop_loss=round(stop, 2),
        target_1=round(t1, 2),
        target_2=round(t2, 2),
        risk_pts=round(risk, 2),
        reward_pts=round(reward, 2),
        rrr=round(rrr, 2),
        entry_trigger=trigger,
        session_window=window,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _alignment_confidence(scores: list[float]) -> float:
    """Fraction of scores pointing in the same direction as the mean."""
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    if mean == 0:
        return 0.0
    direction = 1 if mean > 0 else -1
    aligned = sum(1 for s in scores if s * direction > 0)
    base = aligned / len(scores)
    # Bonus for strength
    strength = min(abs(mean) / 100.0, 1.0) * 0.2
    return min(1.0, base + strength)


def _score_to_grade(confidence: float) -> TradeGrade:
    if confidence >= 0.85:
        return TradeGrade.A_PLUS
    if confidence >= 0.70:
        return TradeGrade.A
    if confidence >= 0.55:
        return TradeGrade.B
    if confidence >= 0.40:
        return TradeGrade.C
    return TradeGrade.F
