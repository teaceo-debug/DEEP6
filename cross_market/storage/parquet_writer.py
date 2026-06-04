"""PyArrow Parquet writer with schema enforcement and partitioning."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pyarrow as pa
import pyarrow.parquet as pq


class ParquetWriter:
    """Write typed data to Parquet files with append support."""

    def __init__(
        self,
        base_dir: str | Path,
        schema: Optional[pa.Schema] = None,
        compression: str = "snappy",
    ):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._schema = schema
        self._compression = compression

    def write(self, filename: str, rows: List[dict]) -> Path:
        """Write rows to a Parquet file, appending if it exists."""
        if not rows:
            return self._base / filename
        path = self._base / filename
        table = pa.Table.from_pylist(rows, schema=self._schema)
        if path.exists():
            existing = pq.read_table(path)
            table = pa.concat_tables([existing, table])
        pq.write_table(table, path, compression=self._compression)
        return path

    def read(self, filename: str) -> pa.Table:
        """Read a Parquet file back as a PyArrow Table."""
        path = self._base / filename
        if not path.exists():
            raise FileNotFoundError(f"No parquet file at {path}")
        return pq.read_table(path)

    def row_count(self, filename: str) -> int:
        """Return the number of rows in a Parquet file."""
        path = self._base / filename
        if not path.exists():
            return 0
        meta = pq.read_metadata(path)
        return meta.num_rows
