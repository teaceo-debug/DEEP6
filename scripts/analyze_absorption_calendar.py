#!/usr/bin/env python3
from __future__ import annotations

import calendar
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data" / "backtests" / "signal_events.csv"
MINUTE_CSV = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
OUT_DIR = ROOT / "data" / "backtests" / "analysis"
OUT_TXT = OUT_DIR / "absorption_calendar_session_report.txt"

TICK_SIZE = 0.25
POINT_VALUE = 20.0
COMMISSION = 0.70
FORWARD_WINDOW = 5
NY_TZ = "America/New_York"
FOMC_DATES = [
    "2025-01-29",
    "2025-03-19",
    "2025-05-07",
    "2025-06-18",
    "2025-07-30",
    "2025-09-17",
    "2025-10-29",
    "2025-12-10",
    "2026-01-28",
    "2026-03-18",
    "2026-04-29",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-09",
]


@dataclass(frozen=True)
class Stats:
    n: int
    wr: float
    avg_pnl: float
    med_pnl: float


def third_friday(year: int, month: int) -> pd.Timestamp:
    cal = calendar.monthcalendar(year, month)
    friday = calendar.FRIDAY
    fridays = [week[friday] for week in cal if week[friday] != 0]
    return pd.Timestamp(year=year, month=month, day=fridays[2])


def op_ex_week_bounds(year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    tf = third_friday(year, month)
    monday = tf - pd.Timedelta(days=tf.weekday())
    friday = monday + pd.Timedelta(days=4)
    return monday.normalize(), friday.normalize()


def rollover_week_bounds(year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    tf = third_friday(year, month)
    roll_date = tf - pd.Timedelta(days=8)  # Thursday before OpEx Friday
    monday = roll_date - pd.Timedelta(days=roll_date.weekday())
    friday = monday + pd.Timedelta(days=4)
    return monday.normalize(), friday.normalize()


def compute_pnl(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    direction = pd.to_numeric(events["direction"], errors="coerce")
    price_move = pd.to_numeric(events[f"fwd_close_{FORWARD_WINDOW}b"], errors="coerce") - pd.to_numeric(
        events["bar_close"], errors="coerce"
    )
    events["pnl_5b"] = direction * price_move * POINT_VALUE - COMMISSION
    events["win_5b"] = events["pnl_5b"] > 0
    return events.dropna(subset=["pnl_5b"])


def load_absorption_events() -> pd.DataFrame:
    events = pd.read_csv(EVENTS_CSV, low_memory=False)
    events = events[events["category"] == "absorption"].copy()
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.normalize()
    events["bar_ts"] = pd.to_datetime(events["bar_ts"], utc=True, errors="coerce").dt.tz_convert(NY_TZ)
    events["month"] = events["session_date"].dt.month
    events["month_name"] = events["session_date"].dt.strftime("%b")
    events["quarter"] = events["session_date"].dt.to_period("Q").astype(str)
    events["weekday"] = events["session_date"].dt.day_name()
    events["day"] = events["session_date"].dt.day
    events["week_of_month"] = ((events["day"] - 1) // 7) + 1
    return compute_pnl(events)


def classify_profile(day: pd.DataFrame) -> str:
    bin_size = 1.0
    prices = np.round(pd.to_numeric(day["close"], errors="coerce") / bin_size) * bin_size
    vols = pd.to_numeric(day["volume"], errors="coerce").fillna(0.0)
    prof = pd.DataFrame({"price": prices, "volume": vols}).groupby("price", as_index=False)["volume"].sum()
    prof = prof.sort_values("price").reset_index(drop=True)
    if len(prof) < 5 or prof["volume"].sum() <= 0:
        return "unknown"

    smooth = prof["volume"].rolling(3, center=True, min_periods=1).mean()
    weights = smooth.to_numpy(dtype=float)
    px = prof["price"].to_numpy(dtype=float)
    mean = np.average(px, weights=weights)
    std = np.sqrt(np.average((px - mean) ** 2, weights=weights))
    skew = 0.0 if std == 0 else np.average(((px - mean) / std) ** 3, weights=weights)
    poc_idx = int(np.argmax(weights))
    low_px = float(day["low"].min())
    high_px = float(day["high"].max())
    close_pos = 0.5 if high_px == low_px else (float(day["close"].iloc[-1]) - low_px) / (high_px - low_px)
    poc_pos = 0.5 if px[-1] == px[0] else (px[poc_idx] - px[0]) / (px[-1] - px[0])

    peaks: list[int] = []
    peak_floor = weights.max() * 0.75
    for i in range(1, len(weights) - 1):
        if weights[i] >= weights[i - 1] and weights[i] >= weights[i + 1] and weights[i] >= peak_floor:
            peaks.append(i)

    if len(peaks) >= 2:
        best_pair: tuple[int, int] | None = None
        best_sep = -1
        for i in range(len(peaks)):
            for j in range(i + 1, len(peaks)):
                a, b = peaks[i], peaks[j]
                sep = abs(px[b] - px[a])
                if sep > best_sep:
                    best_sep = sep
                    best_pair = (a, b)
        if best_pair:
            a, b = best_pair
            valley = weights[a : b + 1].min()
            smaller_peak = min(weights[a], weights[b])
            full_range = max(px[-1] - px[0], bin_size)
            if best_sep >= 0.40 * full_range and valley <= 0.40 * smaller_peak:
                return "double_distribution"

    if abs(skew) <= 0.25 and abs(close_pos - 0.5) <= 0.20 and abs(poc_pos - 0.5) <= 0.20:
        return "D"
    if skew > 0.10 and close_pos >= 0.55:
        return "P"
    if skew < -0.10 and close_pos <= 0.45:
        return "b"
    return "P" if close_pos > 0.5 else "b"


def load_daily_context() -> pd.DataFrame:
    bars = pd.read_csv(MINUTE_CSV, usecols=["ts_event", "open", "high", "low", "close", "volume"])
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True, errors="coerce").dt.tz_convert(NY_TZ)
    bars["session_date"] = bars["ts_event"].dt.normalize().dt.tz_localize(None)
    bars["time"] = bars["ts_event"].dt.strftime("%H:%M")
    rth = bars[(bars["time"] >= "09:30") & (bars["time"] <= "15:59")].copy()

    daily = (
        rth.groupby("session_date")
        .agg(
            session_open=("open", "first"),
            session_high=("high", "max"),
            session_low=("low", "min"),
            session_close=("close", "last"),
            session_volume=("volume", "sum"),
        )
        .reset_index()
        .sort_values("session_date")
    )
    daily["prev_close"] = daily["session_close"].shift(1)
    daily["range_points"] = daily["session_high"] - daily["session_low"]
    daily["range_pct_close"] = daily["range_points"] / daily["session_close"]
    daily["gap_points"] = daily["session_open"] - daily["prev_close"]
    daily["gap_ticks"] = (daily["gap_points"].abs() / TICK_SIZE).round(2)
    daily["gap_flag"] = np.where(daily["gap_ticks"] > 50, "gap_gt_50t", "no_gap")
    daily["range_quartile"] = pd.qcut(
        daily["range_pct_close"],
        q=4,
        labels=["ranging_q1", "q2", "q3", "trending_q4"],
        duplicates="drop",
    )
    daily["trend_bucket"] = np.where(daily["range_quartile"] == "trending_q4", "trending_q4", "other")
    daily.loc[daily["range_quartile"] == "ranging_q1", "trend_bucket"] = "ranging_q1"

    shapes = []
    for session_date, grp in rth.groupby("session_date"):
        shapes.append({"session_date": session_date, "profile_shape": classify_profile(grp)})
    daily = daily.merge(pd.DataFrame(shapes), on="session_date", how="left")
    return daily


def add_calendar_flags(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    fomc_dates = pd.to_datetime(FOMC_DATES)
    after_dates = []
    unique_days = pd.Index(sorted(events["session_date"].unique()))
    for d in fomc_dates:
        later = unique_days[unique_days > d]
        if len(later):
            after_dates.append(later[0])
    events["fomc_flag"] = "non_fomc"
    events.loc[events["session_date"].isin(fomc_dates), "fomc_flag"] = "fomc_day"
    events.loc[events["session_date"].isin(after_dates), "fomc_flag"] = "day_after_fomc"

    events["is_opex_week"] = False
    events["is_rollover_week"] = False
    for year in sorted(events["session_date"].dt.year.unique()):
        for month in range(1, 13):
            op_start, op_end = op_ex_week_bounds(year, month)
            op_mask = (events["session_date"] >= op_start) & (events["session_date"] <= op_end)
            events.loc[op_mask, "is_opex_week"] = True
            if month in {3, 6, 9, 12}:
                ro_start, ro_end = rollover_week_bounds(year, month)
                ro_mask = (events["session_date"] >= ro_start) & (events["session_date"] <= ro_end)
                events.loc[ro_mask, "is_rollover_week"] = True

    events["month_bucket"] = "late_month"
    events.loc[events["week_of_month"] == 1, "month_bucket"] = "first_week"
    events.loc[events["week_of_month"].isin([2, 3]), "month_bucket"] = "mid_month"
    events.loc[events["is_opex_week"], "month_bucket"] = "opex_week"
    return events


def stat_line(df: pd.DataFrame) -> Stats:
    pnl = df["pnl_5b"].dropna()
    if pnl.empty:
        return Stats(0, np.nan, np.nan, np.nan)
    return Stats(len(pnl), float((pnl > 0).mean()), float(pnl.mean()), float(pnl.median()))


def grouped_stats(df: pd.DataFrame, col: str, order: list[str] | None = None) -> pd.DataFrame:
    rows = []
    for key, grp in df.groupby(col, dropna=False):
        s = stat_line(grp)
        rows.append(
            {
                col: key,
                "N": s.n,
                "WR%": s.wr * 100.0,
                "Avg$": s.avg_pnl,
                "Med$": s.med_pnl,
            }
        )
    out = pd.DataFrame(rows)
    if order is not None and not out.empty:
        out[col] = pd.Categorical(out[col], categories=order, ordered=True)
        out = out.sort_values(col)
    else:
        out = out.sort_values("WR%", ascending=False)
    return out.reset_index(drop=True)


def format_df(df: pd.DataFrame, index_name: str) -> str:
    if df.empty:
        return "  <no rows>"
    display = df.copy()
    if index_name in display.columns:
        display[index_name] = display[index_name].astype(str)
    for col in ["WR%", "Avg$", "Med$"]:
        if col in display.columns:
            display[col] = display[col].map(lambda x: f"{x:,.2f}")
    return display.to_string(index=False)


def quarter_weekday_table(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (quarter, weekday), grp in events.groupby(["quarter", "weekday"]):
        s = stat_line(grp)
        rows.append({"Quarter": quarter, "Weekday": weekday, "N": s.n, "WR%": s.wr * 100.0})
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    out = pd.DataFrame(rows)
    out["Weekday"] = pd.Categorical(out["Weekday"], categories=order, ordered=True)
    return out.sort_values(["Quarter", "Weekday"]).reset_index(drop=True)


def summary_lines(events: pd.DataFrame) -> list[str]:
    total = stat_line(events)
    date_min = events["session_date"].min().date()
    date_max = events["session_date"].max().date()
    best_month = grouped_stats(events, "month_name").iloc[0]
    worst_month = grouped_stats(events, "month_name").iloc[-1]
    best_bucket = grouped_stats(events, "month_bucket").sort_values("WR%", ascending=False).iloc[0]
    trend = grouped_stats(events[events["trend_bucket"].isin(["ranging_q1", "trending_q4"])], "trend_bucket")
    gap = grouped_stats(events, "gap_flag")
    return [
        f"Absorption sample: N={total.n}, WR={total.wr*100:.2f}%, AvgPnL=${total.avg_pnl:.2f}, Range={date_min}..{date_max}",
        f"Best month: {best_month['month_name']} (N={int(best_month['N'])}, WR={best_month['WR%']:.2f}%)",
        f"Worst month: {worst_month['month_name']} (N={int(worst_month['N'])}, WR={worst_month['WR%']:.2f}%)",
        f"Best month-bucket: {best_bucket['month_bucket']} (N={int(best_bucket['N'])}, WR={best_bucket['WR%']:.2f}%)",
        f"Ranging vs trending WR: {trend.iloc[0]['trend_bucket']}={trend.iloc[0]['WR%']:.2f}% / {trend.iloc[1]['trend_bucket']}={trend.iloc[1]['WR%']:.2f}%",
        f"Gap-day WR spread: gap_gt_50t={float(gap.loc[gap['gap_flag']=='gap_gt_50t', 'WR%'].iloc[0]):.2f}% vs no_gap={float(gap.loc[gap['gap_flag']=='no_gap', 'WR%'].iloc[0]):.2f}%",
    ]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_absorption_events()
    daily = load_daily_context()
    events = add_calendar_flags(events).merge(daily, on="session_date", how="left")

    month_order = [calendar.month_abbr[m] for m in range(1, 13)]
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    bucket_order = ["first_week", "mid_month", "opex_week", "late_month"]
    fomc_order = ["fomc_day", "day_after_fomc", "non_fomc"]
    profile_order = ["P", "b", "D", "double_distribution", "unknown"]

    sections: list[tuple[str, pd.DataFrame]] = [
        ("1) Monthly seasonality", grouped_stats(events, "month_name", month_order)),
        ("2) Week-of-month / OpEx effect", grouped_stats(events, "month_bucket", bucket_order)),
        ("3) Day-of-week", grouped_stats(events, "weekday", weekday_order)),
        ("3b) Day-of-week by quarter", quarter_weekday_table(events)),
        ("4) FOMC / post-FOMC", grouped_stats(events, "fomc_flag", fomc_order)),
        (
            "5) Contract rollover week",
            grouped_stats(
                events.assign(rollover_flag=np.where(events["is_rollover_week"], "rollover_week", "non_rollover")),
                "rollover_flag",
                ["rollover_week", "non_rollover"],
            ),
        ),
        (
            "6) Trending vs ranging sessions",
            grouped_stats(events[events["trend_bucket"].isin(["ranging_q1", "trending_q4"])], "trend_bucket", ["ranging_q1", "trending_q4"]),
        ),
        ("7) Gap days", grouped_stats(events, "gap_flag", ["gap_gt_50t", "no_gap"])),
        ("8) Volume profile shape", grouped_stats(events, "profile_shape", profile_order)),
    ]

    lines = ["ABSORPTION CALENDAR + SESSION-TYPE ANALYSIS", "=" * 48, *summary_lines(events), ""]
    for title, df in sections:
        lines.append(title)
        lines.append("-" * len(title))
        lines.append(format_df(df, df.columns[0]))
        lines.append("")

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved report -> {OUT_TXT}")


if __name__ == "__main__":
    main()
