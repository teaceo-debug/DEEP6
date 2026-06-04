"""Claude multi-agent bias synthesizer.

Three-agent consensus architecture (TradingAgents pattern):
  1. TechnicalAgent   — ICT/SMC signals: PO3, MTF, OB/FVG/IPDA, structure
  2. SentimentAgent   — News, GEX, options flow, macro calendar
  3. ConsensusAgent   — Final synthesis from both agents + risk gating

System prompts are prompt-cached (ephemeral) for ~5-min TTL.
Falls back to pure PO3 technical score if ANTHROPIC_API_KEY is unset.

Usage:
    synth = ClaudeSynthesizer()
    score = await synth.build_final_score(po3, news, macro, ...)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

try:
    import anthropic
except ImportError:  # optional dependency — fallback mode works without Anthropic installed
    anthropic = None

from deep6.bias_engine.models import (
    BiasDirection,
    DailyBiasScore,
    MacroEvent,
    NewsItem,
    PO3BiasState,
)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS_AGENT = 300
_MAX_TOKENS_CONSENSUS = 500

# ──────────────────────────────────────────────────────────────────────────────
# Cached system prompts — large static blocks cached for ~5min TTL
# ──────────────────────────────────────────────────────────────────────────────

_TECHNICAL_SYSTEM = """\
You are a Technical Analysis Agent specializing in ICT (Inner Circle Trader) Power of 3 for NQ futures.

## Your role
Analyze ONLY the technical signals provided. Give a directional bias based purely on:
- PO3 AMD cycle phase and score
- Judas Swing status (highest-alpha signal)
- Multi-timeframe alignment
- ICT levels: OBs, FVGs, IPDA, OTE zones, BOS/CHoCH
- Premium/Discount array positioning

## ICT scoring weights
- Judas Swing confirmed: strongest signal (+2 pts, double weight)
- Midnight Open relationship: primary anchor (+1 pt)
- Weekly Open relationship: macro context (+1 pt)
- PD zone (discount vs premium): opportunity zone (+1 pt)
- Previous day direction: continuation bias (+1 pt)

## Output format (JSON only, no prose outside JSON)
{
  "direction": "BULL",
  "confidence": 75,
  "key_level": "Above MO + Judas Bull confirmed",
  "reasoning": "One sentence max."
}\
"""

_SENTIMENT_SYSTEM = """\
You are a Sentiment Analysis Agent specializing in macro and options flow for NQ futures.

## Your role
Analyze ONLY the market sentiment signals provided. Give a directional bias based purely on:
- News sentiment and headlines (last 6 hours)
- Economic calendar (upcoming high-impact events: FOMC, CPI, NFP, PCE, GDP)
- GEX/DEX regime (dealer gamma positioning)
- Options flow (net call vs put premium)

## Key rules
- High-impact event within 30 min: NEUTRAL, confidence <= 30
- Negative GEX (trending regime): amplify directional signals
- Positive GEX (range-bound): dampen signals, mean-reversion bias
- CPI/NFP surprise >0.2%: overrides all other signals

## Output format (JSON only, no prose outside JSON)
{
  "direction": "BULL",
  "confidence": 60,
  "key_driver": "Positive options flow + negative GEX regime",
  "reasoning": "One sentence max.",
  "macro_blackout": false
}\
"""

_CONSENSUS_SYSTEM = """\
You are the Consensus Agent for the DEEP6 NQ futures bias engine.

## Your role
You receive outputs from two specialist agents:
  - TechnicalAgent: ICT/SMC signals, PO3, structure
  - SentimentAgent: News, GEX, options flow, macro

Your job is to SYNTHESIZE these into one final bias call.

## Consensus rules
1. If both agree (same direction, both confidence > 50): amplify confidence
2. If they disagree: apply HTF override (technical bias is primary)
3. If macro_blackout is true: NEUTRAL, confidence = 20
4. If extreme divergence (>60 pts): reduce confidence by 30%, add divergence warning
5. STRONG_BULL/STRONG_BEAR only when both agents agree AND both confidence > 70

## NQ context
- Distribution phase (07:00–13:00 ET): highest-probability trading window
- Judas Bull/Bear confirmed: +15% confidence bonus
- Grade A+ requires: same direction + both > 70 confidence

## Output format (JSON only, no prose outside JSON)
{
  "direction": "STRONG_BULL",
  "confidence": 82,
  "score": 65.0,
  "reasoning": "Both agents BULL. Judas confirmed, positive news sentiment, negative GEX regime amplifies.",
  "key_triggers": "Bearish flip if price breaks below midnight open or CPI hot.",
  "divergence_warning": "",
  "trade_grade": "A",
  "macro_blackout": false
}\
"""

_CACHE = {"type": "ephemeral"}


def _cached(text: str) -> list[dict]:
    return [{"type": "text", "text": text, "cache_control": _CACHE}]


class ClaudeSynthesizer:
    """Multi-agent Claude bias synthesizer."""

    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._client: Optional[anthropic.Anthropic] = (
            anthropic.Anthropic(api_key=api_key)
            if anthropic is not None and api_key
            else None
        )

    def is_available(self) -> bool:
        return self._client is not None

    async def synthesize(
        self,
        po3: PO3BiasState,
        news: list[NewsItem],
        macro: list[MacroEvent],
        gex_detail: str = "",
        gex_score: float = 0.0,
        mtf_summary: str = "",
        ict_detail: str = "",
        macro_conf: float = 1.0,
    ) -> tuple[BiasDirection, float, str, str]:
        """Run 3-agent consensus. Returns (direction, confidence, reasoning, triggers)."""
        if self._client is None:
            return _technical_fallback(po3)

        try:
            # Agent 1: Technical
            tech_msg = _build_technical_msg(po3, mtf_summary, ict_detail)
            tech_result = self._call_agent(_cached(_TECHNICAL_SYSTEM), tech_msg, _MAX_TOKENS_AGENT)

            # Agent 2: Sentiment
            sent_msg = _build_sentiment_msg(news, macro, gex_detail, gex_score, macro_conf)
            sent_result = self._call_agent(_cached(_SENTIMENT_SYSTEM), sent_msg, _MAX_TOKENS_AGENT)

            # Agent 3: Consensus
            cons_msg = _build_consensus_msg(tech_result, sent_result, po3)
            cons_result = self._call_agent(_cached(_CONSENSUS_SYSTEM), cons_msg, _MAX_TOKENS_CONSENSUS)

            direction = BiasDirection(cons_result.get("direction", "NEUTRAL"))
            confidence = max(0.0, min(1.0, float(cons_result.get("confidence", 50)) / 100.0))
            reasoning = cons_result.get("reasoning", "")
            triggers = cons_result.get("key_triggers", "")
            return direction, confidence, reasoning, triggers

        except Exception:
            return _technical_fallback(po3)

    def _call_agent(self, system: list[dict], user_msg: str, max_tokens: int) -> dict:
        """Make a single agent call and parse JSON response."""
        response = self._client.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        return json.loads(raw)

    async def build_final_score(
        self,
        po3: PO3BiasState,
        news: list[NewsItem],
        macro: list[MacroEvent],
        news_score: float = 0.0,
        macro_conf: float = 1.0,
        gex_score: float = 0.0,
        gex_detail: str = "",
        mtf_score: float = 0.0,
        mtf_summary: str = "",
        ict_detail: str = "",
    ) -> DailyBiasScore:
        """Assemble the complete DailyBiasScore from all pipeline inputs."""
        direction, confidence, reasoning, triggers = await self.synthesize(
            po3, news, macro,
            gex_detail=gex_detail, gex_score=gex_score,
            mtf_summary=mtf_summary, ict_detail=ict_detail,
            macro_conf=macro_conf,
        )

        technical_score = ((po3.bull_pts - po3.bear_pts) / 6.0) * 100.0
        ai_val = _direction_float(direction) * confidence * 100.0

        # Blended: 40% technical, 25% news, 20% GEX, 10% MTF, 5% AI
        blended = (
            0.40 * technical_score
            + 0.25 * news_score
            + 0.20 * gex_score
            + 0.10 * mtf_score
            + 0.05 * ai_val
        )
        blended = max(-100.0, min(100.0, blended * macro_conf))

        macro_blackout = any(
            ev.impact == "HIGH" and ev.minutes_until is not None and abs(ev.minutes_until) <= 5
            for ev in macro
        )

        div_warn: Optional[str] = None
        if abs(technical_score - news_score) > 60:
            div_warn = (
                f"Divergence: tech={technical_score:+.0f} news={news_score:+.0f} — reduce size"
            )

        return DailyBiasScore(
            direction=direction,
            score=round(blended, 1),
            confidence=round(confidence * macro_conf, 3),
            technical_score=round(technical_score, 1),
            news_score=round(news_score, 1),
            ai_score=round(ai_val, 1),
            po3_state=_state_dict(po3),
            news_items=news[:5],
            macro_events=[e for e in macro if e.impact == "HIGH"][:3],
            ai_reasoning=reasoning,
            ai_key_triggers=triggers,
            macro_blackout=macro_blackout,
            divergence_warning=div_warn,
            timestamp=datetime.now(tz=timezone.utc),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Message builders
# ──────────────────────────────────────────────────────────────────────────────

def _build_technical_msg(po3: PO3BiasState, mtf_summary: str, ict_detail: str) -> str:
    mo_rel = "ABOVE ▲" if po3.above_midnight_open else ("BELOW ▼" if po3.above_midnight_open is not None else "N/A")
    wo_rel = "ABOVE ▲" if po3.above_weekly_open  else ("BELOW ▼" if po3.above_weekly_open  is not None else "N/A")
    zone   = "DISCOUNT" if po3.in_discount else ("PREMIUM" if po3.in_discount is not None else "N/A")

    lines = [
        f"PO3 SCORE: {po3.bull_pts}▲ / {po3.bear_pts}▼ → {po3.direction.value}",
        f"Phase: {po3.phase.value} | Judas: {po3.judas_status.value}",
        f"vs Midnight Open ({po3.midnight_open or 'N/A'}): {mo_rel}",
        f"vs Weekly Open   ({po3.weekly_open or 'N/A'}): {wo_rel}",
        f"Zone vs PD EQ    ({po3.pd_eq or 'N/A'}): {zone}",
        f"Current price: {po3.current_close:.2f}",
    ]
    if po3.asia_eq:
        lines.append(f"Asia EQ: {po3.asia_eq:.2f}")
    if mtf_summary:
        lines.append(f"\nMTF: {mtf_summary}")
    if ict_detail:
        lines.append(f"ICT: {ict_detail}")

    return "\n".join(lines) + "\n\nReturn JSON only."


def _build_sentiment_msg(
    news: list[NewsItem],
    macro: list[MacroEvent],
    gex_detail: str,
    gex_score: float,
    macro_conf: float,
) -> str:
    if news:
        avg = sum(n.sentiment for n in news) / len(news)
        headlines = "\n".join(f"  [{n.sentiment_label.upper()}] {n.headline[:80]}" for n in news[:4])
        news_block = f"NEWS (avg={avg:+.2f}):\n{headlines}"
    else:
        news_block = "NEWS: None available."

    hi_evs = [e for e in macro if e.impact == "HIGH"]
    if hi_evs:
        ev_lines = "\n".join(f"  ⚠ {e.name} in {e.minutes_until}min" for e in hi_evs[:3])
        macro_block = f"HIGH-IMPACT EVENTS:\n{ev_lines}\nConf multiplier: {macro_conf:.1f}x"
    else:
        macro_block = "MACRO: No high-impact events next 24h."

    gex_block = f"GEX/FLOW: {gex_detail} (score={gex_score:+.0f})" if gex_detail else "GEX: unavailable."

    return f"{news_block}\n\n{macro_block}\n\n{gex_block}\n\nReturn JSON only."


def _build_consensus_msg(
    tech: dict,
    sent: dict,
    po3: PO3BiasState,
) -> str:
    judas_note = (
        "\nNote: Judas Bull CONFIRMED — +15% confidence bonus for bull calls."
        if po3.judas_status.value == "BULL_CONFIRMED"
        else "\nNote: Judas Bear CONFIRMED — +15% confidence bonus for bear calls."
        if po3.judas_status.value == "BEAR_CONFIRMED"
        else ""
    )

    return (
        f"TECHNICAL AGENT:\n{json.dumps(tech, indent=2)}\n\n"
        f"SENTIMENT AGENT:\n{json.dumps(sent, indent=2)}"
        f"{judas_note}\n\n"
        f"Current phase: {po3.phase.value}\n\n"
        "Synthesize into final consensus. Return JSON only."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _technical_fallback(po3: PO3BiasState) -> tuple[BiasDirection, float, str, str]:
    conf = max(po3.bull_pts, po3.bear_pts) / 6.0
    return (
        po3.direction,
        conf,
        f"Technical only (Claude unavailable): PO3 {po3.bull_pts}▲/{po3.bear_pts}▼",
        "AI synthesis unavailable; using technical-only fallback.",
    )


def _direction_float(d: BiasDirection) -> float:
    return {
        BiasDirection.STRONG_BULL: 1.0,
        BiasDirection.BULL: 0.5,
        BiasDirection.NEUTRAL: 0.0,
        BiasDirection.BEAR: -0.5,
        BiasDirection.STRONG_BEAR: -1.0,
    }.get(d, 0.0)


def _state_dict(s: PO3BiasState) -> dict:
    return {
        "bull_pts": s.bull_pts,
        "bear_pts": s.bear_pts,
        "direction": s.direction.value,
        "phase": s.phase.value,
        "judas_status": s.judas_status.value,
        "midnight_open": s.midnight_open,
        "weekly_open": s.weekly_open,
        "asia_eq": s.asia_eq,
        "pd_eq": s.pd_eq,
        "current_close": s.current_close,
    }
