"""Multi-timeframe confluence scorer for ICT/SMC bias.

Implements ICT's top-down analysis: bias flows from HTF → LTF.
Higher timeframe alignment amplifies confidence; conflict reduces it.

Timeframe hierarchy (ICT order of precedence):
    W  — Weekly       (macro narrative, strongest)
    D  — Daily        (primary bias, PO3 anchor)
    4H — 4-Hour       (intraday context, session structure)
    1H — 1-Hour       (entry timeframe structure)
    15M — 15-Minute   (entry signal timeframe)
    5M — 5-Minute     (execution, FVG/OB retest)

Usage:
    engine = MTFConfluenceEngine()
    engine.update("W",  direction=+1, score=70)
    engine.update("D",  direction=+1, score=80, judas_confirmed=True)
    engine.update("4H", direction=+1, score=65)
    engine.update("1H", direction=+1, score=55)
    result = engine.compute()
    # result.aligned_score, result.alignment_pct, result.trade_grade
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# Weights per timeframe — weekly has most structural authority
_TF_WEIGHTS: dict[str, float] = {
    "W":    0.30,
    "D":    0.25,
    "4H":   0.20,
    "1H":   0.15,
    "15M":  0.07,
    "5M":   0.03,
}

# Minimum aligned TFs for each trade grade
_GRADE_THRESHOLDS = {
    "A+": 0.85,   # 85%+ aligned → highest conviction
    "A":  0.70,
    "B":  0.55,
    "C":  0.40,
    "F":  0.0,    # below 40% = don't trade
}


@dataclass
class TFState:
    """Bias state for a single timeframe."""
    timeframe: str
    direction: int          # +1 bull, -1 bear, 0 neutral
    score: float            # 0-100 confidence in direction
    structure_break: str = ""   # "BOS" | "CHoCH" | ""
    judas_confirmed: bool = False
    fvg_nearby: bool = False
    ob_nearby: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class MTFConfluenceResult:
    """Output of multi-timeframe confluence scoring."""
    # Overall
    aligned_score: float        # -100 to +100 (directional confidence)
    alignment_pct: float        # 0-1 fraction of weighted TFs agreeing
    net_direction: int          # +1 / -1 / 0
    trade_grade: str            # "A+" | "A" | "B" | "C" | "F"

    # Breakdown
    bull_weight: float = 0.0
    bear_weight: float = 0.0
    neutral_weight: float = 0.0

    # Narratives
    aligned_timeframes: list[str] = field(default_factory=list)
    conflicting_timeframes: list[str] = field(default_factory=list)
    key_narrative: str = ""

    # Bonus flags
    judas_on_htf: bool = False      # Judas confirmed on D or 4H
    structure_aligned: bool = False  # BOS same direction on 3+ TFs
    double_confluence: bool = False  # FVG + OB at same price on entry TF


class MTFConfluenceEngine:
    """Maintains TF states and computes weighted alignment score."""

    def __init__(self) -> None:
        self._states: dict[str, TFState] = {}

    def update(
        self,
        timeframe: str,
        direction: int,
        score: float,
        structure_break: str = "",
        judas_confirmed: bool = False,
        fvg_nearby: bool = False,
        ob_nearby: bool = False,
    ) -> None:
        """Update bias state for a single timeframe."""
        if timeframe not in _TF_WEIGHTS:
            return
        self._states[timeframe] = TFState(
            timeframe=timeframe,
            direction=direction,
            score=max(0.0, min(100.0, score)),
            structure_break=structure_break,
            judas_confirmed=judas_confirmed,
            fvg_nearby=fvg_nearby,
            ob_nearby=ob_nearby,
        )

    def compute(self) -> MTFConfluenceResult:
        """Compute weighted multi-timeframe confluence result."""
        if not self._states:
            return MTFConfluenceResult(
                aligned_score=0.0, alignment_pct=0.0,
                net_direction=0, trade_grade="F",
                key_narrative="No timeframe data yet.",
            )

        bull_w = 0.0
        bear_w = 0.0
        neut_w = 0.0
        total_w = 0.0

        aligned_tfs: list[str] = []
        conflict_tfs: list[str] = []
        judas_htf = False
        bos_dirs: list[int] = []

        for tf, state in self._states.items():
            w = _TF_WEIGHTS.get(tf, 0.01)
            total_w += w
            weighted = w * (state.score / 100.0)

            if state.direction > 0:
                bull_w += weighted
            elif state.direction < 0:
                bear_w += weighted
            else:
                neut_w += weighted

            if state.judas_confirmed and tf in ("D", "4H"):
                judas_htf = True

            if state.structure_break in ("BOS", "CHoCH"):
                bos_dirs.append(state.direction)

        if total_w == 0:
            return MTFConfluenceResult(
                aligned_score=0.0, alignment_pct=0.0,
                net_direction=0, trade_grade="F",
            )

        bull_norm = bull_w / total_w
        bear_norm = bear_w / total_w

        # Net direction
        if bull_norm > bear_norm and bull_norm > 0.4:
            net_dir = +1
            alignment_pct = bull_norm
        elif bear_norm > bull_norm and bear_norm > 0.4:
            net_dir = -1
            alignment_pct = bear_norm
        else:
            net_dir = 0
            alignment_pct = 1.0 - (bull_norm + bear_norm)

        # Directional score: +100 = fully bull, -100 = fully bear
        aligned_score = (bull_norm - bear_norm) * 100.0

        # Structure alignment bonus
        structure_aligned = (
            len(bos_dirs) >= 3
            and all(d == net_dir for d in bos_dirs)
        )
        if structure_aligned:
            alignment_pct = min(1.0, alignment_pct + 0.10)

        # Judas bonus
        if judas_htf:
            alignment_pct = min(1.0, alignment_pct + 0.08)

        # Classify timeframes as aligned / conflicting
        for tf, state in self._states.items():
            if state.direction == net_dir or (net_dir == 0 and state.direction == 0):
                aligned_tfs.append(tf)
            elif state.direction != 0:
                conflict_tfs.append(tf)

        # Double confluence on execution TF
        double_conf = False
        for tf in ("5M", "15M"):
            if tf in self._states:
                s = self._states[tf]
                if s.fvg_nearby and s.ob_nearby:
                    double_conf = True

        # Trade grade
        trade_grade = "F"
        for grade, threshold in _GRADE_THRESHOLDS.items():
            if alignment_pct >= threshold:
                trade_grade = grade
                break

        # Key narrative
        narrative = _build_narrative(
            net_dir, aligned_tfs, conflict_tfs,
            judas_htf, structure_aligned, trade_grade
        )

        return MTFConfluenceResult(
            aligned_score=round(aligned_score, 1),
            alignment_pct=round(alignment_pct, 3),
            net_direction=net_dir,
            trade_grade=trade_grade,
            bull_weight=round(bull_norm, 3),
            bear_weight=round(bear_norm, 3),
            neutral_weight=round(1.0 - bull_norm - bear_norm, 3),
            aligned_timeframes=aligned_tfs,
            conflicting_timeframes=conflict_tfs,
            key_narrative=narrative,
            judas_on_htf=judas_htf,
            structure_aligned=structure_aligned,
            double_confluence=double_conf,
        )

    def get_state(self, timeframe: str) -> Optional[TFState]:
        return self._states.get(timeframe)

    def clear(self) -> None:
        self._states.clear()


def _build_narrative(
    direction: int,
    aligned: list[str],
    conflicting: list[str],
    judas_htf: bool,
    structure_aligned: bool,
    grade: str,
) -> str:
    dir_str = "BULLISH" if direction > 0 else "BEARISH" if direction < 0 else "NEUTRAL"
    parts = [f"{grade} {dir_str}"]

    if aligned:
        parts.append(f"Aligned: {','.join(aligned)}")
    if conflicting:
        parts.append(f"Conflict: {','.join(conflicting)}")
    if judas_htf:
        parts.append("✓ Judas HTF")
    if structure_aligned:
        parts.append("✓ BOS Aligned")

    return " | ".join(parts)
