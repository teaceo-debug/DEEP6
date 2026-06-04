from __future__ import annotations

from deep6.backtest.mutation_engine import MutationEngine, MutationType
from deep6.backtest.param_bounds import validate_config
from deep6.backtest.strategy_config import LevelTarget, StrategyConfig


def test_mutate_sets_generation_and_parent_hash():
    engine = MutationEngine(seed=42)
    parent = StrategyConfig(level_target=LevelTarget.LVN)

    child = engine.mutate(parent)

    assert child.generation == parent.generation + 1
    assert child.parent_hash == parent.config_hash()
    assert child.mutation_type in {mutation.value for mutation in MutationType}


def test_generate_initial_population_is_diverse():
    engine = MutationEngine(seed=42)

    population = engine.generate_initial_population(10)
    hashes = {config.config_hash() for config in population}

    assert len(population) == 10
    assert len(hashes) >= 8


def test_mutations_stay_within_param_bounds():
    engine = MutationEngine(seed=42)
    parent = StrategyConfig()

    children = [engine.mutate(parent) for _ in range(20)]

    assert all(validate_config(child) == [] for child in children)
    assert all((child.bracket_exit is not None) or (child.level_exit is not None) for child in children)


def test_select_mutation_type_returns_enum_member():
    engine = MutationEngine(seed=42)
    history = [
        {"mutation_type": MutationType.TWEAK_PARAMS.value, "oos_fitness": 0.8},
        {"mutation_type": MutationType.SWAP_LEVEL_TARGET.value, "oos_fitness": 0.6},
        {"mutation_type": MutationType.ADD_CONFIRMATION.value, "oos_fitness": 0.2},
        {"mutation_type": MutationType.TWEAK_PARAMS.value, "oos_fitness": 0.7},
        {"mutation_type": MutationType.RANDOM.value, "oos_fitness": 0.1},
    ]

    selected = engine.select_mutation_type(history)

    assert isinstance(selected, MutationType)


def test_crossover_produces_valid_child_with_lineage():
    engine = MutationEngine(seed=7)
    parent = StrategyConfig(level_target=LevelTarget.LVN)
    other_parent = StrategyConfig(level_target=LevelTarget.HVN, generation=3)

    child = engine.mutate(parent, mutation_type=MutationType.CROSSOVER, other_parent=other_parent)

    assert child.generation == parent.generation + 1
    assert child.parent_hash == parent.config_hash()
    assert validate_config(child) == []
