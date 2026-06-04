# Backtesting with Options Data

Historical replay architecture for NQ options-aware strategies. Combines Massive.com flat
files, FlashAlpha historical API, and Databento MBO data into a synchronized replay engine.

Companion files:
- `async-pipeline.md` — live pipeline architecture (same OptionsState used in replay)
- `api-clients.md` — `FlashAlphaClient` historical mode configuration
- `../signal-interfaces.md` — `BaseStrategy` interface and `OptionsState` schema

---

## Data Sources

| Source | What it provides | Format | Cost |
|--------|-----------------|--------|------|
| Massive.com flat files | Minute OHLC, tick trades, daily CSVs | CSV/Parquet on S3 | Included with subscription |
| FlashAlpha historical API | GEX, exposure levels, 0DTE, volatility at any timestamp | REST with `?at=` | Alpha tier ($149/mo) |
| Databento MBO | NQ futures tick data, L3 order book | DBN binary (nanosecond) | $179/mo |

The primary clock is NQ bars from Databento. Options data is forward-filled from the
nearest available snapshot at or before each NQ bar timestamp.

---

## Historical Data Download

Download everything before running a parameter sweep. API calls during optimization
destroy throughput.

### Databento NQ Data

```python
import databento as db
from pathlib import Path
from datetime import date


async def download_nq_data(
    start: date,
    end: date,
    output_dir: Path,
    schema: str = "ohlcv-1m",  # or "mbo" for tick-level
) -> Path:
    """
    Download NQ continuous contract data from Databento.
    Saves as .dbn.zst file for repeated replay without re-downloading.

    schema options:
    - "ohlcv-1m": 1-minute bars (fast, good for parameter sweeps)
    - "ohlcv-5m": 5-minute bars
    - "mbo": full tick-level MBO (slow, use for signal validation only)
    """
    client = db.Historical()  # reads DATABENTO_API_KEY from env
    output_path = output_dir / f"NQ_{start}_{end}_{schema}.dbn.zst"

    if output_path.exists():
        return output_path  # already downloaded

    dataset = await client.timeseries.get_range_async(
        dataset="GLBX.MDP3",
        symbols=["NQ.c.0"],
        schema=schema,
        start=start.isoformat(),
        end=end.isoformat(),
        path=str(output_path),
    )

    return output_path
```

### FlashAlpha Historical Snapshots

```python
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .api_clients import FlashAlphaClient, FAConfig

logger = logging.getLogger("deep6.backtest.download")


async def download_fa_snapshots(
    symbol: str,
    start: datetime,
    end: datetime,
    interval_minutes: int = 5,
    output_dir: Path = Path("data/fa_historical"),
    api_key: str = "",
) -> Path:
    """
    Download FlashAlpha snapshots at regular intervals for a date range.
    Saves as JSONL (one JSON object per line) for fast sequential replay.

    interval_minutes=5 means one snapshot every 5 minutes.
    For a 3-month backtest (65 trading days x 390 min/day / 5) = ~5,070 API calls.
    At 60 req/min, that's ~85 minutes of download time. Run once, cache forever.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol}_{start.date()}_{end.date()}_{interval_minutes}m.jsonl"

    if output_path.exists():
        logger.info("fa_download.cache_hit", extra={"path": str(output_path)})
        return output_path

    config = FAConfig(api_key=api_key, historical_mode=True)
    timestamps = _generate_market_timestamps(start, end, interval_minutes)

    logger.info(
        "fa_download.start",
        extra={"symbol": symbol, "timestamps": len(timestamps), "output": str(output_path)},
    )

    with output_path.open("w") as f:
        async with FlashAlphaClient(config) as fa:
            for i, ts in enumerate(timestamps):
                config.historical_at = ts
                try:
                    snapshot = await fa.get_full_snapshot(symbol)
                    record = {
                        "timestamp": ts.isoformat(),
                        "data": _snapshot_to_dict(snapshot),
                    }
                    f.write(json.dumps(record) + "\n")

                    if i % 100 == 0:
                        logger.info(
                            "fa_download.progress",
                            extra={"done": i, "total": len(timestamps)},
                        )
                except Exception as exc:
                    logger.warning(
                        "fa_download.skip",
                        extra={"timestamp": ts.isoformat(), "error": str(exc)},
                    )
                    # Write null record to preserve timestamp alignment
                    f.write(json.dumps({"timestamp": ts.isoformat(), "data": None}) + "\n")

    logger.info("fa_download.complete", extra={"path": str(output_path)})
    return output_path


def _generate_market_timestamps(
    start: datetime,
    end: datetime,
    interval_minutes: int,
) -> list[datetime]:
    """Generate timestamps during market hours only (9:30 AM - 4:00 PM ET)."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    timestamps = []
    current = start.replace(tzinfo=et)

    while current <= end.replace(tzinfo=et):
        # Skip weekends
        if current.weekday() < 5:
            market_open = current.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = current.replace(hour=16, minute=0, second=0, microsecond=0)
            if market_open <= current <= market_close:
                timestamps.append(current)

        current += timedelta(minutes=interval_minutes)

    return timestamps
```

---

## OptionsBacktestReplay

The core replay engine. Reconstructs `OptionsState` at each NQ bar and calls the strategy.

```python
import asyncio
import logging
import time
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import databento as db
import numpy as np

from .data_shapes import FASnapshot
from .signal_interfaces import OptionsState, DataQuality
from .strategy_interface import BaseStrategy, BarData, TradeSignal

logger = logging.getLogger("deep6.backtest.replay")


@dataclass
class ReplayConfig:
    nq_data_path: Path
    fa_snapshots_path: Path
    symbol: str = "QQQ"           # options symbol (QQQ proxies NQ)
    nq_symbol: str = "NQ.c.0"
    max_forward_fill_minutes: float = 10.0  # max age for options snapshot
    emit_progress_every: int = 500          # log progress every N bars


@dataclass
class ReplayResult:
    trades: list[dict]
    equity_curve: list[tuple[datetime, float]]
    metrics: dict
    bar_count: int
    options_coverage_pct: float  # % of bars with fresh options data


class OptionsBacktestReplay:
    """
    Replays NQ price data synchronized with historical options snapshots.

    Usage:
        replay = OptionsBacktestReplay(config)
        result = await replay.run(strategy=MyStrategy(), initial_capital=100_000)
    """

    def __init__(self, config: ReplayConfig):
        self._config = config
        self._fa_index: Optional[dict[datetime, FASnapshot]] = None

    async def run(
        self,
        strategy: "BaseStrategy",
        initial_capital: float = 100_000.0,
    ) -> ReplayResult:
        """
        Main replay loop. Loads data, iterates bars, calls strategy.evaluate().
        Returns full trade log and equity curve.
        """
        logger.info("replay.start", extra={"config": vars(self._config)})
        start_time = time.monotonic()

        # Load options snapshots into memory index
        self._fa_index = self._load_fa_index(self._config.fa_snapshots_path)
        logger.info("replay.fa_index_loaded", extra={"snapshots": len(self._fa_index)})

        trades: list[dict] = []
        equity_curve: list[tuple[datetime, float]] = []
        capital = initial_capital
        bars_with_options = 0
        bar_count = 0

        # Stream NQ bars from Databento file (no re-download)
        store = db.from_file(str(self._config.nq_data_path))

        for record in store:
            bar_count += 1
            bar_ts = datetime.utcfromtimestamp(record.ts_event / 1e9)

            bar = BarData(
                timestamp=bar_ts,
                open=record.open / 1e9,   # Databento prices are in fixed-point
                high=record.high / 1e9,
                low=record.low / 1e9,
                close=record.close / 1e9,
                volume=record.volume,
            )

            # Look up nearest options snapshot (no look-ahead)
            options_state = self._get_options_state(bar_ts)
            if options_state.quality != DataQuality.STALE:
                bars_with_options += 1

            # Call strategy
            signal = strategy.evaluate(bar, options_state)

            if signal is not None:
                trade = self._execute_signal(signal, bar, capital)
                trades.append(trade)
                capital += trade["pnl"]

            equity_curve.append((bar_ts, capital))

            if bar_count % self._config.emit_progress_every == 0:
                logger.info(
                    "replay.progress",
                    extra={"bars": bar_count, "capital": round(capital, 2)},
                )

        elapsed = time.monotonic() - start_time
        coverage = bars_with_options / bar_count if bar_count > 0 else 0.0

        logger.info(
            "replay.complete",
            extra={
                "bars": bar_count,
                "trades": len(trades),
                "elapsed_s": round(elapsed, 2),
                "options_coverage_pct": round(coverage * 100, 1),
            },
        )

        return ReplayResult(
            trades=trades,
            equity_curve=equity_curve,
            metrics=self._compute_metrics(trades, equity_curve, initial_capital),
            bar_count=bar_count,
            options_coverage_pct=coverage * 100,
        )

    def _load_fa_index(self, path: Path) -> dict[datetime, FASnapshot]:
        """
        Load JSONL snapshot file into a dict keyed by timestamp.
        Uses datetime objects for fast lookup.
        """
        import json
        index = {}
        with path.open() as f:
            for line in f:
                record = json.loads(line)
                if record["data"] is None:
                    continue
                ts = datetime.fromisoformat(record["timestamp"])
                index[ts] = FASnapshot(**record["data"])
        return index

    def _get_options_state(self, bar_ts: datetime) -> OptionsState:
        """
        Find the most recent options snapshot at or before bar_ts.
        Forward-fills up to max_forward_fill_minutes.
        Returns STALE state if no snapshot found within the window.
        """
        if not self._fa_index:
            return self._stale_state(bar_ts)

        max_age = self._config.max_forward_fill_minutes * 60  # seconds

        # Binary search would be faster, but dict lookup with sorted keys is fine
        # for typical backtest sizes (< 100K snapshots)
        best_ts = None
        best_snapshot = None

        for snap_ts, snapshot in self._fa_index.items():
            if snap_ts <= bar_ts:
                age = (bar_ts - snap_ts).total_seconds()
                if age <= max_age:
                    if best_ts is None or snap_ts > best_ts:
                        best_ts = snap_ts
                        best_snapshot = snapshot

        if best_snapshot is None:
            return self._stale_state(bar_ts)

        age_seconds = (bar_ts - best_ts).total_seconds()
        quality = DataQuality.FRESH if age_seconds < 60 else DataQuality.DEGRADED
        conviction = 1.0 if quality == DataQuality.FRESH else max(0.3, 1.0 - age_seconds / max_age)

        return OptionsState(
            timestamp=bar_ts,
            gamma_flip=best_snapshot.gamma_flip,
            call_wall=best_snapshot.call_wall,
            put_wall=best_snapshot.put_wall,
            net_gex=best_snapshot.net_gex,
            net_dex=None,
            net_vex=None,
            net_chex=None,
            regime=best_snapshot.regime,
            zero_dte_expected_move=best_snapshot.zero_dte_expected_move,
            zero_dte_pin_score=best_snapshot.zero_dte_pin_score,
            atm_iv=best_snapshot.atm_iv,
            put_call_ratio=None,
            unusual_flow_score=None,
            quality=quality,
            fa_age_seconds=age_seconds,
            massive_age_seconds=float("inf"),  # Massive not available in historical
            conviction_multiplier=conviction,
        )

    def _stale_state(self, ts: datetime) -> OptionsState:
        return OptionsState(
            timestamp=ts,
            gamma_flip=None, call_wall=None, put_wall=None,
            net_gex=None, net_dex=None, net_vex=None, net_chex=None,
            regime=None, zero_dte_expected_move=None, zero_dte_pin_score=None,
            atm_iv=None, put_call_ratio=None, unusual_flow_score=None,
            quality=DataQuality.STALE,
            fa_age_seconds=float("inf"),
            massive_age_seconds=float("inf"),
            conviction_multiplier=0.0,
        )

    def _execute_signal(self, signal: "TradeSignal", bar: "BarData", capital: float) -> dict:
        """Simplified fill model. Replace with realistic slippage model for production."""
        fill_price = bar.close  # market order at close
        contracts = signal.contracts
        pnl = (fill_price - signal.entry_price) * contracts * 20  # NQ = $20/point

        return {
            "timestamp": bar.timestamp.isoformat(),
            "direction": signal.direction,
            "entry_price": signal.entry_price,
            "fill_price": fill_price,
            "contracts": contracts,
            "pnl": pnl,
            "regime": signal.regime_at_entry,
        }

    def _compute_metrics(
        self,
        trades: list[dict],
        equity_curve: list[tuple[datetime, float]],
        initial_capital: float,
    ) -> dict:
        if not trades:
            return {"total_trades": 0}

        pnls = np.array([t["pnl"] for t in trades])
        equity = np.array([e[1] for e in equity_curve])

        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_dd = float(drawdown.min())

        return {
            "total_trades": len(trades),
            "win_rate": float(len(wins) / len(pnls)),
            "avg_win": float(wins.mean()) if len(wins) > 0 else 0.0,
            "avg_loss": float(losses.mean()) if len(losses) > 0 else 0.0,
            "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) > 0 else float("inf"),
            "total_pnl": float(pnls.sum()),
            "max_drawdown_pct": max_dd * 100,
            "sharpe": _compute_sharpe(pnls),
            "final_capital": float(equity[-1]),
            "return_pct": (float(equity[-1]) - initial_capital) / initial_capital * 100,
        }


def _compute_sharpe(pnls: np.ndarray, risk_free: float = 0.0) -> float:
    if len(pnls) < 2:
        return 0.0
    excess = pnls - risk_free
    std = excess.std()
    if std == 0:
        return 0.0
    return float(excess.mean() / std * np.sqrt(252))
```

---

## Strategy Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .signal_interfaces import OptionsState


@dataclass
class BarData:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class TradeSignal:
    direction: str          # "long" | "short"
    entry_price: float
    stop_price: float
    target_price: float
    contracts: int
    confidence: float       # 0.0 - 1.0
    regime_at_entry: Optional[str]  # options regime at signal time


class BaseStrategy(ABC):
    """
    Implement this interface for any options-aware NQ strategy.
    evaluate() is called once per bar during replay.
    """

    @abstractmethod
    def evaluate(self, bar: BarData, options: OptionsState) -> Optional[TradeSignal]:
        """
        Return a TradeSignal to enter a trade, or None to do nothing.
        Must NOT look ahead — only use bar and options data from current or past bars.
        """
        ...

    def on_trade_closed(self, trade: dict) -> None:
        """Optional hook called after each trade closes."""
        pass
```

---

## Synchronization Strategy

The core challenge: NQ ticks arrive at nanosecond resolution; options snapshots arrive
every 5 minutes. The replay engine handles this with forward-fill and a staleness window.

```
NQ bars (1-min):  |-----|-----|-----|-----|-----|-----|-----|-----|
                  9:30  9:31  9:32  9:33  9:34  9:35  9:36  9:37

FA snapshots:     |                   |                   |
                  9:30                9:35                9:40

Forward-fill:     [9:30 snap]         [9:35 snap]
                  used for 9:30-9:34  used for 9:35-9:39
```

Rules:
1. Options snapshot timestamp must be `<=` NQ bar timestamp (no look-ahead).
2. If the nearest snapshot is older than `max_forward_fill_minutes`, mark state as STALE.
3. Strategy should check `options.quality` before using options signals.

```python
# In your strategy:
def evaluate(self, bar: BarData, options: OptionsState) -> Optional[TradeSignal]:
    # Don't trade on stale options data
    if options.quality == DataQuality.STALE:
        return None

    # Scale conviction by data freshness
    base_confidence = self._compute_base_confidence(bar)
    adjusted_confidence = base_confidence * options.conviction_multiplier

    if adjusted_confidence < 0.6:
        return None

    # Use options context
    if options.regime == "negative" and bar.close < options.gamma_flip:
        return TradeSignal(
            direction="short",
            entry_price=bar.close,
            stop_price=bar.close + 10,
            target_price=bar.close - 20,
            contracts=1,
            confidence=adjusted_confidence,
            regime_at_entry=options.regime,
        )

    return None
```

---

## Parameter Sweep with Optuna

```python
import optuna
import asyncio
from pathlib import Path


def run_backtest_sync(params: dict, config: ReplayConfig) -> float:
    """
    Synchronous wrapper for Optuna. Each trial runs a full replay.
    Returns negative Sharpe (Optuna minimizes by default).
    """
    strategy = OptionsAwareStrategy(
        wall_proximity_threshold=params["wall_proximity_threshold"],
        flow_intensity_threshold=params["flow_intensity_threshold"],
        regime_weight=params["regime_weight"],
        min_conviction=params["min_conviction"],
    )

    replay = OptionsBacktestReplay(config)
    result = asyncio.run(replay.run(strategy))

    # Penalize low trade count (avoid overfitting to few trades)
    if result.metrics["total_trades"] < 20:
        return 0.0

    return result.metrics["sharpe"]


def optimize_parameters(
    config: ReplayConfig,
    n_trials: int = 200,
    n_jobs: int = 4,  # parallel trials (ProcessPoolExecutor)
) -> optuna.Study:
    """
    Run Optuna parameter sweep. Uses ProcessPoolExecutor for parallelism.
    Each process runs its own asyncio.run() — no shared event loop.
    """
    study = optuna.create_study(direction="maximize")

    def objective(trial: optuna.Trial) -> float:
        params = {
            "wall_proximity_threshold": trial.suggest_float("wall_proximity_threshold", 0.001, 0.02),
            "flow_intensity_threshold": trial.suggest_float("flow_intensity_threshold", 0.3, 0.9),
            "regime_weight": trial.suggest_float("regime_weight", 0.1, 1.0),
            "min_conviction": trial.suggest_float("min_conviction", 0.4, 0.8),
        }
        return run_backtest_sync(params, config)

    study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs)
    return study
```

---

## Walk-Forward Validation

Don't trust in-sample optimization. Walk-forward splits prevent overfitting.

```python
from datetime import date, timedelta
from dataclasses import dataclass


@dataclass
class WalkForwardWindow:
    train_start: date
    train_end: date
    test_start: date
    test_end: date


def generate_walk_forward_windows(
    start: date,
    end: date,
    train_months: int = 3,
    test_months: int = 1,
) -> list[WalkForwardWindow]:
    """
    Generate rolling walk-forward windows.

    Example with train=3, test=1:
    Window 1: train Jan-Mar, test Apr
    Window 2: train Feb-Apr, test May
    Window 3: train Mar-May, test Jun
    ...
    """
    windows = []
    current = start

    while True:
        train_end = current + timedelta(days=30 * train_months)
        test_end = train_end + timedelta(days=30 * test_months)

        if test_end > end:
            break

        windows.append(WalkForwardWindow(
            train_start=current,
            train_end=train_end,
            test_start=train_end,
            test_end=test_end,
        ))
        current += timedelta(days=30)  # roll forward 1 month

    return windows


async def run_walk_forward(
    windows: list[WalkForwardWindow],
    base_config: ReplayConfig,
    n_optuna_trials: int = 100,
) -> list[dict]:
    """
    For each window: optimize on train, evaluate on test.
    Returns per-window test results.
    """
    results = []

    for i, window in enumerate(windows):
        print(f"Window {i+1}/{len(windows)}: train {window.train_start} to {window.train_end}")

        # Build train config
        train_config = ReplayConfig(
            nq_data_path=base_config.nq_data_path,
            fa_snapshots_path=base_config.fa_snapshots_path,
        )

        # Optimize on train window
        study = optimize_parameters(train_config, n_trials=n_optuna_trials)
        best_params = study.best_params

        # Evaluate on test window (no optimization)
        test_config = ReplayConfig(
            nq_data_path=base_config.nq_data_path,
            fa_snapshots_path=base_config.fa_snapshots_path,
        )
        strategy = OptionsAwareStrategy(**best_params)
        replay = OptionsBacktestReplay(test_config)
        result = await replay.run(strategy)

        results.append({
            "window": i + 1,
            "train_start": window.train_start.isoformat(),
            "test_start": window.test_start.isoformat(),
            "best_params": best_params,
            "test_sharpe": result.metrics.get("sharpe"),
            "test_return_pct": result.metrics.get("return_pct"),
            "test_trades": result.metrics.get("total_trades"),
            "options_coverage_pct": result.options_coverage_pct,
        })

    return results
```

---

## Performance Optimization

### Pre-load FA Index as Sorted Array

For large backtests (> 1M bars), dict lookup is fast enough. But if you're running
thousands of Optuna trials, pre-sorting the index into a numpy array enables binary search:

```python
import numpy as np
from datetime import datetime


class FAIndexFast:
    """
    Sorted numpy array index for O(log n) options snapshot lookup.
    Use when running > 1,000 Optuna trials on the same dataset.
    """

    def __init__(self, snapshots: dict[datetime, FASnapshot]):
        sorted_items = sorted(snapshots.items(), key=lambda x: x[0])
        self._timestamps = np.array([ts.timestamp() for ts, _ in sorted_items])
        self._snapshots = [snap for _, snap in sorted_items]

    def get_nearest(self, bar_ts: datetime, max_age_seconds: float) -> Optional[FASnapshot]:
        bar_unix = bar_ts.timestamp()

        # Find rightmost timestamp <= bar_ts
        idx = np.searchsorted(self._timestamps, bar_unix, side="right") - 1

        if idx < 0:
            return None

        age = bar_unix - self._timestamps[idx]
        if age > max_age_seconds:
            return None

        return self._snapshots[idx]
```

### Avoid Pandas in the Hot Loop

```python
# SLOW: pandas operations in per-bar loop
for record in store:
    df = pd.DataFrame([record])  # allocation every bar
    close = df["close"].iloc[0]

# FAST: direct attribute access
for record in store:
    close = record.close / 1e9  # Databento fixed-point
```

### Parallelize Independent Optuna Trials

Each Optuna trial is independent. Use `n_jobs > 1` in `study.optimize()` with
`ProcessPoolExecutor` under the hood. Each process gets its own Python interpreter
and event loop — no shared state issues.

```python
# Safe: each process runs asyncio.run() independently
study.optimize(objective, n_trials=200, n_jobs=8)

# UNSAFE: sharing asyncio objects across processes
# Don't pass asyncio.Queue, aiohttp.ClientSession, etc. to worker processes
```

---

## Limitations and Mitigations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| FlashAlpha historical is Alpha tier ($149/mo) | Cost | Download in bulk once per quarter; cache aggressively |
| Massive flat files don't include GEX | Missing computed signal | Use FlashAlpha for GEX; Massive for raw chain/flow |
| Options data frequency mismatch (5min vs 1ms) | Stale signals | Forward-fill with staleness decay; don't trade on STALE state |
| Survivorship bias in options chains | Overfit to current strikes | Use historical snapshots only; never query current chain for past dates |
| FlashAlpha historical API rate limits | Slow download | Batch downloads off-hours; use `RateLimiter(tokens_per_second=1.0)` |
| Databento MBO schema is large (GB/day) | Storage cost | Use `ohlcv-1m` for sweeps; MBO only for signal validation |
| No Massive.com WebSocket in historical | Missing real-time flow | Use Massive flat files for historical flow; accept lower fidelity |

---

## Checklist Before Running a Sweep

- [ ] All historical data downloaded and cached locally (no API calls during sweep)
- [ ] FA snapshots cover the full date range with < 10% null records
- [ ] NQ data file verified: `databento.from_file(path)` opens without error
- [ ] `max_forward_fill_minutes` set appropriately for your bar size (10min for 1-min bars)
- [ ] Strategy `evaluate()` checks `options.quality` before using options signals
- [ ] Walk-forward windows defined (don't optimize on the full dataset)
- [ ] `n_jobs` set to `cpu_count - 1` (leave one core for the OS)
- [ ] Results saved to disk before interpreting (Optuna study is serializable)
