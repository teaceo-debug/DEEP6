"""LLM second-opinion classifier for DepthRadar causal wall features."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

try:
    import anthropic
except ImportError:  # pragma: no cover - optional dependency
    anthropic = None  # type: ignore[assignment]

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - optional dependency
    AsyncOpenAI = None  # type: ignore[assignment]

from deep6.ml.depth_radar.causal_features import CAUSAL_FEATURE_NAMES, NUM_CAUSAL_FEATURES
from deep6.ml.depth_radar.episode import InteractionOutcome, WallIntent, WallState


log = logging.getLogger(__name__)

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_PROVIDER = "claude"
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_CACHE_TTL_SECONDS = 30.0
DEFAULT_MAX_TOKENS = 900

_VALID_PROVIDERS = {"claude", "openai"}
_INTENT_VALUES = {intent.value for intent in WallIntent}
_INTERACTION_VALUES = {outcome.value for outcome in InteractionOutcome}

_SYSTEM_PROMPT = """You are DEEP6's wall-intent classifier for NQ futures order-book walls.

You reason over strictly causal structured features only. Do not invent tape, hidden orders,
or price action that is not supported by the provided evidence.

Your tasks:
1. Classify wall intent as exactly one of:
   - PASSIVE_REAL
   - SPOOF_LIKE
   - RESERVE_REFRESH
   - MIGRATORY
2. Predict near-term wall interaction outcome as exactly one of:
   - BOUNCE
   - BREAK
   - CHURN
3. Explain the decision using the supplied features.
4. Score wall_quality from 0.0 to 1.0.

Microstructure priors:
- PASSIVE_REAL: genuine resting liquidity. Usually stable, does not pull on approach,
  can sit for meaningful time, may absorb repeated tests, often has reinforcement behind it.
- SPOOF_LIKE: intimidating display liquidity. Often short-lived, unstable, modification-heavy,
  cancel/reappear behavior, weak refill behavior, and especially suspicious if it pulls on approach.
- RESERVE_REFRESH: iceberg / reserve behavior. Refills after partial consumption, can recover after
  tests, maintains defense despite absorbed volume, often shows refill elasticity.
- MIGRATORY: market-making or repricing liquidity. Tracks BBO, reprices frequently, spends little
  time at one size or one level, may move instead of meaningfully defending.

Interpretation rules:
- prominence_zscore: high means the wall stands out versus nearby same-side levels.
- pull_approach_flag: one of the strongest spoof tells.
- cancel_reappear_count + size_volatility_10s + mod_rate_2s/mod_rate_10s: instability signals.
- repricing_count + low time_at_current_size: migratory signal.
- refills_so_far + refill_elasticity + recovery_after_test: reserve/defense signal.
- absorbed_volume + absorption_ratio + tests_count: evidence the wall has actually been engaged.
- same_side_depth_behind supports defense; vacuum_behind weakens defense.
- strong delta, sweep_flag, consecutive_aggressor, approach_speed, and attack_intensity indicate attack pressure.

Interaction definitions:
- BOUNCE: wall likely holds and price rejects away.
- BREAK: wall likely gets consumed or price pushes through.
- CHURN: repeated probing, partial fills, indecision, or no clear rejection/break yet.

Confidence rules:
- intent_confidence and interaction_confidence must be floats in [0.0, 1.0].
- Lower confidence when evidence conflicts.
- key_features should be short snake_case phrases backed by the data.

Output JSON only. No markdown. No code fences. Return exactly this object:
{
  "intent": "PASSIVE_REAL",
  "intent_confidence": 0.0,
  "intent_reasoning": "",
  "interaction": "CHURN",
  "interaction_confidence": 0.0,
  "interaction_reasoning": "",
  "wall_quality": 0.0,
  "key_features": ["feature_name"]
}"""


@dataclass(slots=True)
class _CacheEntry:
    created_monotonic: float
    result: dict[str, Any]


class LLMWallClassifier:
    """Foundation model wall classifier using Claude or OpenAI.

    Takes the 44 causal features for a wall, formats them into a structured
    prompt with domain context, and asks the LLM to classify intent and
    predict interaction outcome.

    This runs as a SECOND OPINION alongside the LightGBM classifier.
    Not for hot-path real-time use (latency ~500ms-2s per call).
    Best for: post-session review, training label validation, high-stakes walls.
    """

    def __init__(
        self,
        provider: str | None = None,
        anthropic_model: str = DEFAULT_CLAUDE_MODEL,
        openai_model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.0,
        validation_sample_size: int = 100,
        validation_concurrency: int = 3,
    ) -> None:
        resolved_provider = (provider or os.getenv("DEEP6_LLM_PROVIDER", DEFAULT_PROVIDER)).strip().lower()
        self.provider = resolved_provider if resolved_provider in _VALID_PROVIDERS else DEFAULT_PROVIDER
        self.anthropic_model = anthropic_model
        self.openai_model = openai_model
        self.timeout_seconds = max(0.5, float(timeout_seconds))
        self.cache_ttl_seconds = max(1.0, float(cache_ttl_seconds))
        self.max_tokens = max(200, int(max_tokens))
        self.temperature = max(0.0, min(1.0, float(temperature)))
        self.validation_sample_size = max(1, int(validation_sample_size))
        self.validation_concurrency = max(1, int(validation_concurrency))

        self._anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self._openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self._anthropic_client = (
            anthropic.AsyncAnthropic(api_key=self._anthropic_api_key)
            if anthropic is not None and self._anthropic_api_key
            else None
        )
        self._openai_client = (
            AsyncOpenAI(api_key=self._openai_api_key)
            if AsyncOpenAI is not None and self._openai_api_key
            else None
        )
        self._cache: dict[str, _CacheEntry] = {}

    @property
    def model_name(self) -> str:
        return self.anthropic_model if self.provider == "claude" else self.openai_model

    @property
    def is_available(self) -> bool:
        return self._active_client() is not None

    @property
    def unavailable_reason(self) -> str | None:
        if self.is_available:
            return None
        if self.provider == "claude":
            if anthropic is None:
                return "anthropic SDK is not installed"
            if not self._anthropic_api_key:
                return "ANTHROPIC_API_KEY is not set"
            return "anthropic client unavailable"
        if AsyncOpenAI is None:
            return "openai SDK is not installed"
        if not self._openai_api_key:
            return "OPENAI_API_KEY is not set"
        return "openai client unavailable"

    async def classify_intent(
        self,
        wall: Mapping[str, Any] | Sequence[float] | np.ndarray,
        wall_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return the intent slice of the combined LLM wall classification."""

        result = await self.classify_wall(wall, wall_context=wall_context)
        if result is None:
            return None
        return {
            "intent": result["intent"],
            "intent_confidence": result["intent_confidence"],
            "intent_reasoning": result["intent_reasoning"],
            "wall_quality": result["wall_quality"],
            "key_features": list(result["key_features"]),
        }

    async def predict_interaction(
        self,
        wall: Mapping[str, Any] | Sequence[float] | np.ndarray,
        wall_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return the interaction slice of the combined LLM wall classification."""

        result = await self.classify_wall(wall, wall_context=wall_context)
        if result is None:
            return None
        return {
            "interaction": result["interaction"],
            "interaction_confidence": result["interaction_confidence"],
            "interaction_reasoning": result["interaction_reasoning"],
            "wall_quality": result["wall_quality"],
            "key_features": list(result["key_features"]),
        }

    async def classify_wall(
        self,
        wall: Mapping[str, Any] | Sequence[float] | np.ndarray,
        wall_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return full LLM intent + interaction analysis, or None if unavailable."""

        if not self.is_available:
            log.info(
                "depth_radar.llm_classifier.unavailable provider=%s reason=%s",
                self.provider,
                self.unavailable_reason,
            )
            return None

        features, context = self._coerce_feature_map(wall, wall_context=wall_context)
        cache_key = self._build_cache_key(features, context)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return dict(cached)

        prompt = self.format_wall_request(features, wall_context=context)
        try:
            payload = await asyncio.wait_for(self._request_json(prompt), timeout=self.timeout_seconds)
        except TimeoutError:
            log.warning("depth_radar.llm_classifier.timeout provider=%s timeout=%.2fs", self.provider, self.timeout_seconds)
            return None
        except Exception:
            log.exception("depth_radar.llm_classifier.request_failed provider=%s", self.provider)
            return None

        result = self._normalize_result(payload, features)
        result["provider"] = self.provider
        result["model"] = self.model_name
        result["cached"] = False
        result["wall_state"] = self._resolve_wall_state(features, context).value

        self._cache[cache_key] = _CacheEntry(created_monotonic=time.monotonic(), result=dict(result))
        return result

    async def llm_second_opinion(
        self,
        wall_dict: Mapping[str, Any],
        lightgbm_confidence: float | None = None,
    ) -> dict[str, Any] | None:
        """Compatibility helper for the intended future CausalClassifier hook."""

        features, context = self._coerce_feature_map(wall_dict)
        size = max(
            features["current_size"],
            features["original_size"],
            features["max_size_so_far"],
        )
        confidence = self._coerce_float(
            lightgbm_confidence if lightgbm_confidence is not None else wall_dict.get("intent_confidence", wall_dict.get("confidence")),
            default=1.0,
        )
        distance = min(features["distance_from_bbo"], features["distance_from_mid"])
        if size <= 100.0 or confidence >= 0.6 or distance > 4.0:
            return None
        return await self.classify_wall(features, wall_context=context)

    def format_wall_request(
        self,
        wall: Mapping[str, Any] | Sequence[float] | np.ndarray,
        wall_context: Mapping[str, Any] | None = None,
    ) -> str:
        """Format the 44 causal features into a domain-aware wall analysis prompt."""

        features, context = self._coerce_feature_map(wall, wall_context=wall_context)
        state = self._resolve_wall_state(features, context)
        side = "ASK" if int(round(features["side"])) == 1 else "BID"
        wall_price = self._format_price(self._coerce_float(context.get("wall_price", context.get("price")), default=np.nan))
        imbalance = features["book_imbalance_top10"]
        delta_10s = features["delta_10s"]
        lines = [
            "Wall Analysis Request:",
            f"- Side: {side} at {wall_price}",
            (
                f"- Current size: {self._format_contracts(features['current_size'])} "
                f"(original: {self._format_contracts(features['original_size'])}, "
                f"max: {self._format_contracts(features['max_size_so_far'])}, "
                f"ratio: {features['size_vs_original']:.2f})"
            ),
            f"- Age: {features['age_seconds']:.1f} seconds ({state.value})",
            (
                f"- Modifications: {features['modifications_so_far']:.0f} total, "
                f"{features['mod_rate_10s']:.0f} in last 10s, {features['mod_rate_2s']:.0f} in last 2s"
            ),
            (
                f"- Refills: {features['refills_so_far']:.0f} "
                f"(elasticity: {features['refill_elasticity']:.2f}, size volatility 10s: {features['size_volatility_10s']:.2f})"
            ),
            f"- Pull on approach: {self._yes_no(features['pull_approach_flag'])}",
            f"- Cancel/reappear: {features['cancel_reappear_count']:.0f} times",
            (
                f"- Repricing: {features['repricing_count']:.0f} times, "
                f"time at current size: {features['time_at_current_size']:.1f}s"
            ),
            "",
            "Book context:",
            (
                f"- Distance from mid: {features['distance_from_mid']:.1f} ticks, "
                f"from BBO: {features['distance_from_bbo']:.1f} ticks"
            ),
            f"- Spread: {features['spread_ticks']:.1f} ticks",
            (
                f"- Book imbalance (top 10): {imbalance:+.2f} "
                f"({self._describe_book_imbalance(imbalance)})"
            ),
            (
                f"- Prominence z-score: {features['prominence_zscore']:.2f} "
                f"({self._describe_prominence(features['prominence_zscore'])})"
            ),
            (
                f"- Support depth behind: {self._format_contracts(features['same_side_depth_behind'])}, "
                f"ahead: {self._format_contracts(features['same_side_depth_ahead'])}"
            ),
            f"- Opposite mirror depth: {self._format_contracts(features['opposite_depth_mirror'])}",
            (
                f"- Cluster density: {features['cluster_density']:.0f}, depth slope: {features['depth_slope']:+.2f}, "
                f"ladder correlation: {features['ladder_correlation']:+.2f}"
            ),
            f"- Vacuum behind: {self._yes_no(features['vacuum_behind'])}",
            "",
            "Session/regime context:",
            (
                f"- Session phase: {self._describe_session_phase(features['session_phase'], features['minutes_since_open'])}, "
                f"minutes since open: {features['minutes_since_open']:.1f}"
            ),
            (
                f"- Realized vol 2m: {features['realized_vol_2m']:.2f}, "
                f"range expansion: {self._yes_no(features['range_expansion_flag'])}"
            ),
            "",
            "Flow context:",
            (
                f"- Cumulative delta: {features['cumulative_delta']:+.0f} "
                f"({self._describe_delta(features['cumulative_delta'])})"
            ),
            (
                f"- Delta last 2s: {features['delta_2s']:+.0f}, last 10s: {delta_10s:+.0f} "
                f"({self._describe_delta(delta_10s)})"
            ),
            (
                f"- Wall-relative pressure: {self._describe_wall_pressure(features)}"
            ),
            f"- Approach speed: {features['approach_speed']:.2f} ticks/sec toward wall",
            f"- Consecutive same-side aggressor: {features['consecutive_aggressor']:.0f} trades",
            f"- Sweep flag: {self._yes_no(features['sweep_flag'])}",
            "",
            "Attack/defense:",
            f"- Tests: {features['tests_count']:.0f}",
            f"- Absorbed volume: {self._format_contracts(features['absorbed_volume'])}",
            f"- Absorption ratio: {features['absorption_ratio']:.2f}",
            f"- Recovery after last test: {self._yes_no(features['recovery_after_test'])}",
            f"- Time since last test: {features['time_since_last_test']:.1f}s",
            f"- Attack intensity: {features['attack_intensity']:.2f} contracts/sec",
            "",
            "Respond with JSON only using the exact schema from the system instructions.",
        ]
        return "\n".join(lines)

    async def validate_labels(
        self,
        episodes_parquet: str,
        sample_size: int | None = None,
        random_state: int = 7,
    ) -> pd.DataFrame:
        """Run LLM classification on a sample of labeled episodes and report disagreements."""

        if not self.is_available:
            log.info(
                "depth_radar.llm_classifier.validate_labels_skipped provider=%s reason=%s",
                self.provider,
                self.unavailable_reason,
            )
            return self._empty_validation_report()

        path = Path(episodes_parquet).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Validation parquet not found: {path}")

        try:
            frame = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to read validation parquet: {path}") from exc

        if frame.empty:
            return self._empty_validation_report()

        size = max(1, int(sample_size or self.validation_sample_size))
        sample = self._prepare_validation_sample(frame, sample_size=size, random_state=random_state)
        if sample.empty:
            return self._empty_validation_report()

        semaphore = asyncio.Semaphore(self.validation_concurrency)

        async def classify_row(row: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                llm_result = await self.classify_wall(row)
            rule_intent = self._first_present(row, "intent_label", "rule_intent", "intent", "label")
            rule_interaction = self._first_present(row, "interaction_label", "interaction_outcome", "outcome", "interaction")
            return self._build_validation_row(row, llm_result, rule_intent=rule_intent, rule_interaction=rule_interaction)

        tasks = [classify_row(row) for row in sample.to_dict(orient="records")]
        results = await asyncio.gather(*tasks)
        report = pd.DataFrame(results)
        if report.empty:
            return self._empty_validation_report()
        return report.sort_values(["has_disagreement", "intent_confidence", "interaction_confidence"], ascending=[False, False, False])

    async def _request_json(self, prompt: str) -> dict[str, Any]:
        if self.provider == "claude":
            return await self._call_claude(prompt)
        return await self._call_openai(prompt)

    async def _call_claude(self, prompt: str) -> dict[str, Any]:
        client = self._active_client()
        if client is None:
            raise RuntimeError(self.unavailable_reason or "Claude client unavailable")
        response = await client.messages.create(
            model=self.anthropic_model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = self._extract_anthropic_text(getattr(response, "content", []))
        return self._parse_json_payload(text)

    async def _call_openai(self, prompt: str) -> dict[str, Any]:
        client = self._active_client()
        if client is None:
            raise RuntimeError(self.unavailable_reason or "OpenAI client unavailable")
        response = await client.chat.completions.create(
            model=self.openai_model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        choice = response.choices[0] if getattr(response, "choices", None) else None
        message = getattr(choice, "message", None)
        text = getattr(message, "content", "") or ""
        return self._parse_json_payload(text)

    def _active_client(self) -> Any | None:
        if self.provider == "claude":
            return self._anthropic_client
        return self._openai_client

    def _coerce_feature_map(
        self,
        wall: Mapping[str, Any] | Sequence[float] | np.ndarray,
        wall_context: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        if isinstance(wall, Mapping):
            nested_features = wall.get("features") if isinstance(wall.get("features"), Mapping) else {}
            merged_context = dict(nested_features) if isinstance(nested_features, Mapping) else {}
            merged_context.update(dict(wall))
            if wall_context:
                merged_context.update(dict(wall_context))
            features = {
                name: self._coerce_float(merged_context.get(name), default=0.0)
                for name in CAUSAL_FEATURE_NAMES
            }
            return features, merged_context

        vector = np.asarray(wall, dtype=np.float64)
        if vector.ndim != 1 or vector.shape[0] != NUM_CAUSAL_FEATURES:
            raise ValueError(
                f"Expected feature vector shape ({NUM_CAUSAL_FEATURES},), got {vector.shape}."
            )
        features = {
            name: self._coerce_float(value, default=0.0)
            for name, value in zip(CAUSAL_FEATURE_NAMES, vector.tolist(), strict=False)
        }
        return features, dict(wall_context or {})

    def _build_cache_key(self, features: Mapping[str, float], context: Mapping[str, Any]) -> str:
        cache_payload = {
            "provider": self.provider,
            "model": self.model_name,
            "wall_price": round(self._coerce_float(context.get("wall_price", context.get("price")), default=0.0), 4),
            "state": str(context.get("state", "")),
            "features": {name: round(self._coerce_float(features.get(name), default=0.0), 6) for name in CAUSAL_FEATURE_NAMES},
        }
        encoded = json.dumps(cache_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _get_cached(self, cache_key: str) -> dict[str, Any] | None:
        entry = self._cache.get(cache_key)
        if entry is None:
            return None
        if (time.monotonic() - entry.created_monotonic) > self.cache_ttl_seconds:
            self._cache.pop(cache_key, None)
            return None
        cached = dict(entry.result)
        cached["cached"] = True
        return cached

    def _normalize_result(self, payload: Mapping[str, Any], features: Mapping[str, float]) -> dict[str, Any]:
        key_features = self._normalize_key_features(payload.get("key_features"))
        if not key_features:
            key_features = self._default_key_features(features)

        intent = self._normalize_intent(payload.get("intent"))
        interaction = self._normalize_interaction(payload.get("interaction"))
        if intent is None:
            intent = self._fallback_intent(features)
        if interaction is None:
            interaction = self._fallback_interaction(features)

        return {
            "intent": intent,
            "intent_confidence": self._coerce_probability(
                payload.get("intent_confidence"),
                default=0.35,
            ),
            "intent_reasoning": self._coerce_text(
                payload.get("intent_reasoning"),
                default="LLM response omitted intent reasoning.",
            ),
            "interaction": interaction,
            "interaction_confidence": self._coerce_probability(
                payload.get("interaction_confidence"),
                default=0.35,
            ),
            "interaction_reasoning": self._coerce_text(
                payload.get("interaction_reasoning"),
                default="LLM response omitted interaction reasoning.",
            ),
            "wall_quality": self._coerce_probability(
                payload.get("wall_quality"),
                default=self._heuristic_wall_quality(features),
            ),
            "key_features": key_features,
        }

    def _fallback_intent(self, features: Mapping[str, float]) -> str:
        if features["pull_approach_flag"] >= 0.5 or (
            features["cancel_reappear_count"] >= 2 and features["mod_rate_10s"] >= 3 and features["refills_so_far"] < 1
        ):
            return WallIntent.SPOOF_LIKE.value
        if features["repricing_count"] >= 4 and features["time_at_current_size"] <= 3:
            return WallIntent.MIGRATORY.value
        if (
            features["refills_so_far"] >= 2
            or features["refill_elasticity"] >= 0.5
            or (features["recovery_after_test"] >= 0.5 and features["absorbed_volume"] > 0)
        ):
            return WallIntent.RESERVE_REFRESH.value
        return WallIntent.PASSIVE_REAL.value

    def _fallback_interaction(self, features: Mapping[str, float]) -> str:
        if (
            self._attack_score(features) >= 1.0
            and features["absorption_ratio"] < 0.75
            and features["pull_approach_flag"] < 0.5
        ):
            return InteractionOutcome.BREAK.value
        if (
            features["absorption_ratio"] >= 0.5
            and features["recovery_after_test"] >= 0.5
            and features["pull_approach_flag"] < 0.5
        ):
            return InteractionOutcome.BOUNCE.value
        return InteractionOutcome.CHURN.value

    def _heuristic_wall_quality(self, features: Mapping[str, float]) -> float:
        quality = 0.45
        quality += min(max(features["prominence_zscore"], 0.0), 4.0) * 0.06
        quality += min(features["absorption_ratio"], 1.5) * 0.12
        quality += min(features["refill_elasticity"], 1.5) * 0.10
        quality += min(features["same_side_depth_behind"] / max(features["current_size"], 1.0), 1.0) * 0.08
        quality -= 0.18 if features["pull_approach_flag"] >= 0.5 else 0.0
        quality -= min(features["cancel_reappear_count"], 4.0) * 0.05
        quality -= min(features["repricing_count"], 10.0) * 0.02
        quality -= 0.08 if features["vacuum_behind"] >= 0.5 else 0.0
        return max(0.0, min(1.0, quality))

    def _default_key_features(self, features: Mapping[str, float]) -> list[str]:
        tags: list[str] = []
        if features["pull_approach_flag"] >= 0.5:
            tags.append("pull_on_approach")
        if features["cancel_reappear_count"] >= 2:
            tags.append("cancel_reappear")
        if features["repricing_count"] >= 4:
            tags.append("frequent_repricing")
        if features["refill_elasticity"] >= 0.5 or features["refills_so_far"] >= 2:
            tags.append("refill_behavior")
        if features["absorption_ratio"] >= 0.5:
            tags.append("high_absorption_ratio")
        if abs(features["delta_10s"]) >= 150:
            tags.append("strong_recent_delta")
        if features["attack_intensity"] >= 8:
            tags.append("elevated_attack_intensity")
        if features["prominence_zscore"] >= 2.0:
            tags.append("high_prominence")
        if features["vacuum_behind"] >= 0.5:
            tags.append("vacuum_behind")
        if features["sweep_flag"] >= 0.5:
            tags.append("sweep_attack")
        return tags[:6] or ["balanced_feature_set"]

    def _resolve_wall_state(self, features: Mapping[str, float], context: Mapping[str, Any]) -> WallState:
        explicit = str(context.get("state", "")).strip().upper()
        if explicit in WallState.__members__:
            return WallState[explicit]
        if explicit in {state.value for state in WallState}:
            return WallState(explicit)
        if features["pull_approach_flag"] >= 0.5 and features["size_vs_original"] <= 0.5:
            return WallState.PULLED
        if features["size_vs_original"] <= 0.2 and features["absorbed_volume"] > 0:
            return WallState.EXHAUSTED
        if features["tests_count"] >= 1 and features["attack_intensity"] >= 6:
            return WallState.DEFENDING if features["recovery_after_test"] >= 0.5 else WallState.UNDER_ATTACK
        if features["time_at_current_size"] >= 45 and features["mod_rate_10s"] <= 0:
            return WallState.STALE
        if features["age_seconds"] <= 10 and features["tests_count"] <= 0:
            return WallState.FRESH
        return WallState.ESTABLISHED

    def _prepare_validation_sample(
        self,
        frame: pd.DataFrame,
        sample_size: int,
        random_state: int,
    ) -> pd.DataFrame:
        working = frame.copy()
        if "timestamp" in working.columns:
            sort_ts = pd.to_datetime(working["timestamp"], errors="coerce", utc=True)
            working = working.assign(_sort_ts=sort_ts).sort_values("_sort_ts", kind="stable").drop(columns="_sort_ts")

        label_columns = [column for column in ["intent_label", "rule_intent", "intent", "label", "interaction_label", "interaction_outcome", "outcome", "interaction"] if column in working.columns]
        if label_columns:
            labeled_mask = working[label_columns].notna().any(axis=1)
            working = working.loc[labeled_mask]
        if working.empty:
            return working

        if len(working) <= sample_size:
            return working.reset_index(drop=True)
        return working.sample(n=sample_size, random_state=random_state).reset_index(drop=True)

    def _build_validation_row(
        self,
        row: Mapping[str, Any],
        llm_result: Mapping[str, Any] | None,
        *,
        rule_intent: Any,
        rule_interaction: Any,
    ) -> dict[str, Any]:
        normalized_rule_intent = self._normalize_intent(rule_intent)
        normalized_rule_interaction = self._normalize_interaction(rule_interaction)
        llm_intent = self._normalize_intent(llm_result.get("intent")) if llm_result is not None else None
        llm_interaction = self._normalize_interaction(llm_result.get("interaction")) if llm_result is not None else None
        intent_match = (
            normalized_rule_intent == llm_intent
            if normalized_rule_intent is not None and llm_intent is not None
            else None
        )
        interaction_match = (
            normalized_rule_interaction == llm_interaction
            if normalized_rule_interaction is not None and llm_interaction is not None
            else None
        )
        has_disagreement = bool(intent_match is False or interaction_match is False)
        return {
            "episode_id": self._coerce_text(row.get("episode_id"), default=""),
            "timestamp": row.get("timestamp"),
            "provider": self.provider,
            "model": self.model_name,
            "rule_intent": normalized_rule_intent,
            "llm_intent": llm_intent,
            "intent_match": intent_match,
            "rule_interaction": normalized_rule_interaction,
            "llm_interaction": llm_interaction,
            "interaction_match": interaction_match,
            "intent_confidence": self._coerce_probability(llm_result.get("intent_confidence") if llm_result is not None else None, default=0.0),
            "interaction_confidence": self._coerce_probability(llm_result.get("interaction_confidence") if llm_result is not None else None, default=0.0),
            "wall_quality": self._coerce_probability(llm_result.get("wall_quality") if llm_result is not None else None, default=0.0),
            "key_features": list(llm_result.get("key_features", [])) if llm_result is not None else [],
            "has_disagreement": has_disagreement,
        }

    @staticmethod
    def _empty_validation_report() -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "episode_id",
                "timestamp",
                "provider",
                "model",
                "rule_intent",
                "llm_intent",
                "intent_match",
                "rule_interaction",
                "llm_interaction",
                "interaction_match",
                "intent_confidence",
                "interaction_confidence",
                "wall_quality",
                "key_features",
                "has_disagreement",
            ]
        )

    @staticmethod
    def _parse_json_payload(text: str) -> dict[str, Any]:
        raw = text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < start:
            raise ValueError("LLM response did not contain a JSON object")
        return json.loads(raw[start:end + 1])

    @staticmethod
    def _extract_anthropic_text(content_blocks: Any) -> str:
        parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
                continue
            if getattr(block, "type", None) == "text":
                parts.append(str(getattr(block, "text", "")))
        return "".join(parts).strip()

    @staticmethod
    def _normalize_intent(value: Any) -> str | None:
        text = str(value).strip().upper() if value is not None else ""
        return text if text in _INTENT_VALUES else None

    @staticmethod
    def _normalize_interaction(value: Any) -> str | None:
        text = str(value).strip().upper() if value is not None else ""
        return text if text in _INTERACTION_VALUES else None

    @staticmethod
    def _normalize_key_features(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        for item in value:
            text = str(item).strip().lower().replace(" ", "_").replace("-", "_")
            if text and text not in normalized:
                normalized.append(text)
        return normalized[:6]

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return float(default)
            number = float(value)
            if not np.isfinite(number):
                return float(default)
            return number
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _coerce_probability(value: Any, default: float = 0.0) -> float:
        number = LLMWallClassifier._coerce_float(value, default=default)
        if number > 1.0 and number <= 100.0:
            number /= 100.0
        return max(0.0, min(1.0, number))

    @staticmethod
    def _coerce_text(value: Any, default: str = "") -> str:
        text = str(value).strip() if value is not None else ""
        return text or default

    @staticmethod
    def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in mapping and mapping[key] is not None and not pd.isna(mapping[key]):
                return mapping[key]
        return None

    @staticmethod
    def _yes_no(value: float) -> str:
        return "Yes" if value >= 0.5 else "No"

    @staticmethod
    def _format_contracts(value: float) -> str:
        return f"{int(round(value))} contracts"

    @staticmethod
    def _format_price(value: float) -> str:
        if not np.isfinite(value):
            return "unknown price"
        return f"{value:,.2f}"

    @staticmethod
    def _describe_book_imbalance(value: float) -> str:
        if value >= 0.25:
            return "strong bid pressure"
        if value >= 0.08:
            return "slight bid pressure"
        if value <= -0.25:
            return "strong ask pressure"
        if value <= -0.08:
            return "slight ask pressure"
        return "roughly balanced"

    @staticmethod
    def _describe_prominence(value: float) -> str:
        if value >= 2.5:
            return "extremely large versus neighbors"
        if value >= 1.5:
            return "significantly larger than neighbors"
        if value >= 0.75:
            return "moderately larger than neighbors"
        if value <= -0.5:
            return "not prominent versus neighbors"
        return "close to neighborhood average"

    @staticmethod
    def _describe_session_phase(phase: float, minutes_since_open: float) -> str:
        phase_bucket = int(round(phase))
        if minutes_since_open < 45:
            return f"bucket {phase_bucket} / open"
        if minutes_since_open < 150:
            return f"bucket {phase_bucket} / morning"
        if minutes_since_open < 300:
            return f"bucket {phase_bucket} / midday"
        return f"bucket {phase_bucket} / late session"

    @staticmethod
    def _describe_delta(value: float) -> str:
        if value >= 250:
            return "strong buying pressure"
        if value >= 75:
            return "modest buying pressure"
        if value <= -250:
            return "strong selling pressure"
        if value <= -75:
            return "modest selling pressure"
        return "mixed flow"

    def _describe_wall_pressure(self, features: Mapping[str, float]) -> str:
        side = int(round(features["side"]))
        delta_10s = features["delta_10s"]
        if side == 1:
            attack_delta = delta_10s
            direction = "into the ask"
        else:
            attack_delta = -delta_10s
            direction = "into the bid"
        score = self._attack_score(features)
        if attack_delta >= 250 or score >= 1.4:
            intensity = "strong attack"
        elif attack_delta >= 75 or score >= 0.8:
            intensity = "moderate attack"
        elif attack_delta <= -75:
            intensity = "flow moving away"
        else:
            intensity = "mixed attack pressure"
        return f"{intensity} {direction}"

    def _attack_score(self, features: Mapping[str, float]) -> float:
        side = int(round(features["side"]))
        delta_component = features["delta_10s"] if side == 1 else -features["delta_10s"]
        score = 0.0
        score += min(max(delta_component, 0.0), 400.0) / 250.0
        score += min(max(features["attack_intensity"], 0.0), 20.0) / 20.0
        score += min(max(features["approach_speed"], 0.0), 4.0) / 4.0
        score += 0.35 if features["sweep_flag"] >= 0.5 else 0.0
        score += min(max(features["consecutive_aggressor"], 0.0), 8.0) / 16.0
        return score


__all__ = [
    "DEFAULT_CLAUDE_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "LLMWallClassifier",
]
