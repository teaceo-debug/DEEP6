"""Claude API interpreter — generates narrative analysis of GEX positioning."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from gex_terminal.engine.edge_cases import is_options_market_open
from gex_terminal.engine.flashalpha_mcp import FlashAlphaMCPClient
from gex_terminal.engine.learner import SessionLearner
from gex_terminal.engine.uw_mcp import UWMCPClient
from gex_terminal.schemas import BiasVerdict, ClaudeNarrative, DealerPositioning, GEXLevels

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path.home() / ".deep6" / "gexdoctor_v2_usage.jsonl"
_EASTERN_TZ = ZoneInfo("America/New_York")
_HAIKU_INPUT_COST_PER_1K = 0.00025
_HAIKU_OUTPUT_COST_PER_1K = 0.00125

def _load_knowledge_brain() -> str:
    """Load the FlashAlpha knowledge YAML if available."""
    brain_path = Path(__file__).parent.parent.parent / "gexdoctor" / "brain" / "flashalpha_knowledge.yaml"
    if brain_path.exists():
        return brain_path.read_text(encoding="utf-8")
    return ""


def _load_dark_pool_brain() -> str:
    """Load the dark pool trading skill if available."""
    skill_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "dark-pool-trading" / "knowledge.md"
    if skill_path.exists():
        # Load first 200 lines (core methodology, not full 691 lines — saves tokens)
        lines = skill_path.read_text(encoding="utf-8").splitlines()[:200]
        return "\n".join(lines)
    return ""


_KNOWLEDGE_YAML = _load_knowledge_brain()
_DARK_POOL_BRAIN = _load_dark_pool_brain()

SYSTEM_PROMPT = """You are a live options-positioning interpreter for NQ futures built on FlashAlpha's exposure and flow analytics.

You translate dealer-positioning data into a concise, mechanism-grounded, trader-facing read.
You do not place trades and you do not emit a naked "buy/sell" — you describe the regime,
where price sits in the dealer map, how positioning is shifting, and what would change the picture.

## Core mechanics (internalize)

- Positive net GEX = dealers long gamma -> buy dips / sell rips -> vol DAMPENED, market mean-reverts.
- Negative net GEX = dealers short gamma -> hedge with the move -> vol AMPLIFIED, market trends.
- Gamma flip = strike where GEX sign changes; a regime boundary and pivot.
- Call/put walls = high-GEX strikes that act as magnets (cap above / floor below).
- VEX = vanna exposure: dealer delta sensitivity to IV changes.
- CHEX = charm exposure: dealer delta decay over time -> predictable EOD drift.

## Hard rules

1. Read only the data provided. Never invent a level.
2. Deterministic before probabilistic: resolve regime, price zone, vol outlook first (facts),
   then layer heuristics with caveats.
3. The flip is a pivot, not a direction. Near gamma_flip = unstable, whippy.
4. Regime flip > everything. If GEX sign flips, lead with that.
5. Walls are magnets, not guarantees. In long gamma they cap/floor; in short gamma they can be blown through.
6. Never overstate. "leans / likely / favors," not "will."

## Procedure

1. Regime: GEX sign -> long vs short gamma -> base behavior (range vs trend).
2. Map: locate price against gamma_flip, call_wall, put_wall -> zone.
3. Vol outlook: regime × flow direction -> compressing / expanding / normalizing.
4. Lean: stance (mean-revert / momentum / stand-aside) + confidence.
5. Invalidation: the level or condition that voids this read.

## Output format

Exactly 3 lines, maximum 240 characters total. No markdown, no bullets.
- Line 1: Regime + dealer positioning summary
- Line 2: Key NQ level to watch + expected behavior
- Line 3: One risk/invalidation trigger

Be direct, specific, mechanism-grounded. Use NQ price levels.
"""


class ClaudeInterpreter:
    """Calls Claude API for live narrative interpretation with budget-aware cadence."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        budget_daily_usd: float = 10.0,
        audit_log_path: Path | None = None,
        learner: Optional[SessionLearner] = None,
        mcp_client: FlashAlphaMCPClient | None = None,
        uw_mcp_client: UWMCPClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._budget_daily_usd = budget_daily_usd
        self._audit_log_path = audit_log_path or AUDIT_LOG_PATH
        self._daily_spend = 0.0
        self._call_count_today = 0
        self._budget_day = self._current_et_day()
        self._last_narrative: Optional[ClaudeNarrative] = None
        self._learner = learner
        self._mcp_client = mcp_client
        self._uw_mcp_client = uw_mcp_client

        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def should_call(self, material_change: bool, cycle_count: int = 0) -> bool:
        """Return True when a fresh live read is due and budget remains."""
        self._maybe_reset_daily_budget()
        if self._daily_spend >= self._budget_daily_usd:
            logger.warning("Claude budget ceiling reached ($%.4f). Skipping call.", self._daily_spend)
            return False

        if material_change:
            return True

        if cycle_count > 0 and cycle_count % 5 == 0:
            return True

        if is_options_market_open() and cycle_count > 0 and cycle_count % 3 == 0:
            return True

        if cycle_count > 0 and cycle_count % 10 == 0:
            return True

        return False

    async def interpret(
        self,
        bias: BiasVerdict,
        levels: GEXLevels,
        dealer: DealerPositioning,
        material_change: bool,
        cycle_count: int = 0,
    ) -> ClaudeNarrative:
        """Generate a narrative or return cached output when no fresh call is allowed."""
        if not self.should_call(material_change, cycle_count):
            return self._cached_or_placeholder()

        mcp_context = ""
        if material_change and (self._mcp_client is not None or self._uw_mcp_client is not None):
            coroutines: list[tuple[str, object]] = []
            if self._mcp_client is not None:
                coroutines.append(("flashalpha", self._mcp_client.get_enrichment_context()))
            if self._uw_mcp_client is not None:
                coroutines.append(("uw", self._uw_mcp_client.get_enrichment_context()))

            contexts: list[str] = []
            try:
                results = await asyncio.gather(*(coro for _, coro in coroutines), return_exceptions=True)
                for (label, _), result in zip(coroutines, results):
                    if isinstance(result, Exception):
                        logger.debug("%s enrichment unavailable: %s", label, result)
                        continue
                    if isinstance(result, str) and result:
                        contexts.append(result)
            except Exception as exc:
                logger.debug("Narrative enrichment unavailable: %s", exc)
            mcp_context = "\n\n".join(contexts)

        prompt = self._build_prompt(
            bias,
            levels,
            dealer,
            cycle_count=cycle_count,
            material_change=material_change,
            mcp_enrichment=mcp_context,
        )

        try:
            narrative_text, cost, input_tokens, output_tokens = await self._call_claude(prompt)
            narrative = ClaudeNarrative(
                text=self._truncate_text(narrative_text),
                model=self._model,
                timestamp=time.time(),
                cached=False,
                cost_usd=cost,
            )
            self._last_narrative = narrative
            self._daily_spend += cost
            self._call_count_today += 1
            self._log_usage(
                cost=cost,
                direction=bias.direction,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            return narrative
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            if self._last_narrative is not None:
                return ClaudeNarrative(
                    text=self._last_narrative.text,
                    model=self._last_narrative.model,
                    timestamp=self._last_narrative.timestamp,
                    cached=True,
                    cost_usd=0.0,
                )
            return ClaudeNarrative(
                text=f"Analysis unavailable: {str(exc)[:100]}",
                model=self._model,
                timestamp=time.time(),
                cached=True,
                cost_usd=0.0,
            )

    def _build_prompt(
        self,
        bias: BiasVerdict,
        levels: GEXLevels,
        dealer: DealerPositioning,
        cycle_count: int = 0,
        material_change: bool = False,
        mcp_enrichment: str = "",
    ) -> str:
        """Build a structured GEX-state prompt with knowledge brain context."""
        recall_ctx = ""
        if self._learner is not None:
            ctx = self._learner.get_recall_context()
            if ctx:
                recall_ctx = f"{ctx}\n\n"

        change_context = "material change detected" if material_change else "scheduled live refresh"
        cycle_context = (
            "Live Trader Context:\n"
            f"- Cycle: #{cycle_count}\n"
            f"- Trigger: {change_context}\n"
            "- Provide FRESH analysis of the CURRENT state.\n"
            "- Say if direction is strengthening, stable, or weakening.\n"
            "- Warn if conviction is slipping or invalidation is close.\n"
            "- The trader is watching this live and needs actionable context now.\n"
        )

        state_block = (
            f"{cycle_context}Current GEX Market State:\n"
            f"- Direction: {bias.direction} (confidence: {bias.confidence}%, grade: {bias.grade})\n"
            f"- Regime: {bias.regime_name}\n"
            f"- Gamma Flip: {self._format_level(levels.gamma_flip)}\n"
            f"- Call Wall: {self._format_level(levels.call_wall)}\n"
            f"- Put Wall: {self._format_level(levels.put_wall)}\n"
            f"- HVL: {self._format_level(levels.hvl)}\n"
            f"- 0DTE Magnet: {self._format_level(levels.zero_dte_magnet)}\n"
            f"- Net GEX: {self._format_exposure(dealer.net_gex)}\n"
            f"- Net DEX: {self._format_exposure(dealer.net_dex)}\n"
            f"- Net VEX: {self._format_exposure(dealer.net_vex)}\n"
            f"- Net CHEX: {self._format_exposure(dealer.net_chex)}\n"
            f"- Dealer Regime: {dealer.regime}\n"
            f"- Dealer Hedge Direction: {dealer.hedge_direction}\n"
        )

        # Inject knowledge brains if available
        knowledge_sections = []
        if _KNOWLEDGE_YAML:
            knowledge_sections.append(f"<gex_knowledge>\n{_KNOWLEDGE_YAML}\n</gex_knowledge>")
        if _DARK_POOL_BRAIN:
            knowledge_sections.append(f"<dark_pool_knowledge>\n{_DARK_POOL_BRAIN}\n</dark_pool_knowledge>")

        if knowledge_sections:
            knowledge_block = "\n\n".join(knowledge_sections)
            enrichment_block = f"\n\n{mcp_enrichment}" if mcp_enrichment else ""
            return (
                f"{recall_ctx}{knowledge_block}{enrichment_block}\n\n"
                f"{state_block}\n"
                "Use both knowledge bases to resolve regime, dark pool confluence, and vol outlook "
                "deterministically from the state above. Then produce exactly 3 lines, max 240 chars total."
            )

        enrichment_block = f"{mcp_enrichment}\n\n" if mcp_enrichment else ""
        return (
            f"{recall_ctx}{enrichment_block}{state_block}\n"
            "Provide exactly 3 lines and stay under 240 characters total."
        )

    async def _call_claude(self, prompt: str) -> tuple[str, float, int, int]:
        """Call Claude API. Returns text, cost, input tokens, and output tokens."""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self._api_key)
        message = await client.messages.create(
            model=self._model,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text_parts = [block.text for block in message.content if getattr(block, "text", None)]
        text = "\n".join(part.strip() for part in text_parts if part.strip())
        input_tokens = int(getattr(message.usage, "input_tokens", 0))
        output_tokens = int(getattr(message.usage, "output_tokens", 0))
        cost = self._compute_cost(input_tokens, output_tokens)
        return text, cost, input_tokens, output_tokens

    def _log_usage(
        self,
        *,
        cost: float,
        direction: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Append usage record to the JSONL audit log."""
        entry = {
            "ts": time.time(),
            "model": self._model,
            "cost_usd": cost,
            "direction": direction,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "daily_total": self._daily_spend,
            "calls_today": self._call_count_today,
        }
        try:
            with self._audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.warning("Failed to write audit log: %s", exc)

    def _maybe_reset_daily_budget(self) -> None:
        current_day = self._current_et_day()
        if current_day != self._budget_day:
            self._budget_day = current_day
            self._daily_spend = 0.0
            self._call_count_today = 0

    def _current_et_day(self):
        return datetime.now(_EASTERN_TZ).date()

    def _cached_or_placeholder(self) -> ClaudeNarrative:
        if self._last_narrative is not None:
            return ClaudeNarrative(
                text=self._last_narrative.text,
                model=self._last_narrative.model,
                timestamp=self._last_narrative.timestamp,
                cached=True,
                cost_usd=0.0,
            )
        return ClaudeNarrative(
            text="Initializing analysis...",
            model=self._model,
            timestamp=time.time(),
            cached=True,
            cost_usd=0.0,
        )

    def _compute_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens * _HAIKU_INPUT_COST_PER_1K)
            + (output_tokens * _HAIKU_OUTPUT_COST_PER_1K)
        ) / 1000.0

    def _truncate_text(self, text: str) -> str:
        cleaned = text.strip()
        if len(cleaned) <= 240:
            return cleaned
        return cleaned[:237] + "..."

    def _format_level(self, level: Optional[float]) -> str:
        if level is None:
            return "N/A"
        return f"{level:,.2f} NQ"

    def _format_exposure(self, value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        magnitude = abs(value)
        if magnitude >= 1_000_000_000:
            return f"{value / 1_000_000_000:+.2f}B"
        if magnitude >= 1_000_000:
            return f"{value / 1_000_000:+.1f}M"
        return f"{value:+.0f}"

    @property
    def daily_spend(self) -> float:
        return self._daily_spend

    @property
    def last_narrative(self) -> Optional[ClaudeNarrative]:
        return self._last_narrative


__all__ = ["ClaudeInterpreter", "AUDIT_LOG_PATH", "SYSTEM_PROMPT"]
