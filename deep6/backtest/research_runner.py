from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import duckdb
from pydantic import BaseModel, Field

from deep6.backtest.config import BacktestConfig
from deep6.backtest.session import ReplaySession
from deep6.config import Config
from deep6.state.shared import SharedState


class ReplayRunRequest(BaseModel):
    dataset: str = "GLBX.MDP3"
    symbol: str = "NQ.c.0"
    start: datetime
    end: datetime
    tf_list: list[str] = Field(default_factory=lambda: ["1m"])
    duckdb_path: str = "backtest_results.duckdb"
    git_sha: str = ""
    fill_model: str = "perfect"
    tick_size: float = 0.25
    dry_run: bool = False


class ReplayRunResult(BaseModel):
    run_id: str
    status: str
    started_at: float
    completed_at: float
    duckdb_path: str
    total_bars: int
    rows: list[dict]
    metrics: dict[str, int]
    summary: dict[str, int]
    request: dict


class ResearchRunner:
    """Small replay-backed orchestration layer for Phase 1 backtest runs."""

    async def run(self, request: ReplayRunRequest) -> ReplayRunResult:
        started_at = asyncio.get_running_loop().time()
        state = self._build_state(request)
        event_source = self._build_event_source(request)
        config = BacktestConfig(
            dataset=request.dataset,
            symbol=request.symbol,
            start=request.start,
            end=request.end,
            tf_list=request.tf_list,
            duckdb_path=request.duckdb_path,
            git_sha=request.git_sha or self._request_hash(request),
            fill_model=request.fill_model,
            tick_size=request.tick_size,
        )

        async with ReplaySession(config, state, event_source=event_source) as session:
            await session.run()
            run_id = session.run_id
            metrics = {
                "bars_written": session.bars_written,
                "dom_signal_fires": session.dom_signal_fires,
                "scorer_signal_fires": session.scorer_signal_fires,
                "trades_written": session.trades_written,
                "trades_closed": session.trades_closed,
                "trades_truncated": session.trades_truncated,
            }

        rows, summary = self._load_rows(config.duckdb_path, run_id)
        completed_at = asyncio.get_running_loop().time()
        return ReplayRunResult(
            run_id=run_id,
            status="complete",
            started_at=started_at,
            completed_at=completed_at,
            duckdb_path=config.duckdb_path,
            total_bars=len(rows),
            rows=rows,
            metrics=metrics,
            summary=summary,
            request=request.model_dump(mode="json"),
        )

    def _build_state(self, request: ReplayRunRequest) -> SharedState:
        safe_stem = Path(request.duckdb_path).stem
        cfg = Config(
            rithmic_user="",
            rithmic_password="",
            rithmic_system_name="",
            rithmic_uri="",
            db_path=str(Path(request.duckdb_path).with_name(f"{safe_stem}.sqlite")),
        )
        return SharedState.build(cfg)

    def _build_event_source(self, request: ReplayRunRequest):
        if request.dry_run or not self._has_databento_key():
            base_ns = int(request.start.timestamp() * 1e9)
            return iter(self._synthetic_rth_stream(base_ns=base_ns, n_bars=max(3, self._minutes_span(request))))
        return None

    def _has_databento_key(self) -> bool:
        import os

        return bool(os.environ.get("DATABENTO_API_KEY", ""))

    def _minutes_span(self, request: ReplayRunRequest) -> int:
        seconds = max(60, int((request.end - request.start).total_seconds()))
        return max(1, seconds // 60)

    def _request_hash(self, request: ReplayRunRequest) -> str:
        payload = json.dumps(request.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()[:12]

    def _load_rows(self, duckdb_path: str, run_id: str) -> tuple[list[dict], dict[str, int]]:
        con = duckdb.connect(duckdb_path)
        try:
            raw_rows = con.execute(
                """
                SELECT bar_ts, tf, open, high, low, close, volume, signal_flags, score, tier, direction
                FROM backtest_bars
                WHERE run_id = ?
                ORDER BY bar_ts, tf, bar_key
                """,
                [run_id],
            ).fetchall()
            rows = [
                {
                    "bar_ts": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                    "tf": row[1],
                    "open": row[2],
                    "high": row[3],
                    "low": row[4],
                    "close": row[5],
                    "volume": row[6],
                    "signal_flags": int(row[7]),
                    "score": float(row[8]),
                    "tier": row[9],
                    "direction": row[10],
                }
                for row in raw_rows
            ]
            summary_rows = con.execute(
                "SELECT tier, COUNT(*) FROM backtest_bars WHERE run_id = ? GROUP BY tier",
                [run_id],
            ).fetchall()
            summary = {tier: int(count) for tier, count in summary_rows}
            return rows, summary
        finally:
            con.close()

    def _synthetic_rth_stream(self, base_ns: int, n_bars: int = 3) -> list[_SyntheticMBOEvent]:
        events: list[_SyntheticMBOEvent] = []
        step_ns = 100_000_000
        t = base_ns
        mid_price = 21000.0

        for i in range(10):
            events.append(_SyntheticMBOEvent(t, "A", "B", _wire_price(mid_price - (i + 1) * 0.25), 50))
            t += step_ns
            events.append(_SyntheticMBOEvent(t, "A", "A", _wire_price(mid_price + (i + 1) * 0.25), 50))
            t += step_ns

        for bar_idx in range(n_bars):
            for i in range(3):
                events.append(_SyntheticMBOEvent(t, "C", "A", _wire_price(mid_price + (i + 1) * 0.25), 40))
                t += step_ns
            for i in range(3):
                events.append(_SyntheticMBOEvent(t, "A", "B", _wire_price(mid_price - (i + 1) * 0.25), 80))
                t += step_ns
            for i in range(5):
                events.append(_SyntheticMBOEvent(t, "C", "B", _wire_price(mid_price - (i + 1) * 0.25), 30))
                t += step_ns
            for i in range(5):
                events.append(_SyntheticMBOEvent(t, "A", "B", _wire_price(mid_price - (i + 1) * 0.25), 30))
                t += step_ns
            for i in range(10):
                side = "A" if i % 2 == 0 else "B"
                events.append(_SyntheticMBOEvent(t, "T", side, _wire_price(mid_price), 5))
                t += step_ns
            t = base_ns + (bar_idx + 1) * 60_000_000_000 + step_ns

        events.append(_SyntheticMBOEvent(base_ns + n_bars * 60_000_000_000 + 5_000_000_000, "T", "A", _wire_price(mid_price), 5))
        return events


class _SyntheticMBOEvent:
    def __init__(self, ts_event: int, action: str, side: str, price: int, size: int, instrument_id: int = 1) -> None:
        self.ts_event = ts_event
        self.action = action
        self.side = side
        self.price = price
        self.size = size
        self.instrument_id = instrument_id


def _wire_price(price_dollars: float) -> int:
    return int(round(price_dollars * 1e9))
