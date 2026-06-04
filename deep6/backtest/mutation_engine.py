from __future__ import annotations

import random
from enum import Enum
from typing import Any, Optional

from deep6.backtest.param_bounds import PARAM_BOUNDS, clamp_config, validate_config
from deep6.backtest.strategy_config import (
    ApproachDirection,
    LevelExit,
    LevelTarget,
    StrategyConfig,
    TimingFilter,
)
from deep6v2.types.signal import SignalId


class MutationType(str, Enum):
    TWEAK_PARAMS = "TWEAK_PARAMS"
    SWAP_LEVEL_TARGET = "SWAP_LEVEL_TARGET"
    ADD_CONFIRMATION = "ADD_CONFIRMATION"
    REMOVE_CONFIRMATION = "REMOVE_CONFIRMATION"
    SWAP_EXIT = "SWAP_EXIT"
    CHANGE_TIMING = "CHANGE_TIMING"
    CROSSOVER = "CROSSOVER"
    RANDOM = "RANDOM"


AVAILABLE_SIGNALS = [
    signal_name
    for signal_name in (
        "ABS_01",
        "ABS_02",
        "ABS_03",
        "ABS_04",
        "EXH_01",
        "EXH_02",
        "EXH_03",
        "EXH_04",
        "EXH_05",
        "EXH_06",
        "IMB_01",
        "IMB_02",
        "IMB_03",
        "IMB_04",
        "IMB_05",
        "DELT_01",
        "DELT_02",
        "DELT_03",
        "DELT_04",
        "DELT_05",
        "AUCT_01",
        "AUCT_02",
        "AUCT_03",
        "VOLP_01",
        "VOLP_02",
        "VOLP_03",
    )
    if signal_name in SignalId.__members__
]


class MutationEngine:
    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self._mutation_scores: dict[str, list[float]] = {mt.value: [] for mt in MutationType}

    def mutate(
        self,
        parent: StrategyConfig,
        mutation_type: Optional[MutationType] = None,
        other_parent: Optional[StrategyConfig] = None,
    ) -> StrategyConfig:
        """Mutate parent config. Returns new child config with lineage."""
        if mutation_type is None:
            mutation_type = self.select_mutation_type([])

        if mutation_type == MutationType.CROSSOVER and other_parent is None:
            mutation_type = self._rng.choice([mt for mt in MutationType if mt != MutationType.CROSSOVER])

        for _ in range(5):
            try:
                child_data = parent.model_dump(mode="json", exclude_none=False)

                if mutation_type == MutationType.TWEAK_PARAMS:
                    child_data = self._tweak_params(child_data)
                elif mutation_type == MutationType.SWAP_LEVEL_TARGET:
                    child_data["level_target"] = self._rng.choice(
                        [target.value for target in LevelTarget if target != parent.level_target]
                    )
                elif mutation_type == MutationType.ADD_CONFIRMATION:
                    child_data = self._add_confirmation(child_data)
                elif mutation_type == MutationType.REMOVE_CONFIRMATION:
                    child_data = self._remove_confirmation(child_data)
                elif mutation_type == MutationType.SWAP_EXIT:
                    child_data = self._swap_exit(child_data)
                elif mutation_type == MutationType.CHANGE_TIMING:
                    child_data["timing_filter"] = self._rng.choice(
                        [timing.value for timing in TimingFilter if timing != parent.timing_filter]
                    )
                elif mutation_type == MutationType.CROSSOVER and other_parent is not None:
                    child_data = self._crossover(child_data, other_parent)
                elif mutation_type == MutationType.RANDOM:
                    child_data = self._random_config_data()

                child = self._finalize_child(child_data, parent, mutation_type)
                if not validate_config(child):
                    return child
            except Exception:
                continue

        return self._make_random_config(generation=parent.generation + 1, parent_hash=parent.config_hash())

    def generate_initial_population(self, n: int = 10) -> list[StrategyConfig]:
        """Create a diverse seed population."""
        population: list[StrategyConfig] = []
        seen_hashes: set[str] = set()

        for index, target in enumerate(list(LevelTarget)[: min(len(LevelTarget), n)]):
            data = self._random_config_data()
            data["level_target"] = target.value
            data["approach_direction"] = list(ApproachDirection)[index % len(ApproachDirection)].value
            data["timing_filter"] = list(TimingFilter)[index % len(TimingFilter)].value
            config = self._config_from_data(data)
            config_hash = config.config_hash()
            if config_hash not in seen_hashes:
                population.append(config)
                seen_hashes.add(config_hash)

        while len(population) < n:
            config = self._make_random_config()
            config_hash = config.config_hash()
            if config_hash in seen_hashes:
                continue
            population.append(config)
            seen_hashes.add(config_hash)

        return population[:n]

    def select_mutation_type(self, history: list[dict[str, Any]]) -> MutationType:
        """Select mutation type, biasing toward historically better OOS fitness."""
        if len(history) < 5:
            return self._rng.choice(list(MutationType))

        weights: dict[MutationType, float] = {}
        for mutation in MutationType:
            fitnesses = [
                float(record.get("oos_fitness", 0.0) or 0.0)
                for record in history
                if record.get("mutation_type") == mutation.value
            ]
            avg_fitness = (sum(fitnesses) / len(fitnesses)) if fitnesses else 0.0
            weights[mutation] = max(0.01, avg_fitness + 0.1)

        total_weight = sum(weights.values())
        threshold = self._rng.uniform(0.0, total_weight)
        cumulative = 0.0
        for mutation, weight in weights.items():
            cumulative += weight
            if threshold <= cumulative:
                return mutation
        return self._rng.choice(list(MutationType))

    def _tweak_params(self, data: dict[str, Any]) -> dict[str, Any]:
        mutated = dict(data)
        tweaks = self._rng.sample(
            ["stop_ticks", "target_ticks", "max_bars_in_trade", "multi_level_distance_ticks"],
            k=self._rng.randint(1, 2),
        )

        bracket_exit = dict(mutated.get("bracket_exit") or {})
        time_exit = dict(mutated.get("time_exit") or {})

        for tweak in tweaks:
            factor = self._rng.uniform(0.7, 1.3)
            if tweak in {"stop_ticks", "target_ticks"}:
                current = bracket_exit.get(tweak, PARAM_BOUNDS[tweak].default)
                bracket_exit[tweak] = self._bounded_value(tweak, current * factor)
            elif tweak == "max_bars_in_trade":
                current = time_exit.get(tweak, PARAM_BOUNDS[tweak].default)
                time_exit[tweak] = self._bounded_value(tweak, current * factor)
            elif tweak == "multi_level_distance_ticks":
                current = mutated.get(tweak, PARAM_BOUNDS[tweak].default)
                mutated[tweak] = self._bounded_value(tweak, current * factor)

        if mutated.get("confirmation_signals") and self._rng.random() < 0.5:
            sigs: list[dict[str, Any]] = []
            for signal in mutated["confirmation_signals"]:
                sig = dict(signal)
                sig["threshold"] = round(
                    float(self._bounded_value("confirmation_threshold", sig.get("threshold", 0.6) * self._rng.uniform(0.8, 1.2))),
                    2,
                )
                sigs.append(sig)
            mutated["confirmation_signals"] = sigs

        mutated["bracket_exit"] = self._normalize_bracket_exit(bracket_exit)
        mutated["time_exit"] = self._normalize_time_exit(time_exit)
        return mutated

    def _add_confirmation(self, data: dict[str, Any]) -> dict[str, Any]:
        mutated = dict(data)
        signals = [dict(signal) for signal in mutated.get("confirmation_signals", [])]
        existing_ids = {signal.get("signal_id") for signal in signals}
        available = [signal for signal in AVAILABLE_SIGNALS if signal not in existing_ids]

        if available and len(signals) < 3:
            signals.append(
                {
                    "signal_id": self._rng.choice(available),
                    "threshold": round(self._rng.uniform(0.3, 0.9), 2),
                    "operator": self._rng.choice(["gt", "lt", "active"]),
                }
            )

        mutated["confirmation_signals"] = signals
        return mutated

    def _remove_confirmation(self, data: dict[str, Any]) -> dict[str, Any]:
        mutated = dict(data)
        signals = [dict(signal) for signal in mutated.get("confirmation_signals", [])]
        if signals:
            signals.pop(self._rng.randrange(len(signals)))
        mutated["confirmation_signals"] = signals
        return mutated

    def _swap_exit(self, data: dict[str, Any]) -> dict[str, Any]:
        mutated = dict(data)
        bracket_exit = mutated.get("bracket_exit")
        level_exit = mutated.get("level_exit")

        if bracket_exit is not None and level_exit is None:
            if self._rng.random() < 0.5:
                mutated["level_exit"] = self._random_level_exit()
            else:
                mutated["bracket_exit"] = self._normalize_bracket_exit(dict(bracket_exit))
        elif bracket_exit is None and level_exit is not None:
            mutated["bracket_exit"] = self._random_bracket_exit()
        elif bracket_exit is not None and level_exit is not None:
            if self._rng.random() < 0.5:
                mutated["level_exit"] = None
                mutated["bracket_exit"] = self._normalize_bracket_exit(dict(bracket_exit))
            else:
                mutated["level_exit"] = self._random_level_exit()
        else:
            mutated["bracket_exit"] = self._random_bracket_exit()

        return self._ensure_exit_guard(mutated)

    def _crossover(self, child_data: dict[str, Any], other_parent: StrategyConfig) -> dict[str, Any]:
        other_data = other_parent.model_dump(mode="json", exclude_none=False)
        for key in (
            "level_target",
            "approach_direction",
            "timing_filter",
            "confirmation_signals",
            "multi_level_distance_ticks",
            "require_multi_level",
            "bracket_exit",
            "level_exit",
            "time_exit",
        ):
            if self._rng.random() < 0.5:
                child_data[key] = other_data.get(key)
        return self._ensure_exit_guard(child_data)

    def _random_config_data(self) -> dict[str, Any]:
        data = {
            "level_target": self._rng.choice(list(LevelTarget)).value,
            "approach_direction": self._rng.choice(list(ApproachDirection)).value,
            "timing_filter": self._rng.choice(list(TimingFilter)).value,
            "confirmation_signals": [],
            "multi_level_distance_ticks": self._rng.randint(2, 30),
            "require_multi_level": self._rng.random() < 0.3,
            "bracket_exit": self._random_bracket_exit(),
            "level_exit": self._random_level_exit() if self._rng.random() < 0.35 else None,
            "time_exit": self._random_time_exit(),
            "generation": 0,
            "parent_hash": None,
            "mutation_type": MutationType.RANDOM.value,
        }

        if self._rng.random() < 0.45:
            data = self._add_confirmation(data)
        if self._rng.random() < 0.2:
            data = self._add_confirmation(data)
        return self._ensure_exit_guard(data)

    def _make_random_config(self, generation: int = 0, parent_hash: Optional[str] = None) -> StrategyConfig:
        data = self._random_config_data()
        data["generation"] = generation
        data["parent_hash"] = parent_hash
        return self._config_from_data(data)

    def _random_bracket_exit(self) -> dict[str, Any]:
        stop = self._rng.randint(int(PARAM_BOUNDS["stop_ticks"].min_val), 80)
        target_upper = min(int(PARAM_BOUNDS["target_ticks"].max_val), stop * 4)
        target = self._rng.randint(stop + 5, max(stop + 5, target_upper))
        return self._normalize_bracket_exit({"stop_ticks": stop, "target_ticks": target})

    def _random_level_exit(self) -> dict[str, Any]:
        return {
            "exit_at_next_zone": self._rng.choice([True, False]),
            "trail_to_zone_boundary": self._rng.choice([True, False]),
        }

    def _random_time_exit(self) -> dict[str, Any]:
        return self._normalize_time_exit(
            {
                "max_bars_in_trade": self._rng.randint(
                    int(PARAM_BOUNDS["max_bars_in_trade"].min_val),
                    int(PARAM_BOUNDS["max_bars_in_trade"].max_val),
                ),
                "session_end_flatten": True,
            }
        )

    def _finalize_child(
        self,
        child_data: dict[str, Any],
        parent: StrategyConfig,
        mutation_type: MutationType,
    ) -> StrategyConfig:
        finalized = dict(child_data)
        finalized = self._ensure_exit_guard(finalized)
        finalized["bracket_exit"] = self._normalize_bracket_exit(finalized.get("bracket_exit"))
        finalized["time_exit"] = self._normalize_time_exit(finalized.get("time_exit"))
        finalized["generation"] = parent.generation + 1
        finalized["parent_hash"] = parent.config_hash()
        finalized["mutation_type"] = mutation_type.value
        return self._config_from_data(finalized)

    def _config_from_data(self, data: dict[str, Any]) -> StrategyConfig:
        config = StrategyConfig.model_validate(data)
        clamped = clamp_config(config)
        normalized = clamped.model_dump(mode="json", exclude_none=False)
        normalized["bracket_exit"] = self._normalize_bracket_exit(normalized.get("bracket_exit"))
        normalized["time_exit"] = self._normalize_time_exit(normalized.get("time_exit"))
        normalized = self._ensure_exit_guard(normalized)
        return StrategyConfig.model_validate(normalized)

    def _normalize_bracket_exit(self, bracket_exit: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if bracket_exit is None:
            return None

        stop = self._bounded_value("stop_ticks", bracket_exit.get("stop_ticks", PARAM_BOUNDS["stop_ticks"].default))
        target_floor = stop + 5
        target = self._bounded_value(
            "target_ticks",
            max(bracket_exit.get("target_ticks", stop * 2), target_floor),
        )
        if target <= stop:
            target = min(int(PARAM_BOUNDS["target_ticks"].max_val), stop + 5)
        rr_ratio = round(target / max(stop, 1), 2)
        rr_ratio = float(self._bounded_value("rr_ratio", rr_ratio))
        return {"stop_ticks": stop, "target_ticks": target, "rr_ratio": rr_ratio}

    def _normalize_time_exit(self, time_exit: Optional[dict[str, Any]]) -> dict[str, Any]:
        time_exit = dict(time_exit or {})
        return {
            "max_bars_in_trade": self._bounded_value(
                "max_bars_in_trade",
                time_exit.get("max_bars_in_trade", PARAM_BOUNDS["max_bars_in_trade"].default),
            ),
            "session_end_flatten": bool(time_exit.get("session_end_flatten", True)),
        }

    def _ensure_exit_guard(self, data: dict[str, Any]) -> dict[str, Any]:
        guarded = dict(data)
        if guarded.get("bracket_exit") is None and guarded.get("level_exit") is None:
            guarded["bracket_exit"] = self._random_bracket_exit()
        if guarded.get("level_exit") is not None:
            guarded["level_exit"] = LevelExit.model_validate(guarded["level_exit"]).model_dump(mode="json")
        return guarded

    def _bounded_value(self, param: str, value: float) -> int | float:
        bound = PARAM_BOUNDS[param]
        clamped = max(bound.min_val, min(bound.max_val, value))
        return int(round(clamped)) if bound.dtype is int else float(clamped)


__all__ = ["AVAILABLE_SIGNALS", "MutationEngine", "MutationType"]
