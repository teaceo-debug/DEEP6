"""BacktestConfig — pydantic v2 model + YAML loader.

Phase 13-01 T-13-01-09. Lightweight runtime configuration for a replay
session. YAML-loadable so sweeps can stamp out configs programmatically.

Fields are deliberately minimal for phase 13 (MBO-only, perfect fills).
Phase 14 expands ``fill_model`` to a Literal that includes slippage and
latency models.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class BacktestConfig(BaseModel):
    """Replay run configuration. Serialisable to/from YAML."""

    dataset: str = Field(..., description="Databento dataset, e.g. GLBX.MDP3")
    symbol: str = Field(..., description="Continuous symbol, e.g. NQ.c.0")
    start: datetime
    end: datetime
    tf_list: list[str] = Field(default_factory=lambda: ["1m", "5m"])
    duckdb_path: str = "backtest_results.duckdb"
    git_sha: str = ""
    fill_model: Literal["perfect"] = "perfect"
    tick_size: float = 0.25

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BacktestConfig":
        """Load a BacktestConfig from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Dump this config to a YAML file."""
        data = self.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=True)
