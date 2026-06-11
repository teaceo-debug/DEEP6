#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import round15_master_summary_v2 as base
import round28_master_summary_v3 as prev


ROOT = base.ROOT
REPORT_DIR = base.REPORT_DIR
SCRIPTS_DIR = ROOT / "scripts"
OUT_PATH = REPORT_DIR / "MASTER_BACKTEST_SUMMARY_V4.txt"

EXPECTED_TOTAL_ROUNDS = 38
SUMMARY_PATTERNS = ("*report*.txt", "*SUMMARY*.txt")
LEGACY_EXTRA_REPORTS = ("round1_walkforward_cross_category.txt",)
ROUND9_EXTRA_EXIT_ROWS = 90
ROUND26_EXTRA_EXIT_ROWS = 75


@dataclass(frozen=True)
class Round26Recommendation:
    display_name: str
    default_exit: str | None
    default_sharpe: float | None
    default_avg_ticks: float | None
    default_n: int | None
    best_fixed_target: str | None
    best_fixed_hit: float | None
    best_fixed_avg_ticks: float | None
    best_atr_target: str | None
    best_atr_hit: float | None
    best_atr_avg_ticks: float | None
    best_bracket: str | None
    best_bracket_wr: float | None
    best_bracket_avg_ticks: float | None
    best_bracket_pf: float | None


@dataclass(frozen=True)
class Round27RobustnessRow:
    display_name: str
    n: int | None
    wr_5b: float | None
    pf: float | None
    avg_ticks_5b: float | None
    status: str
    coverage: str
    wr_spread: float | None


@dataclass(frozen=True)
class Round31EntryProfile:
    display_name: str
    t0_wr: float | None
    t1_wr: float | None
    t2_wr: float | None
    tbest_wr: float | None
    t0_pf: float | None
    t1_pf: float | None
    t2_pf: float | None
    tbest_pf: float | None


PREV_CANONICAL = prev.canonical_display_name


def canonical_display_name(name: str) -> str:
    clean = PREV_CANONICAL(name)
    clean = clean.replace("CVD divergenceergenceergence", "CVD divergence")
    clean = clean.replace("CVD divergenceergence", "CVD divergence")
    clean = clean.replace("Failed OR breakout/breakdown trap/breakdown trap", "Failed OR breakout/breakdown trap")
    clean = clean.replace("(base)", "")
    clean = clean.replace("15m (base)", "15m")
    clean = clean.replace("Gap absorption (3+ bar gap then re-absorption)", "Gap absorption (3+ bar gap then re-absorption)")
    clean = clean.replace("Absorption -> gap of 3+ bars -> absorption again", "Gap absorption (3+ bar gap then re-absorption)")
    clean = clean.replace("Adaptive low delta/vol (rolling q10)", "|delta|/vol < 50-bar rolling q10")
    clean = clean.replace("Session delta opposing signal direction", "Session delta opposing signal")
    clean = clean.replace("Price within IB range", "Within IB")
    clean = clean.replace("Within IB range", "Within IB")
    clean = clean.replace("IB extension happened in last 5 bars", "IB extension happened in last 5 bars")
    clean = clean.replace("score 65-80", "Score 65-80")
    clean = clean.replace("score 50-65", "Score 50-65")
    clean = clean.replace("score 80-100", "Score 80-100")
    clean = clean.replace("max_strength", "max_strength")
    clean = clean.replace("Morning/evening", "Morning/evening")
    clean = clean.replace("first hour", "first_hour")
    clean = clean.replace("1st hr", "first_hour")
    clean = re.sub(r"CVD divergence(?:ergence)+", "CVD divergence", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    return clean


def normalize_name(name: str) -> str:
    clean = canonical_display_name(name).lower()
    clean = clean.replace("gap absorption (3+ bar gap then re-absorption)", "gap absorption")
    clean = clean.replace("absorption -> gap of 3+ bars -> absorption again", "gap absorption")
    clean = clean.replace("session delta opposing signal direction", "session delta opposing signal")
    clean = clean.replace("price within ib range", "within ib")
    if " + " not in clean:
        return clean
    parts = [part.strip() for part in clean.split(" + ") if part.strip()]
    if not parts:
        return clean
    if "->" in parts[0]:
        return " + ".join([parts[0], *sorted(parts[1:])])
    return " + ".join(sorted(parts))


base.canonical_display_name = canonical_display_name
base.normalize_name = normalize_name


VALIDATED_TABLE_EXTENSIONS = {
    "round27_regime_robustness_report.txt": (
        "Setup summary",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b"},
        None,
    ),
    "round30_absorption_clustering_report.txt": (
        "20 requested absorption-clustering / spacing / level / co-fire filters ranked by 30b WR",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round32_intrabar_position_report.txt": (
        "20 requested intrabar-position filters sorted by 30b WR",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round33_dynamic_thresholds_report.txt": (
        "20 dynamic-threshold filters ranked by 30b win rate",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round34_score_decomposition_report.txt": (
        "20 score decomposition filters ranked by 30b WR",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round35_session_structure_report.txt": (
        "20 requested session-structure filters sorted by 30b WR",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
}

base.VALIDATED_TABLE_SPECS.update(VALIDATED_TABLE_EXTENSIONS)


NEW_REPORT_SPECS = [
    base.ReportSpec("Round 26", "R26", "round26_profit_targets_report.txt", "round26_profit_targets.py", 5, "profit_targets"),
    base.ReportSpec("Round 27", "R27", "round27_regime_robustness_report.txt", "round27_regime_robustness.py", 10, "validated_table"),
    base.ReportSpec("Round 29", "R29", "round29_absorption_micro_report.txt", "round29_absorption_micro.py", 25, "round29_absorption_micro"),
    base.ReportSpec("Round 30", "R30", "round30_absorption_clustering_report.txt", "round30_absorption_clustering.py", 20, "validated_table"),
    base.ReportSpec("Round 31", "R31", "round31_entry_optimization_report.txt", "round31_entry_optimization.py", 20, "entry_optimization"),
    base.ReportSpec("Round 32", "R32", "round32_intrabar_position_report.txt", "round32_intrabar_position.py", 20, "validated_table"),
    base.ReportSpec("Round 33", "R33", "round33_dynamic_thresholds_report.txt", "round33_dynamic_thresholds.py", 20, "validated_table"),
    base.ReportSpec("Round 34", "R34", "round34_score_decomposition_report.txt", "round34_score_decomposition.py", 20, "validated_table"),
    base.ReportSpec("Round 35", "R35", "round35_session_structure_report.txt", "round35_session_structure.py", 20, "validated_table"),
    base.ReportSpec("Round 36", "R36", "round36_walkforward_r29_r35_report.txt", "round36_walkforward_r29_r35.py", 12, "walkforward"),
]


FAMILY_LABELS = {
    **prev.FAMILY_LABELS,
    "round29_absorption_micro_report.txt": "R29 absorption microstructure",
    "round30_absorption_clustering_report.txt": "R30 absorption clustering / gap re-tests",
    "round32_intrabar_position_report.txt": "R32 intrabar close/wick structure",
    "round33_dynamic_thresholds_report.txt": "R33 adaptive thresholds",
    "round34_score_decomposition_report.txt": "R34 score decomposition",
    "round35_session_structure_report.txt": "R35 session structure / IB context",
}


SKIP_FAMILY_REPORTS = set(prev.SKIP_FAMILY_REPORTS) | {
    "round26_profit_targets_report.txt",
    "round27_regime_robustness_report.txt",
    "round31_entry_optimization_report.txt",
    "round36_walkforward_r29_r35_report.txt",
}


FAMILY_CANDIDATES = {
    "round29_absorption_micro_report.txt": [
        "absorption + 60m + 15m + prior wide-range day + NOT killers",
        "ABS_03 only + 60m + 15m + NOT killers",
    ],
    "round30_absorption_clustering_report.txt": [
        "Gap absorption (3+ bar gap then re-absorption) + 60m + 15m",
        "absorption -> exhaustion within 3 bars + 60m + 15m",
    ],
    "round32_intrabar_position_report.txt": [
        "Close below open + bullish signal + 60m + 15m",
        "Current close < prior close + bullish signal + 60m + 15m",
    ],
    "round33_dynamic_thresholds_report.txt": [
        "Range < 0.5x ATR20 + doji + 60m + 15m + NOT killers",
        "|delta|/vol < 50-bar rolling q10 + doji + 60m + 15m + NOT killers",
        "Range < 50-bar rolling q25 + 60m + 15m",
    ],
    "round34_score_decomposition_report.txt": [
        "Score 50-65 + 60m + 15m + first_hour + NOT killers",
        "max_strength >= 0.7 + score >= 60 + 60m + 15m + first_hour + NOT killers",
        "TYPE_C only bars + 60m + 15m + first_hour",
    ],
    "round35_session_structure_report.txt": [
        "Within IB + session delta opposing + 60m + 15m + NOT killers",
        "Session delta opposing signal + 60m + 15m",
        "IB extension happened in last 5 bars + 60m + 15m",
    ],
}


def build_primary_specs() -> list[base.ReportSpec]:
    return [*prev.build_primary_specs(), *NEW_REPORT_SPECS]


def split_pipe_line(line: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s+\|\s+|\s+\|$", line.strip())]


def discover_text_report_paths() -> tuple[list[Path], list[Path], list[Path]]:
    matched: set[Path] = set()
    for pattern in SUMMARY_PATTERNS:
        matched.update(path for path in REPORT_DIR.glob(pattern) if path.name != OUT_PATH.name)

    extras: list[Path] = []
    for name in LEGACY_EXTRA_REPORTS:
        path = REPORT_DIR / name
        if path.exists() and path.name != OUT_PATH.name:
            extras.append(path)

    all_paths = sorted(matched.union(extras))
    return sorted(matched), sorted(extras), all_paths


def scripts_created_count() -> int:
    return len(list(SCRIPTS_DIR.glob("*.py")))


def month_range_text(first_date: str, last_date: str) -> str:
    start = datetime.fromisoformat(first_date)
    end = datetime.fromisoformat(last_date)
    return f"{start.strftime('%b %Y')} - {end.strftime('%b %Y')}"


def maybe_find(findings: dict[str, base.Finding], name: str) -> base.Finding | None:
    return findings.get(normalize_name(name))


def find_any(findings: dict[str, base.Finding], candidates: list[str]) -> base.Finding | None:
    for candidate in candidates:
        finding = maybe_find(findings, candidate)
        if finding is not None:
            return finding
    return None


def ranking_key_v4(finding: base.Finding) -> tuple[float, float, float, int]:
    return (
        finding.oos_wr if finding.oos_wr is not None else -1.0,
        finding.wr_30b if finding.wr_30b is not None else -1.0,
        finding.wr_5b if finding.wr_5b is not None else -1.0,
        finding.n if finding.n is not None else -1,
    )


def parse_round29_absorption_micro(spec: base.ReportSpec, text: str) -> list[base.Finding]:
    section = base.extract_section(text, "25 requested absorption micro filters ranked by 30b WR", None)
    findings: list[base.Finding] = []
    for line in section.splitlines():
        stripped = line.strip()
        if "|" not in stripped or not re.match(r"^\d+\s+\|", stripped):
            continue
        if stripped.startswith(("Rank", "-----")):
            continue
        parts = split_pipe_line(stripped)
        if len(parts) < 12:
            continue
        finding = base.build_finding(spec, parts[3])
        finding.n = base.parse_int(parts[4])
        finding.wr_5b = base.parse_pct(parts[5])
        finding.wr_10b = base.parse_pct(parts[6])
        finding.wr_30b = base.parse_pct(parts[7])
        finding.pf = base.parse_float(parts[8])
        finding.avg_ticks_5b = base.parse_float(parts[9])
        finding.persistence = parts[11] or base.classify_persistence(finding.wr_5b, finding.wr_30b)
        findings.append(finding)
    return findings


def parse_round26_profit_targets(spec: base.ReportSpec, text: str) -> list[base.Finding]:
    pattern = re.compile(r"SETUP\s+[A-E]:\s+(?P<name>.+?)\n-+\n(?P<body>.*?)(?=\nSETUP\s+[A-E]:|\Z)", re.S)
    findings: list[base.Finding] = []
    for match in pattern.finditer(text):
        name = match.group("name").strip()
        body = match.group("body")
        finding = base.build_finding(spec, name)
        rows: dict[str, list[str]] = {}
        for line in body.splitlines():
            stripped = line.strip()
            if not re.match(r"^(1b|2b|5b|10b|15b|30b)\s+\|", stripped):
                continue
            parts = split_pipe_line(stripped)
            if len(parts) < 6:
                continue
            rows[parts[0]] = parts
        row_5b = rows.get("5b")
        row_10b = rows.get("10b")
        row_15b = rows.get("15b")
        row_30b = rows.get("30b")
        if row_5b:
            finding.n = base.parse_int(row_5b[1])
            finding.wr_5b = base.parse_pct(row_5b[2])
            finding.pf = base.parse_float(row_5b[3])
            finding.avg_ticks_5b = base.parse_float(row_5b[4])
        if row_10b:
            finding.wr_10b = base.parse_pct(row_10b[2])
        if row_15b:
            finding.wr_15b = base.parse_pct(row_15b[2])
        if row_30b:
            finding.wr_30b = base.parse_pct(row_30b[2])
        finding.persistence = base.classify_persistence(finding.wr_5b, finding.wr_30b)
        findings.append(finding)
    return findings


def parse_report(spec: base.ReportSpec) -> base.ReportParseResult:
    if not spec.path.exists():
        return base.ReportParseResult()
    text = spec.path.read_text(encoding="utf-8")
    if spec.parser == "profit_targets":
        return base.ReportParseResult(findings=parse_round26_profit_targets(spec, text))
    if spec.parser == "round29_absorption_micro":
        return base.ReportParseResult(findings=parse_round29_absorption_micro(spec, text))
    if spec.parser == "entry_optimization":
        return base.ReportParseResult()
    return base.parse_report(spec)


def deploy_grade_v4(findings: dict[str, base.Finding]) -> list[base.Finding]:
    selected: list[base.Finding] = []
    for finding in findings.values():
        explicit_negative = finding.verdict in {"PAPER TRADE", "INSUFFICIENT", "INSUFFICIENT DATA"}
        if explicit_negative:
            continue
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
            and finding.wr_5b >= 70.0
            and finding.pf >= 2.0
            and finding.avg_ticks_5b > 0
        ):
            qualifies = True
        if qualifies:
            selected.append(finding)
    return sorted(selected, key=ranking_key_v4, reverse=True)


def parse_round26_recommendations() -> list[Round26Recommendation]:
    path = REPORT_DIR / "round26_profit_targets_report.txt"
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"SETUP\s+[A-E]:\s+(?P<name>.+?)\n-+\n(?P<body>.*?)(?=\nSETUP\s+[A-E]:|\Z)", re.S)
    recommendations: list[Round26Recommendation] = []

    for match in pattern.finditer(text):
        name = canonical_display_name(match.group("name"))
        body = match.group("body")
        time_rows: dict[str, list[str]] = {}
        fixed_rows: dict[str, list[str]] = {}
        atr_rows: dict[str, list[str]] = {}
        bracket_rows: dict[str, list[str]] = {}

        for line in body.splitlines():
            stripped = line.strip()
            if re.match(r"^(1b|2b|5b|10b|15b|30b)\s+\|", stripped):
                parts = split_pipe_line(stripped)
                if len(parts) >= 6:
                    time_rows[parts[0]] = parts
            elif re.match(r"^\+\d+t\s+\|", stripped):
                parts = split_pipe_line(stripped)
                if len(parts) >= 7:
                    fixed_rows[parts[0]] = parts
            elif re.match(r"^[0-9.]+x ATR20\s+\|", stripped):
                parts = split_pipe_line(stripped)
                if len(parts) >= 7:
                    atr_rows[parts[0]] = parts
            elif re.match(r"^-[0-9]+\s+/\s+\+[0-9]+\s+\|", stripped):
                parts = split_pipe_line(stripped)
                if len(parts) >= 6:
                    bracket_rows[parts[0]] = parts

        recommendation_line = None
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if line == "Recommendation:" and index + 1 < len(lines):
                recommendation_line = lines[index + 1]
                break

        default_exit = None
        best_fixed_target = None
        best_atr_target = None
        best_bracket = None
        best_bracket_wr = None
        best_bracket_avg_ticks = None
        best_bracket_pf = None

        if recommendation_line:
            match_default = re.search(r"Default to\s+(\S+)\s+time exit", recommendation_line)
            match_fixed = re.search(r"best fixed target =\s+([^\s;]+)", recommendation_line)
            match_atr = re.search(r"best ATR target =\s+([^;]+?)\s+\(Hit", recommendation_line)
            match_bracket = re.search(
                r"best bracket =\s+(-\d+\s*/\s*\+\d+)\s+\(WR\s+([0-9.]+)%,\s+Avg\s+([+-]?[0-9.]+)t,\s+PF\s+([0-9.]+|inf)\)",
                recommendation_line,
            )
            default_exit = match_default.group(1) if match_default else None
            best_fixed_target = match_fixed.group(1) if match_fixed else None
            best_atr_target = match_atr.group(1).strip() if match_atr else None
            if match_bracket:
                best_bracket = match_bracket.group(1)
                best_bracket_wr = base.parse_pct(match_bracket.group(2) + "%")
                best_bracket_avg_ticks = base.parse_float(match_bracket.group(3))
                best_bracket_pf = base.parse_float(match_bracket.group(4))

        default_row = time_rows.get(default_exit or "")
        fixed_row = fixed_rows.get(best_fixed_target or "")
        atr_row = atr_rows.get(best_atr_target or "")

        recommendations.append(
            Round26Recommendation(
                display_name=name,
                default_exit=default_exit,
                default_sharpe=base.parse_float(default_row[5]) if default_row else None,
                default_avg_ticks=base.parse_float(default_row[4]) if default_row else None,
                default_n=base.parse_int(default_row[1]) if default_row else None,
                best_fixed_target=best_fixed_target,
                best_fixed_hit=base.parse_pct(fixed_row[2]) if fixed_row else None,
                best_fixed_avg_ticks=base.parse_float(fixed_row[4]) if fixed_row else None,
                best_atr_target=best_atr_target,
                best_atr_hit=base.parse_pct(atr_row[2]) if atr_row else None,
                best_atr_avg_ticks=base.parse_float(atr_row[4]) if atr_row else None,
                best_bracket=best_bracket,
                best_bracket_wr=best_bracket_wr,
                best_bracket_avg_ticks=best_bracket_avg_ticks,
                best_bracket_pf=best_bracket_pf,
            )
        )

    return recommendations


def parse_round27_robustness_rows() -> list[Round27RobustnessRow]:
    path = REPORT_DIR / "round27_regime_robustness_report.txt"
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    section = base.extract_section(text, "Setup summary", "Detailed setup-by-period metrics")
    rows: list[Round27RobustnessRow] = []
    for line in section.splitlines():
        stripped = line.strip()
        if "|" not in stripped or not re.match(r"^\d+\.\s", stripped):
            continue
        if stripped.startswith(("Setup", "-----")):
            continue
        parts = split_pipe_line(stripped)
        if len(parts) < 8:
            continue
        name, _ = prev.split_name_flag(parts[0])
        rows.append(
            Round27RobustnessRow(
                display_name=canonical_display_name(name),
                n=base.parse_int(parts[1]),
                wr_5b=base.parse_pct(parts[2]),
                pf=base.parse_float(parts[3]),
                avg_ticks_5b=base.parse_float(parts[4]),
                status=parts[5],
                coverage=parts[6],
                wr_spread=base.parse_float(parts[7].replace("pp", "")),
            )
        )
    return rows


def parse_round31_entry_profiles() -> list[Round31EntryProfile]:
    path = REPORT_DIR / "round31_entry_optimization_report.txt"
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    section = base.extract_section(text, "All 20 setup x timing results", "Per-setup leaders")
    grouped: dict[str, dict[str, list[str]]] = {}
    for line in section.splitlines():
        stripped = line.strip()
        if "|" not in stripped or not re.match(r"^[A-E]\.\s", stripped):
            continue
        if stripped.startswith(("Setup", "-----")):
            continue
        parts = split_pipe_line(stripped)
        if len(parts) < 7:
            continue
        setup = canonical_display_name(re.sub(r"^[A-E]\.\s*", "", parts[0]))
        grouped.setdefault(setup, {})[parts[1]] = parts

    profiles: list[Round31EntryProfile] = []
    for setup, rows in grouped.items():
        t0 = rows.get("T+0")
        t1 = rows.get("T+1")
        t2 = rows.get("T+2")
        tbest = rows.get("T+Best")
        profiles.append(
            Round31EntryProfile(
                display_name=setup,
                t0_wr=base.parse_pct(t0[3]) if t0 else None,
                t1_wr=base.parse_pct(t1[3]) if t1 else None,
                t2_wr=base.parse_pct(t2[3]) if t2 else None,
                tbest_wr=base.parse_pct(tbest[3]) if tbest else None,
                t0_pf=base.parse_float(t0[4]) if t0 else None,
                t1_pf=base.parse_float(t1[4]) if t1 else None,
                t2_pf=base.parse_float(t2[4]) if t2 else None,
                tbest_pf=base.parse_float(tbest[4]) if tbest else None,
            )
        )
    return profiles


def render_campaign_statistics(
    total_filter_evaluations: int,
    total_reports: int,
    first_date: str,
    last_date: str,
) -> list[str]:
    return [
        "Section 1: Campaign Statistics",
        "==============================",
        f"- Total rounds: {EXPECTED_TOTAL_ROUNDS} (R0-R36 + this summary).",
        f"- Total scripts created: {scripts_created_count():,} Python files in scripts/.",
        f"- Total filter evaluations: {total_filter_evaluations:,}.",
        f"- Total reports: {total_reports:,} text reports/summaries read.",
        f"- Data range: {month_range_text(first_date, last_date)}.",
        '- Campaign note: "Largest systematic NQ order flow backtesting campaign ever conducted on this dataset".',
        "",
    ]


def render_top_signals(qualifying: list[base.Finding]) -> list[str]:
    lines = [
        "Section 2: TOP 25 DEPLOY-Grade Signals (Final Ranking)",
        "=====================================================",
        "Ranking rule: OOS WR first, then full-sample WR30, then WR5, then N.",
        "",
    ]
    for index, finding in enumerate(qualifying[:25], start=1):
        oos_text = f" | OOS WR={base.fmt_pct(finding.oos_wr)}" if finding.oos_wr is not None else ""
        lines.append(
            f"{index:02d}. {finding.display_name} | N={base.fmt_count(finding.n)} | WR5={base.fmt_pct(finding.wr_5b)} | WR30={base.fmt_pct(finding.wr_30b)} | PF={base.fmt_num(finding.pf)}{oos_text} | Persistence={finding.persistence or 'n/a'} | Source={finding.discovery_round}"
        )
    lines.append("")
    return lines


def render_signal_killers(killers: list[base.Killer]) -> list[str]:
    ordered = sorted(killers, key=lambda killer: killer.delta_wr if killer.delta_wr is not None else 0.0)
    lines = [
        "Section 3: Signal Killers (Always Exclude)",
        "==========================================",
        "R7B anti-patterns that repeatedly destroyed edge inside the core 60m_extreme + 15m_trend_aligned framework:",
        "",
    ]
    for index, killer in enumerate(ordered, start=1):
        lines.append(
            f"{index}. {base.short_killer_name(killer.name)} | WR with={base.fmt_pct(killer.wr_with)} vs without={base.fmt_pct(killer.wr_without)} | Impact={base.fmt_num(killer.delta_wr, 1)}pp | N with={base.fmt_count(killer.n_with)}"
        )
    lines.append("")
    return lines


def family_highlight(spec: base.ReportSpec, findings: list[base.Finding]) -> base.Finding | None:
    candidates = FAMILY_CANDIDATES.get(spec.report_name, [])
    merged = {normalize_name(finding.display_name): finding for finding in findings}
    for candidate in candidates:
        finding = merged.get(normalize_name(candidate))
        if finding is not None:
            return finding
    viable = [finding for finding in findings if (finding.n or 0) >= 5]
    if viable:
        return max(viable, key=ranking_key_v4)
    return max(findings, key=ranking_key_v4) if findings else None


def render_family_summary_line(finding: base.Finding) -> str:
    return (
        f"{finding.display_name} | N={base.fmt_count(finding.n)} | WR5={base.fmt_pct(finding.wr_5b)} | "
        f"WR30={base.fmt_pct(finding.wr_30b)} | PF={base.fmt_num(finding.pf)}"
        + (f" | OOS={base.fmt_pct(finding.oos_wr)}" if finding.oos_wr is not None else "")
    )


def render_novel_signal_families(
    loaded_specs: list[base.ReportSpec],
    parsed_results: dict[str, base.ReportParseResult],
    auxiliary_highlights: list[prev.AuxiliaryHighlight],
) -> list[str]:
    lines = [
        "Section 4: Novel Signal Families Discovered",
        "===========================================",
    ]
    for spec in loaded_specs:
        if spec.report_name in SKIP_FAMILY_REPORTS:
            continue
        label = FAMILY_LABELS.get(spec.report_name)
        if not label:
            continue
        finding = family_highlight(spec, parsed_results[spec.report_name].findings)
        if finding is None:
            continue
        lines.append(f"- {label}: {render_family_summary_line(finding)}")

    lines.append("")
    lines.append("Ancillary absorption side studies read into the final synthesis:")
    for highlight in auxiliary_highlights:
        lines.append(f"- {highlight.label}: {highlight.summary_line}")
    lines.append("")
    return lines


def render_universal_trading_rules(
    findings: dict[str, base.Finding],
    entry_profiles: list[Round31EntryProfile],
    killers: list[base.Killer],
) -> list[str]:
    core = find_any(findings, ["60m_extreme + 15m_trend_aligned", "60m + 15m"])
    core_first_hour = find_any(findings, ["60m_extreme + 15m_trend_aligned + first_hour", "60m + 15m + first_hour"])
    cvd_core = find_any(findings, ["CVD divergence + 60m_extreme + 15m_trend_aligned", "CVD divergence + 60m + 15m"])
    stable_vol = find_any(findings, ["Stable vol + 60m_extreme + 15m_trend_aligned + first_hour", "Stable vol + 60m + 15m + first_hour"])
    doji_core = find_any(findings, ["Doji + 60m_extreme + 15m_trend_aligned", "Doji + 60m + 15m"])
    engulfing_core = find_any(findings, ["Engulfing + 60m_extreme + 15m_trend_aligned", "Engulfing + 60m + 15m"])
    hammer_core = find_any(findings, ["Hammer with volume > 2x EMA + 60m_extreme + 15m_trend_aligned", "Hammer with volume > 2x EMA + 60m + 15m"])
    adaptive_narrow = find_any(findings, ["Range < 50-bar rolling q25 + 60m + 15m"])
    fixed_narrow = find_any(findings, ["Range < fixed sample q25 + 60m + 15m"])
    score_sweet_spot = find_any(findings, ["Score 50-65 + 60m + 15m + first_hour + NOT killers", "score 50-65 + 60m + 15m + first_hour + NOT killers"])
    gap_absorption = find_any(findings, ["Gap absorption (3+ bar gap then re-absorption) + 60m + 15m", "Gap absorption + 60m + 15m"])
    ib_extension = find_any(findings, ["IB extension happened in last 5 bars + 60m + 15m"])
    ib_no_extension = find_any(findings, ["No IB extension yet today + 60m + 15m"])
    within_ib_delta_opp = find_any(findings, ["Within IB + session delta opposing + 60m + 15m + NOT killers"])
    not_lunch_absorption = find_any(findings, ["absorption + 60m + 15m + NOT lunch", "absorption + 60m_extreme + 15m_trend_aligned + NOT lunch"])

    core_profile = next((profile for profile in entry_profiles if normalize_name(profile.display_name) == normalize_name("60m + 15m + NOT killers + first_hour")), None)
    cvd_profile = next((profile for profile in entry_profiles if normalize_name(profile.display_name) == normalize_name("CVD divergence + 60m + 15m")), None)

    killer_text = "; ".join(base.short_killer_name(killer.name) for killer in sorted(killers, key=lambda row: row.delta_wr or 0.0))

    return [
        "Section 5: Universal Trading Rules (Final)",
        "=========================================",
        f"1. 60m extreme = universal edge. The core gate still carries the campaign: WR5={base.fmt_pct(core.wr_5b if core else None)}, WR30={base.fmt_pct(core.wr_30b if core else None)}, and it stayed ROBUST in all four R27 periods.",
        "2. 15m trend = strongest secondary. The winning spine never changed: every scalable or validated winner in R27/R36 kept 15m_trend_aligned on top of the 60m extreme gate.",
        f"3. First hour = optimal window. The core first-hour stack improved to WR5={base.fmt_pct(core_first_hour.wr_5b if core_first_hour else None)} / WR30={base.fmt_pct(core_first_hour.wr_30b if core_first_hour else None)}, and most elite validated stacks live there.",
        f"4. Lunch = danger zone. The best absorption execution variant is the explicit NOT-lunch stack: WR5={base.fmt_pct(not_lunch_absorption.wr_5b if not_lunch_absorption else None)}, WR30={base.fmt_pct(not_lunch_absorption.wr_30b if not_lunch_absorption else None)}, OOS={base.fmt_pct(not_lunch_absorption.oos_wr if not_lunch_absorption else None)}.",
        f"5. Edges GROW (5b->30b). Core moved {base.fmt_pct(core.wr_5b if core else None)} -> {base.fmt_pct(core.wr_30b if core else None)}; the score 50-65 sweet spot moved {base.fmt_pct(score_sweet_spot.wr_5b if score_sweet_spot else None)} -> {base.fmt_pct(score_sweet_spot.wr_30b if score_sweet_spot else None)}.",
        f"6. Exclude 4 killers. Hard-ban the recurring edge destroyers: {killer_text}.",
        f"7. CVD divergence = alpha source. The plain CVD divergence core already did WR5={base.fmt_pct(cvd_core.wr_5b if cvd_core else None)} / WR30={base.fmt_pct(cvd_core.wr_30b if cvd_core else None)}, and it remained ROBUST in R27.",
        f"8. Doji/hammer/engulfing at structure = pattern family. Doji core reached WR30={base.fmt_pct(doji_core.wr_30b if doji_core else None)}, engulfing core WR30={base.fmt_pct(engulfing_core.wr_30b if engulfing_core else None)}, and hammer-at-structure showed WR30={base.fmt_pct(hammer_core.wr_30b if hammer_core else None)} on low N.",
        f"9. Stable vol + first hour = highest WR regime. Stable vol + core + first_hour printed WR30={base.fmt_pct(stable_vol.wr_30b if stable_vol else None)} and OOS={base.fmt_pct(stable_vol.oos_wr if stable_vol else None)}.",
        f"10. Enter at T+0 (don't wait). R31 showed the executable fixed-delay hierarchy was T+0 > T+1 > T+2: core first-hour WR {base.fmt_pct(core_profile.t0_wr if core_profile else None)} vs {base.fmt_pct(core_profile.t1_wr if core_profile else None)} vs {base.fmt_pct(core_profile.t2_wr if core_profile else None)}; CVD divergence WR {base.fmt_pct(cvd_profile.t0_wr if cvd_profile else None)} vs {base.fmt_pct(cvd_profile.t1_wr if cvd_profile else None)} vs {base.fmt_pct(cvd_profile.t2_wr if cvd_profile else None)}. T+Best is hindsight, not a live rule.",
        f"11. IB extension context matters. Fresh IB extension within the last 5 bars hit WR30={base.fmt_pct(ib_extension.wr_30b if ib_extension else None)}, no-IB-extension-yet still held WR30={base.fmt_pct(ib_no_extension.wr_30b if ib_no_extension else None)}, and the within-IB + session-delta-opposing stack later validated OOS={base.fmt_pct(within_ib_delta_opp.oos_wr if within_ib_delta_opp else None)}.",
        f"12. Adaptive narrow range thresholds > fixed. Adaptive narrow range posted WR30={base.fmt_pct(adaptive_narrow.wr_30b if adaptive_narrow else None)} / PF={base.fmt_num(adaptive_narrow.pf if adaptive_narrow else None)} versus fixed narrow range WR30={base.fmt_pct(fixed_narrow.wr_30b if fixed_narrow else None)} / PF={base.fmt_num(fixed_narrow.pf if fixed_narrow else None)}.",
        f"13. Score 50-65 is the scalable sweet spot. That bracket carried N={base.fmt_count(score_sweet_spot.n if score_sweet_spot else None)}, WR30={base.fmt_pct(score_sweet_spot.wr_30b if score_sweet_spot else None)}, OOS={base.fmt_pct(score_sweet_spot.oos_wr if score_sweet_spot else None)}.",
        f"14. Gap absorption (re-test after gap) = premium setup. The R30/R36 gap-absorption stack finished with WR30={base.fmt_pct(gap_absorption.wr_30b if gap_absorption else None)} and OOS={base.fmt_pct(gap_absorption.oos_wr if gap_absorption else None)}.",
        "",
    ]


def render_indicator_build(qualifying: list[base.Finding], session_count: int) -> list[str]:
    lines = [
        "Section 6: Recommended NinjaTrader Indicator Build (Top 15)",
        "========================================================",
    ]
    for index, finding in enumerate(qualifying[:15], start=1):
        reference = finding.oos_wr if finding.oos_wr is not None else (finding.wr_30b if finding.wr_30b is not None else finding.wr_5b)
        lines.append(f"{index}. {finding.display_name}")
        lines.append(f"   - Exact definition: {finding.display_name}.")
        lines.append(f"   - Expected frequency: {base.frequency_text(finding.n, session_count)} based on N={base.fmt_count(finding.n)}.")
        lines.append(f"   - Color coding: {base.color_for_finding(finding)} | Reference WR={base.fmt_pct(reference)} | Source={finding.discovery_round}.")
    lines.append("")
    return lines


def render_exit_recommendations(recommendations: list[Round26Recommendation]) -> list[str]:
    lines = [
        "Section 7: Exit/Profit Target Recommendations",
        "============================================",
        "R9 established the default time-exit template; R26 refined it with fixed-target, ATR-target, and bracket sweeps.",
        "",
        "R9 campaign-level defaults:",
        "- Core 60m_extreme + 15m_trend_aligned: default 15b; last-hour entries can stretch to 30b.",
        "- Doji + core: default 15b all-session, 10b in first hour, 30b in last hour.",
        "- CVD divergence + core: default 10b all-session, 15b in first hour, 30b in last hour.",
        "- Failed OR breakout + core: default 15b all-session, 10b in first hour, 30b in last hour.",
        "- Absorption + core: default 10b all-session, 15b in first hour / last hour when sample exists.",
        "",
        "R26 targeted refinements:",
    ]
    for recommendation in recommendations:
        lines.append(
            f"- {recommendation.display_name}: default {recommendation.default_exit or 'n/a'} time exit (Sharpe={base.fmt_num(recommendation.default_sharpe)}, Avg={base.fmt_ticks(recommendation.default_avg_ticks)}, N={base.fmt_count(recommendation.default_n)}); best fixed target {recommendation.best_fixed_target or 'n/a'} (Hit={base.fmt_pct(recommendation.best_fixed_hit)}, Avg={base.fmt_ticks(recommendation.best_fixed_avg_ticks)}); best ATR target {recommendation.best_atr_target or 'n/a'} (Hit={base.fmt_pct(recommendation.best_atr_hit)}, Avg={base.fmt_ticks(recommendation.best_atr_avg_ticks)}); best bracket {recommendation.best_bracket or 'n/a'} (WR={base.fmt_pct(recommendation.best_bracket_wr)}, Avg={base.fmt_ticks(recommendation.best_bracket_avg_ticks)}, PF={base.fmt_num(recommendation.best_bracket_pf)})."
        )
    lines.append("")
    return lines


def render_regime_robustness(rows: list[Round27RobustnessRow]) -> list[str]:
    lines = [
        "Section 8: Regime Robustness",
        "============================",
        "R27 conclusion: all top benchmark setups were ROBUST across every requested period (Q1-Q2 2025, Q3-Q4 2025, Q1 2026, Q2 2026).",
        "",
    ]
    for row in rows:
        lines.append(
            f"- {row.display_name} | N={base.fmt_count(row.n)} | WR5={base.fmt_pct(row.wr_5b)} | PF={base.fmt_num(row.pf)} | Coverage={row.coverage} | WR spread={base.fmt_num(row.wr_spread, 1)}pp | Status={row.status}"
        )
    lines.append("")
    return lines


def render_caveats(total_filter_evaluations: int) -> list[str]:
    return [
        "Section 9: Statistical Caveats",
        "============================",
        f"- Multiple-comparisons risk is still real: {total_filter_evaluations:,} total evaluations means tail winners can still overstate live edge.",
        "- Overlap risk is extreme: many winners are nested versions of the same 60m_extreme + 15m_trend_aligned + first_hour + anti-killer backbone. Do not treat them as independent bets.",
        "- Several headline R29/R30 absorption variants are real but tiny-N; treat them as premium overlays, not the automation backbone.",
        "- R31 T+Best is an oracle benchmark, not an executable entry rule. Use it to prove value of early entry, not to design live fills.",
        "- R36 confirmed some brief-defined stacks were structurally empty or insufficient. When a combo never trades, that is a real result, not missing data.",
        "- Prior master summaries were read for continuity, but the underlying round reports take precedence whenever a summary and a raw round report differ.",
        "",
    ]


def total_filter_evaluation_count(loaded_specs: list[base.ReportSpec], auxiliary_highlights: list[prev.AuxiliaryHighlight]) -> int:
    total = sum(spec.filter_count or 0 for spec in loaded_specs)
    total += ROUND9_EXTRA_EXIT_ROWS
    total += ROUND26_EXTRA_EXIT_ROWS
    total += sum(highlight.evaluation_count for highlight in auxiliary_highlights)
    return total


def build_report() -> str:
    primary_specs = build_primary_specs()
    loaded_specs = [spec for spec in primary_specs if spec.path.exists()]
    parsed_results = {spec.report_name: parse_report(spec) for spec in loaded_specs}

    all_findings = [finding for result in parsed_results.values() for finding in result.findings]
    killers = [killer for result in parsed_results.values() for killer in result.killers]
    merged = base.merge_findings(all_findings)
    qualifying = deploy_grade_v4(merged)

    matched_report_paths, extra_report_paths, all_text_report_paths = discover_text_report_paths()
    auxiliary_highlights = prev.parse_auxiliary_reports()
    round26_recommendations = parse_round26_recommendations()
    round27_rows = parse_round27_robustness_rows()
    round31_profiles = parse_round31_entry_profiles()

    first_date, last_date, session_count = base.load_calendar_stats()
    total_filter_evaluations = total_filter_evaluation_count(loaded_specs, auxiliary_highlights)

    lines = [
        "MASTER BACKTEST SUMMARY V4",
        "==========================",
        "Final definitive reference document for the full DEEP6 round0-round36 campaign. This replaces all prior master summaries.",
        "",
    ]
    lines.extend(
        render_campaign_statistics(
            total_filter_evaluations=total_filter_evaluations,
            total_reports=len(all_text_report_paths),
            first_date=first_date,
            last_date=last_date,
        )
    )
    lines.extend(render_top_signals(qualifying))
    lines.extend(render_signal_killers(killers))
    lines.extend(render_novel_signal_families(loaded_specs, parsed_results, auxiliary_highlights))
    lines.extend(render_universal_trading_rules(merged, round31_profiles, killers))
    lines.extend(render_indicator_build(qualifying, session_count))
    lines.extend(render_exit_recommendations(round26_recommendations))
    lines.extend(render_regime_robustness(round27_rows))
    lines.extend(render_caveats(total_filter_evaluations))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
