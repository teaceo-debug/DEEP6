from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from research.continuation_zones.data_loader import (
    apply_rth_filter,
    build_ohlcv,
    get_nq_5m,
    load_1m_bars,
)


def _make_1m_frame(start: str, periods: int = 5, tz: str = "UTC") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=periods, freq="1min", tz=tz, name="ts_event")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0][:periods],
            "high": [101.0, 102.5, 103.0, 104.0, 105.0][:periods],
            "low": [99.5, 100.5, 101.5, 102.5, 103.5][:periods],
            "close": [100.5, 102.0, 102.5, 103.5, 104.5][:periods],
            "volume": [10, 20, 30, 40, 50][:periods],
        },
        index=index,
    )


def test_build_ohlcv_aggregates_5m_correctly() -> None:
    df_1m = _make_1m_frame("2026-01-05 14:30:00+00:00", periods=5)

    result = build_ohlcv(df_1m, "5min")

    assert len(result) == 1
    row = result.iloc[0]
    assert row["open"] == 100.0
    assert row["high"] == 105.0
    assert row["low"] == 99.5
    assert row["close"] == 104.5
    assert row["volume"] == 150


def test_apply_rth_filter_keeps_only_regular_session_bars() -> None:
    eastern_index = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-01-05 08:00:00", tz="America/New_York"),
            pd.Timestamp("2026-01-05 09:30:00", tz="America/New_York"),
            pd.Timestamp("2026-01-05 15:59:00", tz="America/New_York"),
            pd.Timestamp("2026-01-05 16:00:00", tz="America/New_York"),
            pd.Timestamp("2026-01-10 10:00:00", tz="America/New_York"),
        ],
        name="ts_event",
    ).tz_convert("UTC")
    df = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5],
            "high": [1, 2, 3, 4, 5],
            "low": [1, 2, 3, 4, 5],
            "close": [1, 2, 3, 4, 5],
            "volume": [1, 1, 1, 1, 1],
        },
        index=eastern_index,
    )

    result = apply_rth_filter(df)
    local_result = result.index.tz_convert("America/New_York")

    assert list(local_result.strftime("%Y-%m-%d %H:%M")) == [
        "2026-01-05 09:30",
        "2026-01-05 15:59",
    ]


def test_load_1m_bars_writes_and_reads_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "nq.parquet"
    source_df = _make_1m_frame("2026-01-05 14:30:00+00:00", periods=3)

    mock_store = type("MockStore", (), {"to_df": lambda self, **_: source_df})()
    mock_client = type(
        "MockClient",
        (),
        {"timeseries": type("MockTimeseries", (), {"get_range": lambda self, **_: mock_store})()},
    )()

    with patch("research.continuation_zones.data_loader.db.Historical", return_value=mock_client) as historical:
        downloaded = load_1m_bars(api_key="test-key", cache_path=cache_path, force_download=True)

    assert cache_path.exists()
    assert historical.call_count == 1
    pd.testing.assert_frame_equal(downloaded, source_df, check_freq=False)

    with patch("research.continuation_zones.data_loader.db.Historical") as historical:
        cached = load_1m_bars(cache_path=cache_path)

    historical.assert_not_called()
    pd.testing.assert_frame_equal(cached, source_df, check_freq=False)


def test_get_nq_5m_raises_without_api_key_or_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "missing.parquet"

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="DATABENTO_API_KEY"):
            get_nq_5m(cache_path=cache_path)
