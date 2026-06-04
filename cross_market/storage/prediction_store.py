"""Store for LLM predictions — maps assessment to timestamps for outcome tracking."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from cross_market.storage.parquet_writer import ParquetWriter


class PredictionStore:
    """Append-only store for LLM assessments keyed by timestamp."""

    def __init__(self, base_dir: str | Path = "data/cross_market/predictions"):
        self._writer = ParquetWriter(base_dir)

    def store(self, predictions: List[dict]) -> Path:
        """Store a batch of predictions. Each dict should have timestamp_ns, pattern, confidence, etc."""
        return self._writer.write("predictions.parquet", predictions)

    def load_all(self) -> List[dict]:
        """Load all stored predictions as list of dicts."""
        try:
            table = self._writer.read("predictions.parquet")
            return table.to_pylist()
        except FileNotFoundError:
            return []

    def count(self) -> int:
        return self._writer.row_count("predictions.parquet")
