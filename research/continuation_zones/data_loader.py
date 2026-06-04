"""NQ OHLCV data acquisition via Databento.

Downloads 1-minute bars, resamples to 5m/15m, applies RTH filter, caches as parquet.
"""
from __future__ import annotations

import os
from datetime import time
from pathlib import Path

import pandas as pd

try:
    import databento as db
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without Databento installed
    db = None

SYMBOL = "NQ.c.0"
STYPE_IN = "continuous"
SCHEMA = "ohlcv-1m"
START_DATE = "2025-05-25"
END_DATE = "2026-05-25"
RTH_START = time(9, 30)
RTH_END = time(16, 0)
CACHE_PATH = Path("data/nq_ohlcv_1m_2025-2026.parquet")
DATASET = "GLBX.MDP3"
PRICE_COLUMNS = ["open", "high", "low", "close"]
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def write_ohlcv_cache(df: pd.DataFrame, cache_path: Path) -> None:
    """Persist OHLCV cache without requiring a network install of parquet engines.

    Parquet is preferred when pyarrow/fastparquet is available. In lean research
    environments where those optional wheels are not installed, fall back to a
    pandas pickle at the requested path so --skip-download local runs can still
    complete from the CSV source without downloading anything.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(cache_path)
    except ImportError:
        df.to_pickle(cache_path)


def read_ohlcv_cache(cache_path: Path) -> pd.DataFrame:
    """Read OHLCV cache written by write_ohlcv_cache."""
    cache_path = Path(cache_path)
    try:
        return pd.read_parquet(cache_path)
    except ImportError:
        return pd.read_pickle(cache_path)


def _resolve_api_key(api_key: str | None) -> str:
    resolved = api_key or os.environ.get("DATABENTO_API_KEY")
    if resolved:
        return resolved
    raise ValueError(
        "Databento API key required. Pass api_key or set DATABENTO_API_KEY."
    )


def _ensure_ts_event_index(df: pd.DataFrame) -> pd.DataFrame:
    if "ts_event" in df.columns:
        df = df.set_index("ts_event")

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    elif df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    df.index.name = "ts_event"
    return df


def _normalize_price_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in PRICE_COLUMNS:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if PRICE_COLUMNS[0] in normalized.columns:
        max_abs = normalized[PRICE_COLUMNS].abs().max().max()
        if pd.notna(max_abs) and max_abs > 1_000_000:
            normalized[PRICE_COLUMNS] = normalized[PRICE_COLUMNS] / 1e9
    return normalized


def _clean_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = _ensure_ts_event_index(df)
    frame = _normalize_price_columns(frame)
    missing = [column for column in OHLCV_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Databento response missing required columns: {missing}")
    frame = frame.loc[:, OHLCV_COLUMNS].sort_index()
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    return frame


def _download_1m_bars(api_key: str) -> pd.DataFrame:
    if db is None:
        raise ModuleNotFoundError(
            "databento is required for downloading data. Install databento or use cached parquet data."
        )
    client = db.Historical(api_key)
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[SYMBOL],
        stype_in=STYPE_IN,
        schema=SCHEMA,
        start=START_DATE,
        end=END_DATE,
    )
    try:
        df = data.to_df(price_type="float", pretty_ts=True)
    except TypeError:
        df = data.to_df()
    return _clean_ohlcv_frame(df)


def load_1m_bars(
    api_key: str | None = None,
    cache_path: Path = CACHE_PATH,
    force_download: bool = False,
) -> pd.DataFrame:
    """Load 1-minute NQ bars.

    Uses cache if available. Returns DataFrame with columns
    [open, high, low, close, volume] and UTC tz-aware index named ``ts_event``.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not force_download:
        return _clean_ohlcv_frame(read_ohlcv_cache(cache_path))

    resolved_key = _resolve_api_key(api_key)
    try:
        df = _download_1m_bars(resolved_key)
    except Exception as exc:  # pragma: no cover - exercised through mocks
        raise RuntimeError(
            f"Failed to download Databento {SCHEMA} data for {SYMBOL} "
            f"from {START_DATE} to {END_DATE}."
        ) from exc

    write_ohlcv_cache(df, cache_path)
    return df


def build_ohlcv(df_1m: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample 1m bars to target frequency using OHLCV aggregation."""
    if freq not in {"5min", "15min"}:
        raise ValueError("freq must be '5min' or '15min'")

    frame = _clean_ohlcv_frame(df_1m)
    aggregated = frame.resample(freq).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    aggregated = aggregated.dropna(how="any")
    aggregated.index.name = "ts_event"
    return aggregated


def apply_rth_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to RTH only: 09:30-16:00 ET, Mon-Fri, optional market-calendar holidays."""
    frame = _clean_ohlcv_frame(df)
    local_index = frame.index.tz_convert("America/New_York")

    weekday_mask = local_index.weekday < 5
    time_mask = (local_index.time >= RTH_START) & (local_index.time < RTH_END)
    mask = weekday_mask & time_mask

    try:
        import pandas_market_calendars as mcal  # type: ignore

        calendar = mcal.get_calendar("CME_Equity")
        valid_days = calendar.valid_days(
            start_date=local_index.min().date(),
            end_date=local_index.max().date(),
        )
        valid_dates = set(pd.DatetimeIndex(valid_days).tz_localize(None).date)
        holiday_mask = pd.Index(local_index.date).isin(valid_dates)
        mask = mask & holiday_mask
    except ImportError:
        pass

    filtered = frame.loc[mask].copy()
    filtered.index = local_index[mask].tz_convert("UTC")
    filtered.index.name = "ts_event"
    return filtered


def get_nq_5m(
    api_key: str | None = None,
    cache_path: Path = CACHE_PATH,
    force_download: bool = False,
    rth_only: bool = True,
) -> pd.DataFrame:
    """Main entry point: returns 5m NQ bars, RTH-filtered by default."""
    df = build_ohlcv(
        load_1m_bars(
            api_key=api_key,
            cache_path=cache_path,
            force_download=force_download,
        ),
        "5min",
    )
    return apply_rth_filter(df) if rth_only else df


def get_nq_15m(
    api_key: str | None = None,
    cache_path: Path = CACHE_PATH,
    force_download: bool = False,
    rth_only: bool = True,
) -> pd.DataFrame:
    """Main entry point: returns 15m NQ bars, RTH-filtered by default."""
    df = build_ohlcv(
        load_1m_bars(
            api_key=api_key,
            cache_path=cache_path,
            force_download=force_download,
        ),
        "15min",
    )
    return apply_rth_filter(df) if rth_only else df
