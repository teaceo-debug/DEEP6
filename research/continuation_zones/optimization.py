from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random
from types import SimpleNamespace

import pandas as pd

from .backtest_engine import BacktestConfig, BacktestEngine, Trade

try:  # pragma: no cover - exercised when optuna is installed
    import optuna
except ModuleNotFoundError:  # pragma: no cover - fallback is covered instead
    class _FallbackTrialPruned(Exception):
        pass

    class _FallbackTrialState:
        COMPLETE = "COMPLETE"
        PRUNED = "PRUNED"
        FAIL = "FAIL"

    class _FallbackTrial:
        def __init__(self, number: int, rng: Random):
            self.number = number
            self._rng = rng
            self.params: dict[str, object] = {}
            self.user_attrs: dict[str, object] = {}
            self.state = _FallbackTrialState.FAIL
            self.value: float | None = None

        def suggest_float(self, name: str, low: float, high: float, step: float | None = None) -> float:
            if step is None:
                value = self._rng.uniform(low, high)
            else:
                steps = int(round((high - low) / step))
                value = low + (self._rng.randint(0, steps) * step)
                value = round(value, 10)
            self.params[name] = value
            return float(value)

        def suggest_int(self, name: str, low: int, high: int, step: int = 1) -> int:
            steps = int((high - low) / step)
            value = low + (self._rng.randint(0, steps) * step)
            self.params[name] = value
            return int(value)

        def suggest_categorical(self, name: str, choices: list[object]) -> object:
            value = choices[self._rng.randrange(len(choices))]
            self.params[name] = value
            return value

        def set_user_attr(self, name: str, value: object) -> None:
            self.user_attrs[name] = value

    class _FallbackStudy:
        def __init__(self, seed: int | None):
            self._rng = Random(seed)
            self.trials: list[_FallbackTrial] = []

        def optimize(self, objective, n_trials: int) -> None:
            for number in range(n_trials):
                trial = _FallbackTrial(number=number, rng=self._rng)
                try:
                    trial.value = float(objective(trial))
                    trial.state = _FallbackTrialState.COMPLETE
                except _FallbackTrialPruned:
                    trial.state = _FallbackTrialState.PRUNED
                self.trials.append(trial)

    class _FallbackTPESampler:
        def __init__(self, seed: int | None = None):
            self.seed = seed

    class _FallbackMedianPruner:
        def __init__(self, n_warmup_steps: int = 0):
            self.n_warmup_steps = n_warmup_steps

    def _fallback_create_study(*, direction: str, sampler: _FallbackTPESampler | None = None, pruner=None) -> _FallbackStudy:
        del direction, pruner
        return _FallbackStudy(seed=None if sampler is None else sampler.seed)

    optuna = SimpleNamespace(
        Trial=_FallbackTrial,
        TrialPruned=_FallbackTrialPruned,
        create_study=_fallback_create_study,
        samplers=SimpleNamespace(TPESampler=_FallbackTPESampler),
        pruners=SimpleNamespace(MedianPruner=_FallbackMedianPruner),
        trial=SimpleNamespace(TrialState=_FallbackTrialState),
    )


@dataclass(frozen=True)
class WalkForwardSplit:
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp

    @classmethod
    def from_df(cls, df: pd.DataFrame, is_months: int = 8, oos_months: int = 4) -> "WalkForwardSplit":
        """Create split from a DataFrame's date range."""
        if df.empty:
            raise ValueError("cannot create walk-forward split from empty DataFrame")

        if "ts_event" in df.columns:
            timestamps = pd.to_datetime(df["ts_event"], utc=True)
        else:
            timestamps = pd.to_datetime(df.index, utc=True)

        start = pd.Timestamp(timestamps.min())
        is_end = start + pd.DateOffset(months=is_months)
        oos_end = is_end + pd.DateOffset(months=oos_months)
        return cls(is_start=start, is_end=is_end, oos_start=is_end, oos_end=oos_end)


@dataclass(frozen=True)
class OptimizationResult:
    params: dict
    is_sharpe: float
    oos_sharpe: float
    is_win_rate: float
    oos_win_rate: float
    is_trades: int
    oos_trades: int
    is_total_pnl: float
    oos_total_pnl: float
    fitness: float
    is_overfit: bool
    trial_number: int


def _compute_fitness(trades: list[Trade]) -> tuple[float, float, float, int]:
    """Returns (sharpe, win_rate, total_pnl, n_trades)."""
    if len(trades) < 10:
        return -999.0, 0.0, 0.0, len(trades)

    pnls = [trade.pnl_dollars for trade in trades]
    mean_pnl = sum(pnls) / len(pnls)
    std_pnl = (sum((pnl - mean_pnl) ** 2 for pnl in pnls) / len(pnls)) ** 0.5
    sharpe = (mean_pnl / std_pnl * (252 ** 0.5)) if std_pnl > 0 else 0.0
    win_rate = sum(1 for pnl in pnls if pnl > 0) / len(pnls)
    total_pnl = sum(pnls)
    return sharpe, win_rate, total_pnl, len(pnls)


def _suggest_config(trial: optuna.Trial) -> BacktestConfig:
    return BacktestConfig(
        small_body_ratio=trial.suggest_float("small_body_ratio", 0.20, 0.70, step=0.05),
        min_zone_ticks=trial.suggest_int("min_zone_ticks", 1, 5),
        max_zone_age_bars_5m=trial.suggest_int("max_zone_age_bars_5m", 20, 300, step=20),
        max_zone_age_bars_15m=trial.suggest_int("max_zone_age_bars_15m", 10, 100, step=10),
        max_touch_count=trial.suggest_int("max_touch_count", 1, 3),
        min_score=trial.suggest_int("min_score", 4, 7),
        stop_ticks=trial.suggest_int("stop_ticks", 4, 16, step=2),
        target_ticks=trial.suggest_int("target_ticks", 8, 24, step=2),
        breakeven_ticks=trial.suggest_int("breakeven_ticks", 4, 10, step=2),
        trail_ticks=trial.suggest_int("trail_ticks", 0, 8, step=2),
        trail_activation_ticks=trial.suggest_int("trail_activation_ticks", 6, 14, step=2),
        rth_only=trial.suggest_categorical("rth_only", [True, False]),
    )


class ContinuationZoneOptimizer:
    def __init__(
        self,
        df_5m: pd.DataFrame,
        df_15m: pd.DataFrame,
        split: WalkForwardSplit,
        n_trials: int = 200,
        min_oos_trades: int = 200,
        seed: int = 42,
    ):
        self.df_5m = self._normalize_frame(df_5m)
        self.df_15m = self._normalize_frame(df_15m)
        self.split = split
        self.n_trials = n_trials
        self.min_oos_trades = min_oos_trades
        self.seed = seed

        self.df_5m_is = self._slice_frame(self.df_5m, split.is_start, split.is_end)
        self.df_5m_oos = self._slice_frame(self.df_5m, split.oos_start, split.oos_end)
        self.df_15m_is = self._slice_frame(self.df_15m, split.is_start, split.is_end)
        self.df_15m_oos = self._slice_frame(self.df_15m, split.oos_start, split.oos_end)

    def optimize(self) -> list[OptimizationResult]:
        """Run Optuna sweep. Returns top-10 OOS results sorted by fitness desc."""
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=self.seed),
            pruner=optuna.pruners.MedianPruner(n_warmup_steps=5),
        )
        study.optimize(self._objective, n_trials=self.n_trials)

        completed_results: list[OptimizationResult] = []
        for trial in study.trials:
            if trial.state != optuna.trial.TrialState.COMPLETE or trial.value is None:
                continue
            oos_sharpe = float(trial.user_attrs["oos_sharpe"])
            completed_results.append(
                OptimizationResult(
                    params=dict(trial.params),
                    is_sharpe=float(trial.user_attrs["is_sharpe"]),
                    oos_sharpe=oos_sharpe,
                    is_win_rate=float(trial.user_attrs["is_win_rate"]),
                    oos_win_rate=float(trial.user_attrs["oos_win_rate"]),
                    is_trades=int(trial.user_attrs["is_trades"]),
                    oos_trades=int(trial.user_attrs["oos_trades"]),
                    is_total_pnl=float(trial.user_attrs["is_total_pnl"]),
                    oos_total_pnl=float(trial.user_attrs["oos_total_pnl"]),
                    fitness=float(trial.value),
                    is_overfit=float(trial.user_attrs["is_sharpe"]) > 2 * oos_sharpe,
                    trial_number=trial.number,
                )
            )

        completed_results.sort(key=lambda result: (result.fitness, result.oos_sharpe, result.oos_total_pnl), reverse=True)
        return completed_results[:10]

    def save_results(self, results: list[OptimizationResult], output_dir: Path) -> None:
        """Save top10_param_sets.csv to output_dir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, object]] = []
        for rank, result in enumerate(results[:10], start=1):
            row: dict[str, object] = {
                "rank": rank,
                "trial_number": result.trial_number,
                "fitness": result.fitness,
                "oos_sharpe": result.oos_sharpe,
                "oos_win_rate": result.oos_win_rate,
                "oos_trades": result.oos_trades,
                "oos_total_pnl": result.oos_total_pnl,
                "is_sharpe": result.is_sharpe,
                "is_win_rate": result.is_win_rate,
                "is_trades": result.is_trades,
                "is_overfit": result.is_overfit,
            }
            row.update(result.params)
            rows.append(row)

        columns = [
            "rank",
            "trial_number",
            "fitness",
            "oos_sharpe",
            "oos_win_rate",
            "oos_trades",
            "oos_total_pnl",
            "is_sharpe",
            "is_win_rate",
            "is_trades",
            "is_overfit",
            "small_body_ratio",
            "min_zone_ticks",
            "max_zone_age_bars_5m",
            "max_zone_age_bars_15m",
            "max_touch_count",
            "min_score",
            "stop_ticks",
            "target_ticks",
            "breakeven_ticks",
            "trail_ticks",
            "trail_activation_ticks",
            "rth_only",
        ]
        pd.DataFrame(rows, columns=columns).to_csv(output_dir / "top10_param_sets.csv", index=False)

    def _objective(self, trial: optuna.Trial) -> float:
        config = self._suggest_config(trial)
        engine = BacktestEngine(config)

        is_trades = engine.run(self.df_5m_is, self.df_15m_is)
        is_sharpe, is_wr, is_pnl, is_n = self._compute_fitness(is_trades)

        oos_trades = engine.run(self.df_5m_oos, self.df_15m_oos)
        oos_sharpe, oos_wr, oos_pnl, oos_n = self._compute_fitness(oos_trades)

        trial.set_user_attr("is_sharpe", is_sharpe)
        trial.set_user_attr("oos_sharpe", oos_sharpe)
        trial.set_user_attr("is_win_rate", is_wr)
        trial.set_user_attr("oos_win_rate", oos_wr)
        trial.set_user_attr("is_trades", is_n)
        trial.set_user_attr("oos_trades", oos_n)
        trial.set_user_attr("is_total_pnl", is_pnl)
        trial.set_user_attr("oos_total_pnl", oos_pnl)

        if oos_n < self.min_oos_trades:
            raise optuna.TrialPruned()

        return oos_sharpe * oos_wr

    @staticmethod
    def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()
        if "ts_event" in frame.columns:
            frame = frame.set_index("ts_event")
        if not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, utc=True)
        elif frame.index.tz is None:
            frame.index = frame.index.tz_localize("UTC")
        else:
            frame.index = frame.index.tz_convert("UTC")
        frame.index.name = "ts_event"
        return frame.sort_index()

    @staticmethod
    def _slice_frame(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        return df.loc[(df.index >= start) & (df.index < end)].copy()

    @staticmethod
    def _compute_fitness(trades: list[Trade]) -> tuple[float, float, float, int]:
        return _compute_fitness(trades)

    @staticmethod
    def _suggest_config(trial: optuna.Trial) -> BacktestConfig:
        return _suggest_config(trial)


__all__ = [
    "ContinuationZoneOptimizer",
    "OptimizationResult",
    "WalkForwardSplit",
    "_compute_fitness",
    "_suggest_config",
]
