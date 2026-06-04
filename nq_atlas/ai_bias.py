from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic
from anthropic import APIStatusError, APITimeoutError, APIConnectionError

from nq_atlas.types import BiasDirection, BiasOutput, NQLevels
from nq_atlas.state import AtlasState

logger = logging.getLogger(__name__)


class BiasInterpreter:
    """Calls Claude API to interpret options positioning data as NQ bias."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    def _build_prompt(self, state: AtlasState) -> str:
        """Build structured options-analytics prompt from current state."""
        qqq_spot = state.spots.get("QQQ", 0.0)
        nq_price = state.spots.get("NQ", 0.0)
        gex = state.gex
        vc = state.vanna_charm
        flow = state.flow
        levels = state.nq_levels

        ratio = (nq_price / qqq_spot) if qqq_spot > 0 and nq_price > 0 else 0.0

        def to_nq(qqq_lvl: float | int | None) -> str:
            if not qqq_lvl or not ratio:
                return "N/A"
            return f"{float(qqq_lvl) * ratio:,.0f}"

        def to_float(value: object, default: float = 0.0) -> float:
            try:
                if value is None:
                    return default
                return float(value)
            except (TypeError, ValueError):
                return default

        fa = state.flashalpha or {}
        fa_summary = fa.get("summary", {})
        fa_levels = (fa.get("levels") or {}).get("levels", {})
        fa_zte = fa.get("zero_dte", {})
        fa_vex = fa.get("vex", {})
        fa_chex = fa.get("chex", {})

        fa_regime = str(fa_summary.get("regime", ""))
        fa_flip = to_float(fa_summary.get("gamma_flip"), 0.0)
        fa_net_gex = to_float((fa_summary.get("exposures") or {}).get("net_gex", 0), 0.0)
        fa_net_vex = to_float((fa_summary.get("exposures") or {}).get("net_vex", fa_vex.get("net_vex", 0)), 0.0)
        fa_net_chex = to_float((fa_summary.get("exposures") or {}).get("net_chex", fa_chex.get("net_chex", 0)), 0.0)
        fa_interp = fa_summary.get("interpretation", {})
        fa_hedge = fa_summary.get("hedging_estimate", {})

        fa_call_wall = fa_levels.get("call_wall")
        fa_put_wall = fa_levels.get("put_wall")
        fa_dte_magnet = fa_levels.get("zero_dte_magnet")

        fa_zte_regime = (fa_zte.get("regime") or {}).get("label", "")
        fa_zte_flip = to_float((fa_zte.get("regime") or {}).get("gamma_flip"), 0.0)
        fa_pin_score = to_float((fa_zte.get("pin_risk") or {}).get("pin_score", 0), 0.0)
        fa_magnet = (fa_zte.get("pin_risk") or {}).get("magnet_strike")
        fa_em_rem = to_float((fa_zte.get("expected_move") or {}).get("remaining_1sd_dollars", 0), 0.0)
        fa_em_upper = (fa_zte.get("expected_move") or {}).get("upper_bound")
        fa_em_lower = (fa_zte.get("expected_move") or {}).get("lower_bound")
        fa_charm_regime = (fa_zte.get("decay") or {}).get("charm_regime", "")
        fa_theta_hr = to_float((fa_zte.get("decay") or {}).get("theta_per_hour_remaining", 0), 0.0)
        fa_hours_close = to_float(fa_zte.get("time_to_close_hours", 0), 0.0)
        fa_dte_iv = to_float((fa_zte.get("vol_context") or {}).get("zero_dte_atm_iv", 0), 0.0)
        fa_7dte_iv = to_float((fa_zte.get("vol_context") or {}).get("seven_dte_atm_iv", 0), 0.0)
        fa_vanna_interp_dte = (fa_zte.get("vol_context") or {}).get("vanna_interpretation", "")

        hedge_down = fa_hedge.get("spot_down_1pct") or {}
        hedge_down_dir = hedge_down.get("direction", "?")
        hedge_down_notional = abs(to_float(hedge_down.get("notional_usd", 0), 0.0)) / 1e6

        dte_diverge = ""
        if fa_regime and fa_zte_regime and fa_regime != fa_zte_regime:
            dte_diverge = (
                f"⚠ REGIME DIVERGENCE: Full-chain={fa_regime} vs 0DTE={fa_zte_regime} "
                "— short-term suppression despite macro trend pressure"
            )

        flow_5m_m = (flow.signed_premium_5m / 1e6) if flow else 0
        flow_15m_m = (flow.signed_premium_15m / 1e6) if flow else 0
        flow_dir = (
            "BULLISH" if (flow and flow.net_direction > 0)
            else "BEARISH" if (flow and flow.net_direction < 0)
            else "NEUTRAL"
        )
        z_score = flow.z_score if flow else 0

        now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
        session_time = now_et.strftime("%H:%M ET")

        has_fa = bool(fa)
        fa_zte_flip_str = f"${fa_zte_flip:.2f}" if fa_zte_flip else "$0.00"
        dealer_vanna_massive = vc.dealer_hedge_direction if vc else 0
        dealer_charm_massive = (vc.net_charm_exposure / 1e6) if vc else 0

        prompt = f"""ROLE: You are an institutional-grade options market structure analyst providing directional bias on NQ futures based on dealer positioning analytics.

MARKET TIME: {session_time} | QQQ Spot: ${qqq_spot:.2f} | NQ Price: {nq_price:,.0f} | QQQ→NQ Ratio: {ratio:.2f}×

CURRENT STATE:

"""

        if has_fa:
            prompt += f"""=== FLASHALPHA DEALER STATE (institutional-grade) ===
Full-chain regime: {fa_regime.upper().replace('_', ' ')}
Gamma flip (QQQ): ${fa_flip:.2f} → NQ: {to_nq(fa_flip)}
Call wall (QQQ): ${fa_call_wall} → NQ: {to_nq(fa_call_wall)}
Put wall (QQQ):  ${fa_put_wall} → NQ: {to_nq(fa_put_wall)}
0DTE magnet (QQQ): ${fa_dte_magnet} → NQ: {to_nq(fa_dte_magnet)}
Net GEX:  ${fa_net_gex/1e6:+.0f}M
Net VEX:  ${fa_net_vex/1e9:+.2f}B
Net CHEX: ${fa_net_chex/1e6:+.0f}M

Dealer gamma:  {fa_interp.get('gamma', f"regime_sign={gex.regime_sign}" if gex else 'N/A')}
Dealer vanna:  {fa_interp.get('vanna', fa_vex.get('vex_interpretation', 'N/A'))}
Dealer charm:  {fa_interp.get('charm', fa_chex.get('chex_interpretation', 'N/A'))}
Down 1%: dealers {hedge_down_dir} ${hedge_down_notional:.0f}M additional

=== 0DTE ANALYTICS ===
0DTE regime: {fa_zte_regime.upper().replace('_', ' ')}
0DTE flip: {fa_zte_flip_str} → NQ: {to_nq(fa_zte_flip)}
Pin risk: {fa_pin_score}/100 at ${fa_magnet} → NQ: {to_nq(fa_magnet)}
Expected move remaining: ±${fa_em_rem:.2f} | Range: {to_nq(fa_em_lower)}–{to_nq(fa_em_upper)} NQ
0DTE charm regime: {fa_charm_regime}
Theta bleed: ${fa_theta_hr:,.0f}/hr | Time to close: {fa_hours_close:.1f}h
0DTE IV: {fa_dte_iv:.1f}% vs 7DTE IV: {fa_7dte_iv:.1f}%
0DTE vanna: {fa_vanna_interp_dte}
{dte_diverge}

"""
        else:
            prompt += "=== FLASHALPHA: NO DATA — using Massive.com computed Greeks only ===\n\n"

        prompt += f"""=== MASSIVE.COM SIGNED PREMIUM FLOW ===
Signed premium 5m:  ${flow_5m_m:+.2f}M (z={z_score:.2f})
Signed premium 15m: ${flow_15m_m:+.2f}M
Flow direction: {flow_dir}
Dealer vanna (Massive): {dealer_vanna_massive:+d}
Dealer charm (Massive): {dealer_charm_massive:+.1f}M
Legacy NQ levels: flip={levels.gex_flip if levels and levels.gex_flip is not None else 'N/A'}, call_wall={levels.call_wall if levels and levels.call_wall is not None else 'N/A'}, put_wall={levels.put_wall if levels and levels.put_wall is not None else 'N/A'}

=== GAMMA REGIME MECHANICS (apply to your interpretation) ===
NEGATIVE GAMMA: Dealers short gamma → moves AMPLIFIED → trend mode. Walls are breakout targets, not support/resistance.
POSITIVE GAMMA: Dealers long gamma → moves SUPPRESSED → mean-reversion. Walls are fade zones.
FLIP ZONE (±0.5% of flip): Regime uncertain — conviction should be reduced.
0DTE DIVERGENCE from full-chain: short-term pinning at current price while macro trend pressure builds.

TASK: Based on the above dealer positioning data, options market structure, and regime mechanics, provide your NQ futures directional bias for the next 30–120 minutes.

RESPOND IN JSON ONLY (no markdown):
{{
  "direction": "BULLISH" or "BEARISH" or "NEUTRAL",
  "conviction": 0-100,
  "support_nq": <integer>,
  "resistance_nq": <integer>,
  "narrative": "<2-3 sentences: why this bias, citing specific options data points>",
  "risk_flags": ["<specific warnings based on options data>"]
}}"""

        return prompt

    async def interpret(self, state: AtlasState) -> BiasOutput:
        """Call Claude and return BiasOutput. Falls back to last known on failure."""
        prompt = self._build_prompt(state)

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
                timeout=15.0,
            )
            raw_text = response.content[0].text.strip()

            # Strip markdown code blocks if present
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)

            data = json.loads(raw_text)

            direction = BiasDirection(data["direction"])
            conviction = max(0, min(100, int(data["conviction"])))
            support = float(data.get("support_nq", 0)) or None
            resistance = float(data.get("resistance_nq", 0)) or None

            levels = state.nq_levels
            nq_levels = NQLevels(
                gex_flip=levels.gex_flip if levels else None,
                call_wall=levels.call_wall if levels else None,
                put_wall=levels.put_wall if levels else None,
                support=support,
                resistance=resistance,
            )

            return BiasOutput(
                direction=direction,
                conviction=conviction,
                levels=nq_levels,
                narrative=str(data.get("narrative", "")),
                updated_at=datetime.now(timezone.utc),
                degraded=state.degraded(),
                risk_flags=list(data.get("risk_flags", [])),
            )

        except (APITimeoutError, APIConnectionError) as e:
            logger.warning(f"Claude API timeout/connection error: {e}")
        except APIStatusError as e:
            logger.error(f"Claude API status error {e.status_code}: {e.message}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse Claude response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in interpret(): {e}")

        # Fallback: return last known bias with degraded flag
        if state.bias is not None:
            return BiasOutput(
                direction=state.bias.direction,
                conviction=state.bias.conviction,
                levels=state.bias.levels,
                narrative=state.bias.narrative,
                updated_at=state.bias.updated_at,
                degraded=True,
                risk_flags=["AI interpretation unavailable - showing last known bias"],
            )

        # No prior bias: return neutral degraded
        return BiasOutput(
            direction=BiasDirection.NEUTRAL,
            conviction=0,
            levels=NQLevels(),
            narrative="Initializing — no bias available yet.",
            updated_at=datetime.now(timezone.utc),
            degraded=True,
            risk_flags=["No bias data available"],
        )

    async def interpret_loop(self, state: AtlasState, interval: int) -> None:
        """Async loop: call Claude every `interval` seconds."""
        while True:
            try:
                bias = await self.interpret(state)
                state.bias = bias
                state.last_ai_ts = time.time()
                logger.info(f"Bias updated: {bias.direction.value} conviction={bias.conviction}")
            except Exception as e:
                logger.error(f"interpret_loop error: {e}")
                state.log_error("ai_bias", str(e))
            await asyncio.sleep(interval)


__all__ = ["BiasInterpreter"]
