"""Store for trade outcomes — links predictions to realized P&L for calibration."""
from __future__ import annotations

from pathlib import Path
from typing import List

from cross_market.storage.parquet_writer import ParquetWriter


class OutcomeStore:
    """Append-only store for realized outcomes tied to prediction timestamps."""

    def __init__(self, base_dir: str | Path = "data/cross_market/outcomes"):
        self._writer = ParquetWriter(base_dir)

    def store(self, outcomes: List[dict]) -> Path:
        """Store a batch of outcomes. Each dict: timestamp_ns, price_at_signal, price_30s, price_60s, realized_pnl, etc."""
        return self._writer.write("outcomes.parquet", outcomes)

    def load_all(self) -> List[dict]:
        """Load all stored outcomes as list of dicts."""
        try:
            table = self._writer.read("outcomes.parquet")
            return table.to_pylist()
        except FileNotFoundError:
            return []

    def count(self) -> int:
        return self._writer.row_count("outcomes.parquet")
