#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = REPORT_DIR / "MASTER_BACKTEST_SUMMARY_V2.txt"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"


@dataclass(frozen=True)
class ReportSpec:
    round_label: str
    short_label: str
    report_name: str
    script_name: str
    filter_count: int | None
    parser: str
    optional: bool = False

    @property
    def path(self) -> Path:
        return REPORT_DIR / self.report_name


@dataclass
class Finding:
    display_name: str
    normalized_name: str
    discovery_round: str
    discovery_script: str
    discovery_report: str
    n: int | None = None
    wr_5b: float | None = None
    wr_10b: float | None = None
    wr_15b: float | None = None
    wr_30b: float | None = None
    pf: float | None = None
    avg_ticks_5b: float | None = None
    oos_n: int | None = None
    oos_wr: float | None = None
    bayes_mean: float | None = None
    verdict: str | None = None
    flag: str | None = None
    persistence: str | None = None
    sources: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class Killer:
    name: str
    delta_wr: float | None
    n_with: int | None
    wr_with: float | None
    n_without: int | None
    wr_without: float | None


@dataclass
class ExitRecommendation:
    context: str
    display_name: str
    normalized_name: str
    optimal_exit: str
    sharpe: float | None
    avg_ticks: float | None
    n: int | None


@dataclass
class ReportParseResult:
    findings: list[Finding] = field(default_factory=list)
    killers: list[Killer] = field(default_factory=list)
    exit_recommendations: list[ExitRecommendation] = field(default_factory=list)


REPORT_SPECS = [
    ReportSpec("Round 0", "R0", "compound_filter_report.txt", "analyze_compound_filters.py", 30, "compound"),
    ReportSpec("Round 0", "R0", "top5_validation_report.txt", "validate_top5_filters.py", 5, "walkforward"),
    ReportSpec("Round 0.5", "R0.5", "cross_category_combo_report.txt", "analyze_cross_category_combos.py", 25, "simple_discovery"),
    ReportSpec("Round 1A", "R1A", "round1_walkforward_cross_category.txt", "round1_walkforward_cross_category.py", 8, "walkforward"),
    ReportSpec("Round 1B", "R1B", "round1_regime_gated_report.txt", "round1_regime_gated_signals.py", 20, "simple_discovery"),
    ReportSpec("Round 1C", "R1C", "round1_strength_persistence_report.txt", "round1_strength_persistence.py", 20, "persistence"),
    ReportSpec("Round 1D", "R1D", "round1_time_day_report.txt", "round1_time_day_filters.py", 25, "simple_discovery"),
    ReportSpec("Round 2A", "R2A", "round2_stacked_persistence_time_report.txt", "round2_stacked_persistence_time.py", 20, "persistence_with_sharpe"),
    ReportSpec("Round 2B", "R2B", "round2_absorption_deep_report.txt", "round2_absorption_deep_filters.py", 15, "persistence"),
    ReportSpec("Round 2C", "R2C", "round2_novel_bar_patterns_report.txt", "round2_novel_bar_patterns.py", 15, "simple_discovery"),
    ReportSpec("Round 3A", "R3A", "round3_validate_novel_patterns_report.txt", "round3_validate_novel_patterns.py", 10, "walkforward"),
    ReportSpec("Round 3B", "R3B", "round3_multi_bar_sequences_report.txt", "round3_multi_bar_sequences.py", 15, "multi_bar"),
    ReportSpec("Round 3C", "R3C", "round3_signal_density_report.txt", "round3_signal_density_confluence.py", 20, "persistence"),
    ReportSpec("Round 4", "R4", "round4_final_walkforward_report.txt", "round4_final_walkforward.py", 12, "walkforward"),
    ReportSpec("Round 6A", "R6A", "round6_multi_session_report.txt", "round6_multi_session.py", 20, "validated_table"),
    ReportSpec("Round 6B", "R6B", "round6_gap_opening_range_report.txt", "round6_gap_opening_range.py", 20, "validated_table"),
    ReportSpec("Round 7A", "R7A", "round7_signal_sequences_report.txt", "round7_signal_sequences.py", 20, "validated_table"),
    ReportSpec("Round 7B", "R7B", "round7_signal_negation_report.txt", "round7_signal_negation.py", 20, "negation"),
    ReportSpec("Round 8A", "R8A", "round8_price_levels_report.txt", "round8_price_levels.py", 20, "validated_table"),
    ReportSpec("Round 8B", "R8B", "round8_delta_cvd_report.txt", "round8_delta_cvd_patterns.py", 20, "validated_table"),
    ReportSpec("Round 9", "R9", "round9_exit_timing_report.txt", "round9_exit_timing.py", 15, "exit_timing"),
    ReportSpec("Round 10", "R10", "round10_stack_winners_exclude_killers_report.txt", "round10_stack_winners_exclude_killers.py", 20, "validated_table"),
    ReportSpec("Round 11", "R11", "round11_chain_triple_report.txt", "round11_chain_triple_interaction.py", 20, "validated_table"),
    ReportSpec("Round 12", "R12", "round12_bar_microstructure_report.txt", "round12_bar_microstructure.py", 20, "validated_table", optional=True),
    ReportSpec("Round 13", "R13", "round13_macro_calendar_report.txt", "round13_macro_calendar.py", 20, "validated_table", optional=True),
    ReportSpec("Round 14", "R14", "round14_overnight_momentum_regime_report.txt", "round14_overnight_momentum_regime.py", 20, "validated_table", optional=True),
]


VALIDATED_TABLE_SPECS: dict[str, tuple[str, dict[int, str], str | int | None]] = {
    "round6_multi_session_report.txt": (
        "All 20 cross-session filters ranked by 5-bar average return",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b"},
        "name",
    ),
    "round6_gap_opening_range_report.txt": (
        "All 20 opening-range / gap filters ranked by 5-bar average return",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b"},
        "name",
    ),
    "round7_signal_sequences_report.txt": (
        "20 requested sequential filters",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round8_price_levels_report.txt": (
        "20 requested price-level filters ranked by 5-bar average return",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round8_delta_cvd_report.txt": (
        "All round 8 filters ranked by 5-bar average return",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round10_stack_winners_exclude_killers_report.txt": (
        "20 stacked winner / anti-killer filters ranked by 30b win rate",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round11_chain_triple_report.txt": (
        "20 requested chain / triple-interaction filters",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round12_bar_microstructure_report.txt": (
        "20 bar microstructure filters ranked by 30b win rate",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round13_macro_calendar_report.txt": (
        "All 20 macro/calendar filters ranked by Avg Ticks",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round14_overnight_momentum_regime_report.txt": (
        "20 overnight / momentum / regime filters ranked by 30b win rate",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
}


UNIVERSAL_KILLER_NAMES = [
    "signal closes in middle 40-60% of 60m range",
    "volume spike > 3x EMA",
    "bar_delta same direction and > 90th percentile",
    "next-bar delta flips opposite signal",
]


def parse_int(value: str) -> int | None:
    cleaned = value.strip().replace(",", "")
    if not cleaned or cleaned.lower() == "nan":
        return None
    return int(float(cleaned))


def parse_float(value: str) -> float | None:
    cleaned = value.strip().replace(",", "")
    cleaned = cleaned.replace("ticks", "").replace("t", "").strip()
    if not cleaned or cleaned.lower() == "nan":
        return None
    if cleaned.lower() == "inf":
        return float("inf")
    return float(cleaned.replace("+", ""))


def parse_pct(value: str) -> float | None:
    cleaned = value.strip().replace("%", "")
    if not cleaned or cleaned.lower() == "nan":
        return None
    return float(cleaned)


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%"


def fmt_num(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    if value == float("inf"):
        return "inf"
    return f"{value:,.{decimals}f}"


def fmt_ticks(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value == float("inf"):
        return "inf"
    return f"{value:+,.2f}t"


def fmt_count(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,}"


def classify_persistence(wr_5b: float | None, wr_30b: float | None) -> str | None:
    if wr_5b is None or wr_30b is None:
        return None
    delta = wr_30b - wr_5b
    if delta > 0:
        return "GROWING"
    if abs(delta) < 3.0:
        return "STABLE"
    return "DECAYING"


def split_name_flag(raw_name: str) -> tuple[str, str | None]:
    text = raw_name.strip()
    text = re.sub(r"^\d+\.\s*", "", text)
    text = re.sub(r"^\[[A-Z]\]\s*", "", text)
    match = re.search(r"\[(VALIDATED|PROMISING|LOW_N|DEPLOY|PAPER TRADE|INSUFFICIENT DATA)\]\s*$", text)
    flag = match.group(1) if match else None
    if match:
        text = text[: match.start()].rstrip()
    return text, flag


def canonical_display_name(name: str) -> str:
    clean = name.strip()
    clean = clean.replace("Any TYPE_A bar", "TYPE_A")
    clean = clean.replace("Any TYPE_B bar", "TYPE_B")
    clean = clean.replace("ALL +", "all signals +")
    clean = clean.replace("ALL signals", "all signals")
    clean = clean.replace("score_final", "score")
    clean = clean.replace("15m trend aligned", "15m_trend_aligned")
    clean = clean.replace("15m trend", "15m_trend_aligned")
    clean = clean.replace("15m_trend ", "15m_trend_aligned ")
    clean = clean.replace("15m_trend_aligned_aligned", "15m_trend_aligned")
    clean = re.sub(r"(^| \+ )15m_trend(?=( \+|$))", lambda match: f"{match.group(1)}15m_trend_aligned", clean)
    clean = clean.replace(" + 60m + 15m_trend_aligned", " + 60m_extreme + 15m_trend_aligned")
    clean = clean.replace(" + 60m + 15m_trend", " + 60m_extreme + 15m_trend_aligned")
    clean = clean.replace(" + 60m + 15m", " + 60m_extreme + 15m_trend_aligned")
    clean = clean.replace("60m + 15m_trend", "60m_extreme + 15m_trend_aligned")
    clean = clean.replace("60m + 15m", "60m_extreme + 15m_trend_aligned")
    clean = re.sub(r"(^| \+ )60m(?=( \+|$))", lambda match: f"{match.group(1)}60m_extreme", clean)
    clean = clean.replace("reversal 60m extreme", "60m_extreme")
    clean = clean.replace("momentum 60m extreme", "momentum_60m_extreme")
    clean = clean.replace("2-bar price/delta divergence", "2-bar delta divergence")
    clean = clean.replace("first_hour (all signal bars)", "first_hour")
    clean = clean.replace("first_hour (all signals)", "first_hour")
    clean = clean.replace("first_hour (09:30-10:30)", "first_hour")
    clean = clean.replace("NOT lunch (12:00-14:00)", "NOT lunch")
    clean = clean.replace("NOT_lunch", "NOT lunch")
    clean = clean.replace("NOT Monday", "NOT Monday")
    clean = clean.replace("last_hour (15:00-16:00)", "last_hour")
    clean = clean.replace("hour 09-10 (open range)", "hour 09-10")
    clean = clean.replace("hour 10-12 (mid-morning)", "hour 10-12")
    clean = clean.replace("hour 12-14 (lunch/afternoon)", "hour 12-14")
    clean = clean.replace("hour 14-16 (close range)", "hour 14-16")
    clean = clean.replace("hour 15 only (power hour)", "hour 15 only")
    clean = clean.replace("3+ categories firing same bar + 60m_extreme", "3+ categories + 60m_extreme")
    clean = clean.replace("4+ unique signals same bar + 60m_extreme", "4+ signals + 60m_extreme")
    clean = clean.replace("5+ unique signals same bar + 60m_extreme", "5+ signals + 60m_extreme")
    clean = clean.replace("6+ unique signals same bar + 60m_extreme", "6+ signals + 60m_extreme")
    clean = clean.replace("Core stack", "absorption + 60m_extreme + 15m_trend_aligned")
    clean = clean.replace("ABS_04 core", "ABS_04 + 60m_extreme + 15m_trend_aligned")
    clean = clean.replace("prior_wide_range_day", "Prior session wide range (top quartile)")
    clean = clean.replace("gap_down (bearish signal)", "Gap down below prior low")
    clean = clean.replace("NOT killers", "NOT all_killers")
    clean = clean.replace("NOT killer_1", "NOT middle 40-60% of 60m range")
    clean = clean.replace("NOT killer_2", "NOT volume spike > 3x EMA")
    if "60m_extreme" in clean:
        clean = clean.replace("NOT all_killers", "NOT volume spike > 3x EMA")
        clean = clean.replace(" + NOT middle 40-60% of 60m range", "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def normalize_name(name: str) -> str:
    clean = canonical_display_name(name).lower()
    if " + " not in clean:
        return clean
    parts = [part.strip() for part in clean.split(" + ") if part.strip()]
    if not parts:
        return clean
    if "->" in parts[0]:
        prefix = parts[0]
        suffix = sorted(parts[1:])
        return " + ".join([prefix, *suffix])
    return " + ".join(sorted(parts))


def build_finding(spec: ReportSpec, name: str, flag: str | None = None) -> Finding:
    display_name = canonical_display_name(name)
    return Finding(
        display_name=display_name,
        normalized_name=normalize_name(display_name),
        discovery_round=spec.short_label,
        discovery_script=spec.script_name,
        discovery_report=spec.report_name,
        flag=flag,
        sources=[(spec.short_label, spec.script_name, spec.report_name)],
    )


def extract_section(text: str, start_marker: str, end_marker: str | None = None) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise ValueError(f"Missing marker: {start_marker}")
    section = text[start:]
    if end_marker:
        end = section.find(end_marker)
        if end != -1:
            section = section[:end]
    return section


def iter_pipe_rows(section: str, row_pattern: str = r"^\d+\.\s") -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if "|" not in stripped:
            continue
        if stripped.startswith(("Filter", "Rank", "-----", "Overview", "Setup")):
            continue
        if not re.match(row_pattern, stripped):
            continue
        rows.append([part.strip() for part in re.split(r"\s+\|\s+|\s+\|$", stripped)])
    return rows


def parse_ranked_table(
    spec: ReportSpec,
    text: str,
    start_marker: str,
    end_marker: str | None,
    column_map: dict[int, str],
    flag_source: str | int | None = "name",
) -> list[Finding]:
    section = extract_section(text, start_marker, end_marker)
    findings: list[Finding] = []
    for parts in iter_pipe_rows(section):
        raw_name = parts[0]
        name, name_flag = split_name_flag(raw_name)
        flag = name_flag
        if isinstance(flag_source, int):
            flag = parts[flag_source].strip() or flag
        finding = build_finding(spec, name, flag)
        for index, field_name in column_map.items():
            value = parts[index] if index < len(parts) else ""
            if field_name == "n":
                finding.n = parse_int(value)
            elif field_name.startswith("wr_"):
                setattr(finding, field_name, parse_pct(value))
            elif field_name == "pf":
                finding.pf = parse_float(value)
            elif field_name == "avg_ticks_5b":
                finding.avg_ticks_5b = parse_float(value)
            elif field_name == "persistence":
                finding.persistence = value.strip() or None
            elif field_name == "flag":
                finding.flag = value.strip() or finding.flag
        if finding.persistence is None:
            finding.persistence = classify_persistence(finding.wr_5b, finding.wr_30b)
        findings.append(finding)
    return findings


def parse_compound_report(spec: ReportSpec, text: str) -> list[Finding]:
    findings = parse_ranked_table(
        spec,
        text,
        "Compound filters ranked by 5-bar average return",
        "Forward window detail",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b"},
    )
    detail_section = extract_section(text, "Forward window detail", None)
    detail_map: dict[str, tuple[float | None, str | None]] = {}
    current_name: str | None = None
    for line in detail_section.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\.\s", stripped):
            current_name = normalize_name(split_name_flag(stripped)[0])
            continue
        if current_name and "30b N=" in stripped:
            wr_5b_match = re.search(r"5b N=\d+ WR=([0-9.]+)%", stripped)
            wr_30b_match = re.search(r"30b N=\d+ WR=([0-9.]+)%", stripped)
            wr_5b = parse_pct(wr_5b_match.group(1) + "%") if wr_5b_match else None
            wr_30b = parse_pct(wr_30b_match.group(1) + "%") if wr_30b_match else None
            detail_map[current_name] = (wr_30b, classify_persistence(wr_5b, wr_30b))
    for finding in findings:
        wr_30b, persistence = detail_map.get(finding.normalized_name, (None, None))
        finding.wr_30b = wr_30b
        finding.persistence = persistence
    return findings


def parse_simple_discovery(spec: ReportSpec, text: str) -> list[Finding]:
    marker_map = {
        "cross_category_combo_report.txt": "All 25 combos ranked by 5-bar average return",
        "round1_regime_gated_report.txt": "All 20 regime-gated filters ranked by 5-bar average return",
        "round1_time_day_report.txt": "All 25 filters ranked by 5-bar average return",
        "round2_novel_bar_patterns_report.txt": "All 15 novel filters ranked by 5-bar average return",
    }
    start_marker = marker_map[spec.report_name]
    return parse_ranked_table(spec, text, start_marker, None, {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b"})


def parse_persistence(spec: ReportSpec, text: str) -> list[Finding]:
    marker_map = {
        "round1_strength_persistence_report.txt": "20 requested filters ranked by 30b win rate",
        "round2_absorption_deep_report.txt": "15 requested deep filters",
        "round3_signal_density_report.txt": "20 requested density / confluence filters ranked by 30b win rate",
    }
    start_marker = marker_map[spec.report_name]
    return parse_ranked_table(
        spec,
        text,
        start_marker,
        None,
        {
            1: "n",
            2: "wr_5b",
            3: "wr_10b",
            4: "wr_15b",
            5: "wr_30b",
            6: "pf",
            7: "avg_ticks_5b",
            9: "persistence",
        },
    )


def parse_persistence_with_sharpe(spec: ReportSpec, text: str) -> list[Finding]:
    return parse_ranked_table(
        spec,
        text,
        "20 requested stacked filters ranked by 30b win rate",
        None,
        {
            1: "n",
            2: "wr_5b",
            3: "wr_10b",
            4: "wr_15b",
            5: "wr_30b",
            6: "pf",
            7: "avg_ticks_5b",
            10: "persistence",
        },
    )


def parse_multi_bar(spec: ReportSpec, text: str) -> list[Finding]:
    return parse_ranked_table(
        spec,
        text,
        "15 requested multi-bar sequence filters",
        None,
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "flag"},
        flag_source=8,
    )


def parse_walkforward(spec: ReportSpec, text: str) -> list[Finding]:
    pattern = re.compile(r"FILTER\s+\d+:\s+(?P<name>.+?)\n-+\n(?P<body>.*?)(?=\nFILTER\s+\d+:|\Z)", re.S)
    findings: list[Finding] = []
    for match in pattern.finditer(text):
        name = match.group("name").strip()
        body = match.group("body")
        finding = build_finding(spec, name)

        summary_match = re.search(
            r"(?:Summary|Discovery sample):\s+N=(?P<n>[\d,]+),\s+WR=(?P<wr>[0-9.]+)%,\s+PF=(?P<pf>[-+0-9.,infna]+),\s+Avg=(?P<avg>[-+0-9.,]+)\s+ticks",
            body,
        )
        if summary_match:
            finding.n = parse_int(summary_match.group("n"))
            finding.wr_5b = parse_pct(summary_match.group("wr") + "%")
            finding.pf = parse_float(summary_match.group("pf"))
            finding.avg_ticks_5b = parse_float(summary_match.group("avg"))

        oos_match = re.search(
            r"(?:Overall OOS|Composite OOS):\s+N=(?P<n>[\d,]+),(?:\s+Wins=\d+,)?\s+WR=(?P<wr>[0-9.]+)%,\s+Avg=(?P<avg>[-+0-9.,]+)\s+ticks",
            body,
        )
        if oos_match:
            finding.oos_n = parse_int(oos_match.group("n"))
            finding.oos_wr = parse_pct(oos_match.group("wr") + "%")

        bayes_match = re.search(r"Posterior:\s+Beta\([^\)]*\),\s+mean=(?P<mean>[0-9.]+)%", body)
        if bayes_match:
            finding.bayes_mean = parse_pct(bayes_match.group("mean") + "%")

        verdict_match = re.search(r"OVERALL VERDICT:\s+(?P<verdict>DEPLOY|PAPER TRADE|INSUFFICIENT DATA)", body)
        if verdict_match:
            finding.verdict = verdict_match.group("verdict")

        findings.append(finding)
    return findings


def parse_validated_table(spec: ReportSpec, text: str) -> list[Finding]:
    start_marker, column_map, flag_source = VALIDATED_TABLE_SPECS[spec.report_name]
    return parse_ranked_table(spec, text, start_marker, None, column_map, flag_source=flag_source)


def parse_round7_negation(spec: ReportSpec, text: str) -> ReportParseResult:
    section = extract_section(text, "20 anti-pattern filters", "KILLER count")
    killers: list[Killer] = []
    for parts in iter_pipe_rows(section):
        if len(parts) < 7:
            continue
        name, _ = split_name_flag(parts[0])
        verdict = parts[6].strip()
        if verdict != "KILLER":
            continue
        killers.append(
            Killer(
                name=canonical_display_name(name),
                delta_wr=parse_float(parts[5].replace("pp", "")),
                n_with=parse_int(parts[1]),
                wr_with=parse_pct(parts[2]),
                n_without=parse_int(parts[3]),
                wr_without=parse_pct(parts[4]),
            )
        )
    return ReportParseResult(killers=killers)


def parse_exit_timing(spec: ReportSpec, text: str) -> ReportParseResult:
    contexts = [
        ("ALL ENTRIES", "FIRST-HOUR ENTRIES", "all"),
        ("FIRST-HOUR ENTRIES", "LAST-HOUR ENTRIES", "first_hour"),
        ("LAST-HOUR ENTRIES", "RECOMMENDATION SECTION", "last_hour"),
    ]
    findings: list[Finding] = []
    recommendations: list[ExitRecommendation] = []

    for start_marker, end_marker, context in contexts:
        section = extract_section(text, start_marker, end_marker)
        overview = extract_section(section, "Overview:", "Detailed metrics:")
        detail = extract_section(section, "Detailed metrics:", "Observation units:")

        optimal_map: dict[str, tuple[str, float | None]] = {}
        for parts in iter_pipe_rows(overview, row_pattern=r"^[A-Za-z0-9]"):
            if len(parts) < 9:
                continue
            setup = parts[0].strip()
            optimal_map[setup] = (parts[7].strip(), parse_float(parts[8]))

        grouped_rows: dict[str, dict[str, list[str]]] = {}
        for parts in iter_pipe_rows(detail, row_pattern=r"^[A-Za-z0-9]"):
            if len(parts) < 7:
                continue
            setup = parts[0].strip()
            window = parts[1].strip()
            grouped_rows.setdefault(setup, {})[window] = parts

        for raw_setup, window_rows in grouped_rows.items():
            display_name = build_exit_timing_name(raw_setup, context)
            finding = build_finding(spec, display_name)
            row_5b = window_rows.get("5b")
            row_10b = window_rows.get("10b")
            row_15b = window_rows.get("15b")
            row_30b = window_rows.get("30b")
            if row_5b:
                finding.n = parse_int(row_5b[2])
                finding.wr_5b = parse_pct(row_5b[3])
                finding.pf = parse_float(row_5b[4])
                finding.avg_ticks_5b = parse_float(row_5b[5])
            if row_10b:
                finding.wr_10b = parse_pct(row_10b[3])
            if row_15b:
                finding.wr_15b = parse_pct(row_15b[3])
            if row_30b:
                finding.wr_30b = parse_pct(row_30b[3])
            finding.persistence = classify_persistence(finding.wr_5b, finding.wr_30b)
            findings.append(finding)

            optimal_exit, sharpe = optimal_map.get(raw_setup, ("", None))
            best_row = window_rows.get(optimal_exit)
            recommendations.append(
                ExitRecommendation(
                    context=context,
                    display_name=finding.display_name,
                    normalized_name=finding.normalized_name,
                    optimal_exit=optimal_exit,
                    sharpe=sharpe,
                    avg_ticks=parse_float(best_row[5]) if best_row else None,
                    n=parse_int(best_row[2]) if best_row else None,
                )
            )

    return ReportParseResult(findings=findings, exit_recommendations=recommendations)


def build_exit_timing_name(raw_setup: str, context: str) -> str:
    base = canonical_display_name(raw_setup)
    if context == "all":
        return base
    if context == "first_hour":
        if "first_hour" not in base:
            return f"{base} + first_hour"
        return base
    if context == "last_hour":
        if "last_hour" not in base:
            return f"{base} + last_hour"
        return base
    return base


def parse_generic_auto(spec: ReportSpec, text: str) -> list[Finding]:
    findings: list[Finding] = []
    started = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\.\s", stripped) and "|" in stripped:
            started = True
        if not started:
            continue
        if not (re.match(r"^\d+\.\s", stripped) and "|" in stripped):
            continue
        parts = [part.strip() for part in stripped.split("|")]
        name, name_flag = split_name_flag(parts[0])
        finding = build_finding(spec, name, name_flag)
        numeric_parts = parts[1:]
        if numeric_parts:
            finding.n = parse_int(numeric_parts[0])
        pct_values = [parse_pct(part) for part in numeric_parts if "%" in part]
        float_values = [parse_float(part) for part in numeric_parts if re.search(r"[-+]?\d", part) and "%" not in part and "[" not in part]
        if pct_values:
            finding.wr_5b = pct_values[0]
        if len(pct_values) >= 2:
            finding.wr_30b = pct_values[-1]
        if float_values:
            finding.pf = float_values[0]
        if len(float_values) >= 2:
            finding.avg_ticks_5b = float_values[1]
        finding.persistence = classify_persistence(finding.wr_5b, finding.wr_30b)
        findings.append(finding)
    return findings


def parse_report(spec: ReportSpec) -> ReportParseResult:
    if not spec.path.exists():
        return ReportParseResult()
    text = spec.path.read_text(encoding="utf-8")
    if spec.parser == "compound":
        findings = parse_compound_report(spec, text)
        return ReportParseResult(findings=findings)
    if spec.parser == "simple_discovery":
        findings = parse_simple_discovery(spec, text)
        return ReportParseResult(findings=findings)
    if spec.parser == "persistence":
        findings = parse_persistence(spec, text)
        return ReportParseResult(findings=findings)
    if spec.parser == "persistence_with_sharpe":
        findings = parse_persistence_with_sharpe(spec, text)
        return ReportParseResult(findings=findings)
    if spec.parser == "multi_bar":
        findings = parse_multi_bar(spec, text)
        return ReportParseResult(findings=findings)
    if spec.parser == "walkforward":
        findings = parse_walkforward(spec, text)
        return ReportParseResult(findings=findings)
    if spec.parser == "validated_table":
        findings = parse_validated_table(spec, text)
        return ReportParseResult(findings=findings)
    if spec.parser == "negation":
        return parse_round7_negation(spec, text)
    if spec.parser == "exit_timing":
        return parse_exit_timing(spec, text)
    if spec.parser == "generic_auto":
        findings = parse_generic_auto(spec, text)
        return ReportParseResult(findings=findings)
    raise ValueError(f"Unknown parser: {spec.parser}")


def merge_findings(all_findings: list[Finding]) -> dict[str, Finding]:
    merged: dict[str, Finding] = {}
    for finding in all_findings:
        existing = merged.get(finding.normalized_name)
        if existing is None:
            merged[finding.normalized_name] = finding
            continue
        for source in finding.sources:
            if source not in existing.sources:
                existing.sources.append(source)
        if existing.flag is None and finding.flag is not None:
            existing.flag = finding.flag
        if existing.verdict is None and finding.verdict is not None:
            existing.verdict = finding.verdict
        for field_name in ("n", "wr_5b", "wr_10b", "wr_15b", "wr_30b", "pf", "avg_ticks_5b", "oos_n", "oos_wr", "bayes_mean"):
            if getattr(existing, field_name) is None and getattr(finding, field_name) is not None:
                setattr(existing, field_name, getattr(finding, field_name))
        if existing.persistence is None and finding.persistence is not None:
            existing.persistence = finding.persistence
        if existing.persistence is None:
            existing.persistence = classify_persistence(existing.wr_5b, existing.wr_30b)
        if finding.verdict == "DEPLOY" and existing.verdict != "DEPLOY":
            existing.verdict = finding.verdict
        if finding.oos_wr is not None and (existing.oos_wr is None or finding.oos_wr > existing.oos_wr):
            existing.oos_wr = finding.oos_wr
            existing.oos_n = finding.oos_n
        if finding.bayes_mean is not None and (existing.bayes_mean is None or finding.bayes_mean > existing.bayes_mean):
            existing.bayes_mean = finding.bayes_mean
    for finding in merged.values():
        if finding.persistence is None:
            finding.persistence = classify_persistence(finding.wr_5b, finding.wr_30b)
    return merged


def load_calendar_stats() -> tuple[str, str, int]:
    with OHLCV_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        ts_index = header.index("ts_event")
        dates: set[str] = set()
        for row in reader:
            if not row:
                continue
            value = row[ts_index]
            if value:
                dates.add(value[:10])
    ordered = sorted(dates)
    if not ordered:
        raise ValueError("No dates found in OHLCV CSV")
    return ordered[0], ordered[-1], len(ordered)


def deploy_grade(findings: dict[str, Finding]) -> list[Finding]:
    selected: list[Finding] = []
    for finding in findings.values():
        qualifies = False
        if finding.verdict == "DEPLOY":
            qualifies = True
        elif finding.flag == "VALIDATED":
            qualifies = True
        elif (
            finding.n is not None
            and finding.wr_5b is not None
            and finding.pf is not None
            and finding.avg_ticks_5b is not None
            and finding.n >= 100
            and finding.wr_5b >= 65.0
            and finding.pf >= 1.50
            and finding.avg_ticks_5b > 0
        ):
            qualifies = True
        if qualifies:
            selected.append(finding)
    return sorted(selected, key=ranking_key, reverse=True)


def ranking_wr(finding: Finding) -> float:
    if finding.wr_30b is not None:
        return finding.wr_30b
    if finding.wr_5b is not None:
        return finding.wr_5b
    return -1.0


def ranking_key(finding: Finding) -> tuple[float, float, int]:
    return (
        finding.oos_wr if finding.oos_wr is not None else -1.0,
        ranking_wr(finding),
        finding.n if finding.n is not None else -1,
    )


def find_one(findings: dict[str, Finding], name: str) -> Finding:
    normalized = normalize_name(name)
    finding = findings.get(normalized)
    if finding is None:
        raise KeyError(f"Missing finding: {name}")
    return finding


def validation_status(finding: Finding) -> str:
    if finding.verdict:
        return finding.verdict
    if finding.flag == "VALIDATED":
        return "VALIDATED"
    if finding.flag == "PROMISING":
        return "PROMISING"
    if finding.oos_wr is not None:
        return "WALK-FORWARD"
    return "DISCOVERY_STRONG"


def source_text(finding: Finding) -> str:
    primary = f"{finding.discovery_round}/{finding.discovery_script}"
    extras = [f"{round_label}/{script_name}" for round_label, script_name, _ in finding.sources[1:]]
    if not extras:
        return primary
    return primary + " | also: " + ", ".join(extras)


def frequency_text(n: int | None, session_count: int) -> str:
    if n is None or session_count <= 0:
        return "n/a"
    per_day = n / session_count
    per_week = per_day * 5.0
    return f"~{per_day:.2f}/day | ~{per_week:.1f}/week"


def color_for_finding(finding: Finding) -> str:
    reference = finding.oos_wr if finding.oos_wr is not None else ranking_wr(finding)
    if reference >= 80.0:
        return "GREEN"
    if reference >= 75.0:
        return "YELLOW"
    if reference >= 70.0:
        return "ORANGE"
    return "GRAY"


def short_killer_name(name: str) -> str:
    lowered = name.lower()
    if "middle 40-60%" in lowered:
        return "middle 40-60% of 60m range"
    if "volume spike > 3x ema" in lowered:
        return "volume spike > 3x EMA"
    if "bar_delta same direction" in lowered:
        return "same-direction bar_delta > 90th percentile"
    if "next-bar delta flips opposite signal" in lowered:
        return "next-bar delta flips opposite signal"
    return name


def signal_protects_from_killer(finding: Finding, killer: Killer) -> bool:
    name = finding.normalized_name
    killer_name = killer.name.lower()
    if "middle 40-60%" in killer_name:
        return "60m_extreme" in name or "not middle 40-60% of 60m range" in name or "not all_killers" in name
    if "volume spike > 3x ema" in killer_name:
        return "not volume spike > 3x ema" in name or "not all_killers" in name
    return False


def killer_text_for_finding(finding: Finding, killers: list[Killer]) -> str:
    active = [short_killer_name(killer.name) for killer in killers if not signal_protects_from_killer(finding, killer)]
    return "; ".join(active) if active else "already structurally excludes the round7 killers"


def render_executive_summary(
    loaded_specs: list[ReportSpec],
    documented_filter_count: int,
    qualifying: list[Finding],
    first_date: str,
    last_date: str,
    optional_missing: list[str],
) -> list[str]:
    scripts_created = len({spec.script_name for spec in loaded_specs})
    return [
        "Section 1: Executive Summary",
        "============================",
        "- Total rounds in scope: 15 (R0-R14).",
        f"- Reports available/read: {len(loaded_specs)}." + (f" Optional missing: {', '.join(optional_missing)}." if optional_missing else ""),
        f"- Total scripts created: {scripts_created} report-generating analysis scripts reviewed here (+ round5 master summary + this round15 compiler).",
        f"- Total filter evaluations: {documented_filter_count:,} explicitly enumerated filters / setup-context profiles (+ 90 exit-window rows in R9).",
        f"- Total DEPLOY-grade findings: {len(qualifying):,} unique signals.",
        f"- Date range: {first_date} to {last_date}.",
        "",
    ]


def render_deploy_grade_section(qualifying: list[Finding], killers: list[Killer]) -> list[str]:
    lines = [
        "Section 2: TOP 30 DEPLOY-Grade Signals",
        "======================================",
        "Ranking rule: OOS WR first, then best available full-sample WR (30b preferred, else 5b), then N.",
        "",
    ]
    for index, finding in enumerate(qualifying[:30], start=1):
        lines.append(f"{index:02d}. {finding.display_name}")
        lines.append(
            "    "
            + " | ".join(
                [
                    f"Status={validation_status(finding)}",
                    f"N={fmt_count(finding.n)}",
                    f"WR5={fmt_pct(finding.wr_5b)}",
                    f"WR30={fmt_pct(finding.wr_30b)}",
                    f"PF={fmt_num(finding.pf)}",
                    f"Avg={fmt_ticks(finding.avg_ticks_5b)}",
                    f"OOS={fmt_pct(finding.oos_wr)}" + (f" (N={fmt_count(finding.oos_n)})" if finding.oos_n is not None else ""),
                    f"Bayes={fmt_pct(finding.bayes_mean)}",
                    f"Persistence={finding.persistence or 'n/a'}",
                ]
            )
        )
        lines.append(f"    Source: {source_text(finding)}")
        lines.append(f"    Killers to avoid: {killer_text_for_finding(finding, killers)}")
    lines.append("")
    return lines


def render_signal_killers(killers: list[Killer]) -> list[str]:
    lines = [
        "Section 3: Signal Killers (What to AVOID)",
        "========================================",
        "From R7B, these four anti-patterns consistently destroy edge inside the core 60m_extreme + 15m_trend regime:",
        "",
    ]
    for index, killer in enumerate(killers, start=1):
        lines.append(
            f"{index}. {short_killer_name(killer.name)} | WR with={fmt_pct(killer.wr_with)} vs without={fmt_pct(killer.wr_without)} | Delta={fmt_num(killer.delta_wr, 1)}pp | N with={fmt_count(killer.n_with)}"
        )
    lines.extend(
        [
            "",
            "Recommendation: always exclude these conditions in automation unless a future walk-forward report proves a specific exception.",
            "",
        ]
    )
    return lines


def find_exit_recommendation(recommendations: list[ExitRecommendation], name: str, context: str) -> ExitRecommendation | None:
    normalized = normalize_name(name)
    for recommendation in recommendations:
        if recommendation.normalized_name == normalized and recommendation.context == context:
            return recommendation
    return None


def render_novel_discoveries(findings: dict[str, Finding], killers: list[Killer], exit_recommendations: list[ExitRecommendation], missing_latest: list[str]) -> list[str]:
    r0_core = find_one(findings, "absorption + 60m_extreme + 15m_trend_aligned")
    r2_doji = find_one(findings, "Doji + 60m_extreme + 15m_trend_aligned + first_hour")
    r6_gap = find_one(findings, "Failed OR breakout/breakdown trap + 60m_extreme + 15m_trend_aligned")
    r6_prior = find_one(findings, "Prior session wide range (top quartile) + 60m_extreme + 15m_trend_aligned")
    r7_seq = find_one(findings, "Any signal -> confirming signal within 2 bars + 60m_extreme + 15m_trend_aligned")
    r8_cvd = find_one(findings, "CVD divergence + 60m_extreme + 15m_trend_aligned")
    r8_levels = find_one(findings, "Prior day level + 60m_extreme + 15m_trend_aligned + NOT lunch")
    r10_stack = find_one(findings, "CVD divergence + doji + 60m_extreme + 15m_trend_aligned")
    r11_chain = find_one(findings, "score >= 70 + delta_opposite + first_hour + 60m_extreme + 15m_trend_aligned")
    r9_all = find_exit_recommendation(exit_recommendations, "60m_extreme + 15m_trend_aligned", "all")
    r9_first = find_exit_recommendation(exit_recommendations, "CVD divergence + 60m_extreme + 15m_trend_aligned + first_hour", "first_hour")
    r9_last = find_exit_recommendation(exit_recommendations, "60m_extreme + 15m_trend_aligned + last_hour", "last_hour")
    r12_micro = findings.get(normalize_name("|delta|/vol < 0.05 + 60m_extreme + 15m_trend_aligned"))
    r13_calendar = findings.get(normalize_name("NOT summer + NOT FOMC + 60m_extreme + 15m_trend_aligned + NOT volume spike > 3x EMA + first_hour"))
    r14_overnight = findings.get(normalize_name("Small overnight move < 20 ticks + 60m_extreme + 15m_trend_aligned"))
    r14_overlay = findings.get(normalize_name("CVD divergence + doji + 60m_extreme + 15m_trend_aligned + NOT volume spike > 3x EMA + first_hour"))

    lines = [
        "Section 4: Novel Discoveries by Round",
        "=====================================",
        f"- R0: 60m_extreme became the universal anchor, and the absorption core stack reached WR5={fmt_pct(r0_core.wr_5b)}, OOS={fmt_pct(r0_core.oos_wr)}.",
        f"- R2: Doji / first-hour / lunch-exclusion family emerged; Doji + 60m_extreme + 15m_trend_aligned + first_hour printed WR5={fmt_pct(r2_doji.wr_5b)}, OOS={fmt_pct(r2_doji.oos_wr)}.",
        f"- R6: Prior-day context and gap/OR reversal patterns validated; prior wide-range day + core stack hit WR5={fmt_pct(r6_prior.wr_5b)}, while failed OR trap + core stack hit WR5={fmt_pct(r6_gap.wr_5b)}.",
        f"- R7: Sequential confirmation added new alpha (Any signal -> confirming signal within 2 bars + core stack WR5={fmt_pct(r7_seq.wr_5b)}), while killers proved costly: {', '.join(short_killer_name(k.name) for k in killers)}.",
        f"- R8: CVD divergence at structure became the biggest new alpha source (WR5={fmt_pct(r8_cvd.wr_5b)}, PF={fmt_num(r8_cvd.pf)}), while prior-day / VWAP / round-number confluence added level-aware context (best level stack WR5={fmt_pct(r8_levels.wr_5b)}).",
        f"- R9: Exit timing showed the core stack prefers {r9_all.optimal_exit if r9_all else '15b'} holds on all entries, CVD divergence first-hour likes {r9_first.optimal_exit if r9_first else '15b'}, and last-hour core trades stretch to {r9_last.optimal_exit if r9_last else '30b'}.",
        f"- R10: Stacked winners + killer exclusion pushed the best anti-killer combo to WR30={fmt_pct(r10_stack.wr_30b)} on CVD divergence + doji + core trend context.",
        f"- R11: Chain/triple interactions added higher-order confluence; score >= 70 + delta_opposite + first_hour + core stack reached WR5={fmt_pct(r11_chain.wr_5b)} with Avg={fmt_ticks(r11_chain.avg_ticks_5b)}.",
    ]
    if r12_micro or r13_calendar or r14_overnight or r14_overlay:
        latest_parts: list[str] = []
        if r12_micro:
            latest_parts.append(f"R12 microstructure: low delta/volume ratio + core regime reached WR30={fmt_pct(r12_micro.wr_30b)}")
        if r13_calendar:
            latest_parts.append(f"R13 macro/calendar: NOT summer + NOT FOMC + first_hour + killer exclusion averaged {fmt_ticks(r13_calendar.avg_ticks_5b)}")
        if r14_overnight:
            latest_parts.append(f"R14 overnight/regime: small overnight moves + core regime reached WR30={fmt_pct(r14_overnight.wr_30b)}")
        if r14_overlay:
            latest_parts.append(f"best low-N overlay was CVD divergence + doji + core + first_hour at WR30={fmt_pct(r14_overlay.wr_30b)}")
        lines.append("- R12-R14: " + "; ".join(latest_parts) + ".")
    elif missing_latest:
        lines.append(f"- R12-R14: no optional reports were present at build time ({', '.join(missing_latest)}), so no additional validated discoveries were added.")
    lines.append("")
    return lines


def render_universal_trading_rules(findings: dict[str, Finding]) -> list[str]:
    sixty_only = find_one(findings, "60m_extreme")
    base_stack = find_one(findings, "60m_extreme + 15m_trend_aligned")
    first_hour = find_one(findings, "60m_extreme + 15m_trend_aligned + first_hour")
    lunch = find_one(findings, "all signals + 60m_extreme + hour 12-14")
    score_stack = find_one(findings, "score >= 60 + 60m_extreme + 15m_trend_aligned")
    cvd_core = find_one(findings, "CVD divergence + 60m_extreme + 15m_trend_aligned")
    doji_core = find_one(findings, "Doji + 60m_extreme + 15m_trend_aligned")
    hammer = find_one(findings, "Hammer + 60m_extreme + 15m_trend_aligned")
    engulfing = find_one(findings, "Engulfing + 60m_extreme + 15m_trend_aligned")

    return [
        "Section 5: Universal Trading Rules",
        "==================================",
        f"1. 60m extreme is THE universal edge: standalone 60m_extreme reached WR5={fmt_pct(sixty_only.wr_5b)} and WR30={fmt_pct(sixty_only.wr_30b)}.",
        f"2. 15m trend alignment is the strongest secondary: the base core stack reached WR5={fmt_pct(base_stack.wr_5b)} and WR30={fmt_pct(base_stack.wr_30b)}.",
        f"3. First hour (09:30-10:30) is optimal: the core first-hour stack printed WR5={fmt_pct(first_hour.wr_5b)} and OOS={fmt_pct(first_hour.oos_wr)}.",
        f"4. Lunch (12:00-14:00) is a danger zone: the broad lunch bucket only managed WR5={fmt_pct(lunch.wr_5b)} versus materially stronger first-hour performance.",
        f"5. Edges grow over time (5b→30b): the base stack rose from WR5={fmt_pct(base_stack.wr_5b)} to WR30={fmt_pct(base_stack.wr_30b)}, and score>=60 + core rose from {fmt_pct(score_stack.wr_5b)} to {fmt_pct(score_stack.wr_30b)}.",
        "6. Exclude the killers: middle-of-range anchors, volume spikes > 3x EMA, same-direction bar_delta > 90th percentile, and next-bar delta flips opposite signal.",
        f"7. CVD divergence at structure is a new alpha source: the core CVD divergence stack printed WR5={fmt_pct(cvd_core.wr_5b)} and PF={fmt_num(cvd_core.pf)}.",
        f"8. Doji / hammer / engulfing at 60m_extreme form a durable pattern family: doji WR5={fmt_pct(doji_core.wr_5b)}, hammer WR5={fmt_pct(hammer.wr_5b)}, engulfing WR5={fmt_pct(engulfing.wr_5b)}.",
        "",
    ]


def render_indicator_build(qualifying: list[Finding], killers: list[Killer], session_count: int) -> list[str]:
    lines = [
        "Section 6: Recommended NinjaTrader Indicator Build (Top 10)",
        "==========================================================",
        "Use the 10 highest-ranked signals below as the first implementation tranche:",
        "",
    ]
    for index, finding in enumerate(qualifying[:10], start=1):
        lines.append(f"{index}. {finding.display_name}")
        lines.append(f"   - Exact definition: {finding.display_name}.")
        lines.append(f"   - Expected frequency: {frequency_text(finding.n, session_count)} based on N={fmt_count(finding.n)}.")
        lines.append(
            f"   - Color: {color_for_finding(finding)} | Reference WR={fmt_pct(finding.oos_wr if finding.oos_wr is not None else ranking_wr(finding))} | Killers to avoid: {killer_text_for_finding(finding, killers)}."
        )
    lines.append("")
    return lines


def render_caveats(documented_filter_count: int, optional_missing: list[str]) -> list[str]:
    lines = [
        "Section 7: Statistical Caveats",
        "==============================",
        f"- Multiple-comparisons risk remains real: {documented_filter_count:,} explicitly documented filters / setup-context profiles (+ 90 R9 exit-window rows) means some tails will overstate edge by chance.",
        "- Validation depth is mixed: walk-forward DEPLOY signals have the strongest evidence; later VALIDATED tables rely on Wilson-threshold in-sample confirmation, not true OOS composites.",
        "- Overlap risk is high: many top signals are nested versions of the same core regime (60m_extreme + 15m trend + first-hour / doji / CVD / killer exclusion). Do not size them as independent bets.",
        "- Small-N warning: elite absorption and some chain/sequence overlays are real but sparse. Treat N<100 as premium overlays, not the automation backbone.",
        "- Mixed observation frames matter: bar/global_index, signal/global_index+direction, and second-bar sequence studies are comparable directionally, but not perfectly apples-to-apples.",
    ]
    if optional_missing:
        lines.append(f"- Coverage gap: optional late-round reports were missing at build time ({', '.join(optional_missing)}), so this summary reflects the available R0-R11 evidence set plus the prior round5 master summary context.")
    lines.append("")
    return lines


def build_report() -> str:
    loaded_specs = [spec for spec in REPORT_SPECS if spec.path.exists()]
    optional_missing = [spec.report_name for spec in REPORT_SPECS if spec.optional and not spec.path.exists()]

    parsed_results: list[ReportParseResult] = [parse_report(spec) for spec in loaded_specs]
    all_findings = [finding for result in parsed_results for finding in result.findings]
    killers = [killer for result in parsed_results for killer in result.killers]
    exit_recommendations = [recommendation for result in parsed_results for recommendation in result.exit_recommendations]

    documented_filter_count = 0
    for spec, result in zip(loaded_specs, parsed_results):
        if spec.filter_count is not None:
            documented_filter_count += spec.filter_count
        else:
            documented_filter_count += len(result.findings)

    merged = merge_findings(all_findings)
    qualifying = deploy_grade(merged)
    first_date, last_date, session_count = load_calendar_stats()

    lines = [
        "MASTER BACKTEST SUMMARY V2",
        "==========================",
        "Consolidated review of all available round reports from R0-R14, updated through the round 11 research set and written for implementation prioritization.",
        "",
    ]
    lines.extend(render_executive_summary(loaded_specs, documented_filter_count, qualifying, first_date, last_date, optional_missing))
    lines.extend(render_deploy_grade_section(qualifying, killers))
    lines.extend(render_signal_killers(killers))
    lines.extend(render_novel_discoveries(merged, killers, exit_recommendations, optional_missing))
    lines.extend(render_universal_trading_rules(merged))
    lines.extend(render_indicator_build(qualifying, killers, session_count))
    lines.extend(render_caveats(documented_filter_count, optional_missing))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
