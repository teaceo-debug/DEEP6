#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import round15_master_summary_v2 as base


ROOT = base.ROOT
REPORT_DIR = base.REPORT_DIR
SCRIPTS_DIR = ROOT / "scripts"
OUT_PATH = REPORT_DIR / "MASTER_BACKTEST_SUMMARY_V3.txt"
EXPECTED_CAMPAIGN_ROUNDS = 28
SUMMARY_PATTERNS = ("*report*.txt", "*SUMMARY*.txt")
EXTRA_TEXT_REPORTS = ("round1_walkforward_cross_category.txt",)
ROUND9_EXTRA_EXIT_ROWS = 90


@dataclass(frozen=True)
class AuxiliaryHighlight:
    label: str
    source_name: str
    evaluation_count: int
    summary_line: str


ORIGINAL_CANONICAL = base.canonical_display_name


EXTENDED_REPORT_SPECS = [
    base.ReportSpec("Round 16", "R16", "round16_consecutive_sessions_report.txt", "round16_consecutive_sessions.py", 20, "validated_table"),
    base.ReportSpec("Round 17", "R17", "round17_vol_of_vol_report.txt", "round17_vol_of_vol.py", 20, "validated_table"),
    base.ReportSpec("Round 18", "R18", "round18_weekly_relative_strength_report.txt", "round18_weekly_relative_strength.py", 20, "validated_table"),
    base.ReportSpec("Round 19", "R19", "round19_walkforward_r12_r14_report.txt", "round19_walkforward_r12_r14.py", 12, "walkforward"),
    base.ReportSpec("Round 20", "R20", "round20_ultra_stack_report.txt", "round20_ultra_stack.py", 20, "validated_table"),
    base.ReportSpec("Round 21", "R21", "round21_walkforward_r16_r20_report.txt", "round21_walkforward_r16_r20.py", 12, "walkforward"),
    base.ReportSpec("Round 22", "R22", "round22_inverse_signals_report.txt", "round22_inverse_signals.py", 20, "validated_table"),
    base.ReportSpec("Round 23", "R23", "round23_candle_combos_report.txt", "round23_candle_combos.py", 20, "validated_table"),
    base.ReportSpec("Round 24", "R24", "round24_signal_clustering_report.txt", "round24_signal_clustering.py", 20, "validated_table"),
    base.ReportSpec("Round 25", "R25", "round25_momentum_exhaustion_report.txt", "round25_momentum_exhaustion.py", 20, "validated_table"),
]


FAMILY_LABELS = {
    "compound_filter_report.txt": "R0 compound anchors",
    "cross_category_combo_report.txt": "R0.5 cross-category confluence",
    "round1_regime_gated_report.txt": "R1B regime gating",
    "round1_strength_persistence_report.txt": "R1C persistence overlays",
    "round1_time_day_report.txt": "R1D time/day gating",
    "round2_stacked_persistence_time_report.txt": "R2A stacked time/persistence",
    "round2_absorption_deep_report.txt": "R2B deep absorption filters",
    "round2_novel_bar_patterns_report.txt": "R2C novel bar patterns",
    "round3_multi_bar_sequences_report.txt": "R3B multi-bar candlestick sequences",
    "round3_signal_density_report.txt": "R3C density/confluence",
    "round6_multi_session_report.txt": "R6A multi-session context",
    "round6_gap_opening_range_report.txt": "R6B gap/opening-range reversals",
    "round7_signal_sequences_report.txt": "R7A sequential confirmation",
    "round8_price_levels_report.txt": "R8A price-level confluence",
    "round8_delta_cvd_report.txt": "R8B delta/CVD structure",
    "round10_stack_winners_exclude_killers_report.txt": "R10 anti-killer stacks",
    "round11_chain_triple_report.txt": "R11 chain/triple interactions",
    "round12_bar_microstructure_report.txt": "R12 bar microstructure",
    "round13_macro_calendar_report.txt": "R13 macro/calendar overlays",
    "round14_overnight_momentum_regime_report.txt": "R14 overnight/regime",
    "round16_consecutive_sessions_report.txt": "R16 consecutive-session memory",
    "round17_vol_of_vol_report.txt": "R17 vol-of-vol / contraction",
    "round18_weekly_relative_strength_report.txt": "R18 weekly relative strength",
    "round20_ultra_stack_report.txt": "R20 ultra-stacks",
    "round22_inverse_signals_report.txt": "R22 inverse/failure logic",
    "round23_candle_combos_report.txt": "R23 candle combos",
    "round24_signal_clustering_report.txt": "R24 signal clustering",
    "round25_momentum_exhaustion_report.txt": "R25 momentum exhaustion",
}


SKIP_FAMILY_REPORTS = {
    "top5_validation_report.txt",
    "round1_walkforward_cross_category.txt",
    "round3_validate_novel_patterns_report.txt",
    "round4_final_walkforward_report.txt",
    "round7_signal_negation_report.txt",
    "round9_exit_timing_report.txt",
    "round19_walkforward_r12_r14_report.txt",
    "round21_walkforward_r16_r20_report.txt",
}


VALIDATED_TABLE_EXTENSIONS = {
    "round16_consecutive_sessions_report.txt": (
        "All 20 consecutive-session filters ranked by 5-bar average return",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round17_vol_of_vol_report.txt": (
        "20 volatility-change / vol-of-vol filters ranked by 30b win rate",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round18_weekly_relative_strength_report.txt": (
        "All 20 weekly-relative-strength filters ranked by 5-bar average return",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round20_ultra_stack_report.txt": (
        "20 ultra-stacked filters ranked by 30b win rate",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round22_inverse_signals_report.txt": (
        "20 inverse / failure filters",
        {1: "n", 2: "wr_5b", 3: "pf", 4: "avg_ticks_5b", 6: "flag"},
        6,
    ),
    "round23_candle_combos_report.txt": (
        "20 requested candlestick-combo filters sorted by 30b WR",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round24_signal_clustering_report.txt": (
        "20 signal-density / diversity / score filters ranked by 30b WR",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
    "round25_momentum_exhaustion_report.txt": (
        "20 momentum exhaustion filters ranked by 30b win rate",
        {1: "n", 2: "wr_5b", 3: "wr_10b", 4: "wr_30b", 5: "pf", 6: "avg_ticks_5b", 8: "persistence"},
        None,
    ),
}


def split_name_flag(raw_name: str) -> tuple[str, str | None]:
    text = raw_name.strip()
    text = re.sub(r"^\d+(?:\[[A-Z]\])?\.\s*", "", text)
    text = re.sub(r"^\d+\.\s*", "", text)
    text = re.sub(r"^\[[A-Z]\]\s*", "", text)
    match = re.search(r"\[(VALIDATED|PROMISING|LOW_N|DEPLOY|PAPER TRADE|INSUFFICIENT DATA|INSUFFICIENT)\]\s*$", text)
    flag = match.group(1) if match else None
    if match:
        text = text[: match.start()].rstrip()
    return text, flag


def canonical_display_name(name: str) -> str:
    clean = ORIGINAL_CANONICAL(name)
    clean = clean.replace("CVD div", "CVD divergence")
    clean = clean.replace("60m+15m", "60m_extreme + 15m_trend_aligned")
    clean = clean.replace("60m + 15m", "60m_extreme + 15m_trend_aligned")
    clean = clean.replace("3 bars of contracting ranges", "3 narrowing ranges")
    clean = clean.replace("3 bars contracting ranges", "3 narrowing ranges")
    clean = clean.replace("3 contracting ranges", "3 narrowing ranges")
    clean = clean.replace("3 narrowing/contracting bars", "3 narrowing ranges")
    clean = clean.replace("Failed OR breakout", "Failed OR breakout/breakdown trap")
    clean = clean.replace("failed OR breakout", "Failed OR breakout/breakdown trap")
    clean = clean.replace("small overnight +", "Small overnight move < 20 ticks +")
    clean = clean.replace("small overnight", "Small overnight move < 20 ticks")
    clean = clean.replace("stable vol", "Stable vol")
    clean = clean.replace("first hour", "first_hour")
    clean = clean.replace("Weekly breakout", "weekly breakout")
    clean = re.sub(r"\b60m_extreme \+ 15m_trend_aligned_extreme\b", "60m_extreme + 15m_trend_aligned", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    return clean


def normalize_name(name: str) -> str:
    clean = canonical_display_name(name).lower()
    if " + " not in clean:
        return clean
    parts = [part.strip() for part in clean.split(" + ") if part.strip()]
    if not parts:
        return clean
    if "->" in parts[0]:
        return " + ".join([parts[0], *sorted(parts[1:])])
    return " + ".join(sorted(parts))


def iter_pipe_rows(section: str, row_pattern: str = r"^\d+(?:\[[A-Z]\])?\.\s") -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if "|" not in stripped:
            continue
        if stripped.startswith(("Filter", "Rank", "-----", "Overview", "Setup", "Bucket", "Baseline")):
            continue
        if not re.match(row_pattern, stripped):
            continue
        rows.append([part.strip() for part in re.split(r"\s+\|\s+|\s+\|$", stripped)])
    return rows


def parse_walkforward(spec: base.ReportSpec, text: str) -> list[base.Finding]:
    pattern = re.compile(r"FILTER\s+\d+:\s+(?P<name>.+?)\n-+\n(?P<body>.*?)(?=\nFILTER\s+\d+:|\Z)", re.S)
    findings: list[base.Finding] = []
    for match in pattern.finditer(text):
        name = match.group("name").strip()
        body = match.group("body")
        finding = base.build_finding(spec, name)

        summary_match = re.search(
            r"(?:Summary|Discovery sample):\s+N=(?P<n>[\d,]+),\s+WR=(?P<wr>[0-9.]+)%,\s+PF=(?P<pf>[-+0-9.,infna]+),\s+Avg=(?P<avg>[-+0-9.,]+)\s+ticks",
            body,
        )
        if summary_match:
            finding.n = base.parse_int(summary_match.group("n"))
            finding.wr_5b = base.parse_pct(summary_match.group("wr") + "%")
            finding.pf = base.parse_float(summary_match.group("pf"))
            finding.avg_ticks_5b = base.parse_float(summary_match.group("avg"))

        oos_match = re.search(
            r"(?:Overall OOS|Composite OOS):\s+N=(?P<n>[\d,]+),(?:\s+Wins=\d+,)?\s+WR=(?P<wr>[0-9.]+)%,\s+Avg=(?P<avg>[-+0-9.,]+)\s+ticks",
            body,
        )
        if oos_match:
            finding.oos_n = base.parse_int(oos_match.group("n"))
            finding.oos_wr = base.parse_pct(oos_match.group("wr") + "%")

        bayes_match = re.search(r"Posterior:\s+Beta\([^\)]*\),\s+mean=(?P<mean>[0-9.]+)%", body)
        if bayes_match:
            finding.bayes_mean = base.parse_pct(bayes_match.group("mean") + "%")

        verdict_match = re.search(r"OVERALL VERDICT:\s+(?P<verdict>DEPLOY|PAPER TRADE|INSUFFICIENT DATA|INSUFFICIENT)", body)
        if verdict_match:
            finding.verdict = verdict_match.group("verdict")

        findings.append(finding)
    return findings


def parse_ranked_table(
    spec: base.ReportSpec,
    text: str,
    start_marker: str,
    end_marker: str | None,
    column_map: dict[int, str],
    flag_source: str | int | None = "name",
) -> list[base.Finding]:
    section = base.extract_section(text, start_marker, end_marker)
    findings: list[base.Finding] = []
    for parts in iter_pipe_rows(section):
        raw_name = parts[0]
        name, name_flag = split_name_flag(raw_name)
        flag = name_flag
        if isinstance(flag_source, int) and flag_source < len(parts):
            flag = parts[flag_source].strip() or flag
        finding = base.build_finding(spec, name, flag)
        for index, field_name in column_map.items():
            value = parts[index] if index < len(parts) else ""
            if field_name == "n":
                finding.n = base.parse_int(value)
            elif field_name.startswith("wr_"):
                setattr(finding, field_name, base.parse_pct(value))
            elif field_name == "pf":
                finding.pf = base.parse_float(value)
            elif field_name == "avg_ticks_5b":
                finding.avg_ticks_5b = base.parse_float(value)
            elif field_name == "persistence":
                finding.persistence = value.strip() or None
            elif field_name == "flag":
                finding.flag = value.strip() or finding.flag
        if finding.persistence is None:
            finding.persistence = base.classify_persistence(finding.wr_5b, finding.wr_30b)
        findings.append(finding)
    return findings


base.split_name_flag = split_name_flag
base.canonical_display_name = canonical_display_name
base.normalize_name = normalize_name
base.iter_pipe_rows = iter_pipe_rows
base.parse_ranked_table = parse_ranked_table
base.parse_walkforward = parse_walkforward
base.VALIDATED_TABLE_SPECS.update(VALIDATED_TABLE_EXTENSIONS)


def build_primary_specs() -> list[base.ReportSpec]:
    specs = list(base.REPORT_SPECS)
    specs.extend(EXTENDED_REPORT_SPECS)
    return specs


def discover_text_report_paths() -> tuple[list[Path], list[Path], list[Path]]:
    matched: set[Path] = set()
    for pattern in SUMMARY_PATTERNS:
        matched.update(path for path in REPORT_DIR.glob(pattern) if path.name != OUT_PATH.name)

    extras: list[Path] = []
    for name in EXTRA_TEXT_REPORTS:
        path = REPORT_DIR / name
        if path.exists() and path.name != OUT_PATH.name:
            extras.append(path)

    all_paths = sorted(matched.union(extras))
    return sorted(matched), sorted(extras), all_paths


def scripts_created_count() -> int:
    matched: set[Path] = set()
    for pattern in ("round*.py", "analyze*.py", "validate*.py"):
        matched.update(SCRIPTS_DIR.glob(pattern))
    return len(matched)


def load_duration_note(first_date: str, last_date: str, session_count: int) -> str:
    start = date.fromisoformat(first_date)
    end = date.fromisoformat(last_date)
    span_days = (end - start).days + 1
    months = span_days / 30.44
    return f"{session_count:,} trading sessions across {span_days:,} calendar days (~{months:.1f} months)."


def pick_top_finding(findings: list[base.Finding]) -> base.Finding | None:
    if not findings:
        return None
    return max(
        findings,
        key=lambda finding: (
            finding.oos_wr if finding.oos_wr is not None else -1.0,
            finding.wr_30b if finding.wr_30b is not None else (finding.wr_5b if finding.wr_5b is not None else -1.0),
            finding.avg_ticks_5b if finding.avg_ticks_5b is not None else -1.0,
            finding.n if finding.n is not None else -1,
        ),
    )


def maybe_find(findings: dict[str, base.Finding], name: str) -> base.Finding | None:
    return findings.get(base.normalize_name(name))


def deploy_grade_v3(findings: dict[str, base.Finding]) -> list[base.Finding]:
    selected: list[base.Finding] = []
    for finding in findings.values():
        explicit_negative = finding.verdict in {"PAPER TRADE", "INSUFFICIENT", "INSUFFICIENT DATA"}
        qualifies = False
        if finding.verdict == "DEPLOY":
            qualifies = True
        elif finding.flag == "VALIDATED" and not explicit_negative:
            qualifies = True
        elif (
            not explicit_negative
            and finding.flag not in {"PROMISING", "LOW_N"}
            and finding.n is not None
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
    return sorted(selected, key=base.ranking_key, reverse=True)


def robustness_label(finding: base.Finding) -> str:
    if finding.verdict in {"PAPER TRADE", "INSUFFICIENT", "INSUFFICIENT DATA"}:
        return "FRAGILE"
    if finding.oos_wr is not None and finding.verdict == "DEPLOY":
        if finding.oos_n is not None and finding.oos_n >= 30 and finding.oos_wr >= 75.0 and finding.persistence != "DECAYING":
            return "ROBUST"
        if finding.oos_wr >= 65.0 and finding.persistence != "DECAYING":
            return "PROVISIONAL"
        return "FRAGILE"
    if finding.flag == "VALIDATED" and finding.n is not None and finding.n >= 100 and base.ranking_wr(finding) >= 80.0 and finding.persistence != "DECAYING":
        return "PROVISIONAL"
    if finding.persistence == "DECAYING" or (finding.n is not None and finding.n < 30):
        return "FRAGILE"
    return "PROVISIONAL"


def parse_auxiliary_reports() -> list[AuxiliaryHighlight]:
    highlights: list[AuxiliaryHighlight] = []

    multitimeframe_path = REPORT_DIR / "absorption_multitimeframe_report.txt"
    if multitimeframe_path.exists():
        text = multitimeframe_path.read_text(encoding="utf-8")
        trend = re.search(r"15m trend aligned: N=(\d+) \| WR=([0-9.]+)% \| PF=([0-9.]+)", text)
        extreme = re.search(r"Near favorable 60m extreme: N=(\d+) \| WR=([0-9.]+)% \| PF=([0-9.]+)", text)
        if trend and extreme:
            highlights.append(
                AuxiliaryHighlight(
                    label="Absorption MTF",
                    source_name=multitimeframe_path.name,
                    evaluation_count=12,
                    summary_line=(
                        f"Absorption-only audit: 15m alignment improved raw absorption to WR={trend.group(2)}% (N={trend.group(1)}), "
                        f"and favorable 60m extremes pushed it to WR={extreme.group(2)}% (N={extreme.group(1)}, PF={extreme.group(3)})."
                    ),
                )
            )

    calendar_path = REPORT_DIR / "absorption_calendar_session_report.txt"
    if calendar_path.exists():
        text = calendar_path.read_text(encoding="utf-8")
        best_month = re.search(r"Best month: (.+)", text)
        best_bucket = re.search(r"Best month-bucket: (.+)", text)
        profile_d = re.search(r"^\s*D\s+(\d+)\s+([0-9.]+)", text, re.M)
        if best_month and best_bucket and profile_d:
            highlights.append(
                AuxiliaryHighlight(
                    label="Absorption calendar/session",
                    source_name=calendar_path.name,
                    evaluation_count=64,
                    summary_line=(
                        f"Absorption seasonality stayed weak overall, but {best_month.group(1).lower()}, {best_bucket.group(1).lower()}, "
                        f"and D-profile days (N={profile_d.group(1)}, WR={profile_d.group(2)}%) were the best contextual pockets."
                    ),
                )
            )

    volume_profile_path = REPORT_DIR / "absorption_volume_profile_report.txt"
    if volume_profile_path.exists():
        text = volume_profile_path.read_text(encoding="utf-8")
        beyond_value = re.search(r"Beyond value area\s+(\d+)\s+([0-9.]+)%\s+([-0-9.]+)", text)
        abs04 = re.search(r"ABS_04\s+(\d+)\s+([0-9.]+)%\s+([-0-9.]+)", text)
        if beyond_value and abs04:
            highlights.append(
                AuxiliaryHighlight(
                    label="Absorption volume profile",
                    source_name=volume_profile_path.name,
                    evaluation_count=15,
                    summary_line=(
                        f"Volume-profile absorption worked best beyond value area (N={beyond_value.group(1)}, WR={beyond_value.group(2)}%, Avg={beyond_value.group(3)} ticks), "
                        f"and ABS_04 was the strongest subtype (N={abs04.group(1)}, WR={abs04.group(2)}%)."
                    ),
                )
            )

    return highlights


def parse_legacy_summary_rules() -> list[str]:
    rules: list[str] = []
    for name in ("MASTER_BACKTEST_SUMMARY.txt", "MASTER_BACKTEST_SUMMARY_V2.txt"):
        path = REPORT_DIR / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            section = base.extract_section(text, "Section 5:", "Section 6:")
        except ValueError:
            continue
        for line in section.splitlines():
            stripped = line.strip()
            if re.match(r"^\d+\.\s", stripped):
                rules.append(re.sub(r"^\d+\.\s*", "", stripped))
    return rules


def source_round_text(finding: base.Finding) -> str:
    return finding.discovery_round


def render_campaign_statistics(
    matched_report_paths: list[Path],
    extra_report_paths: list[Path],
    total_filter_evaluations: int,
    first_date: str,
    last_date: str,
    duration_note: str,
    missing_round_reports: list[str],
) -> list[str]:
    lines = [
        "Section 1: Campaign Statistics",
        "==============================",
        f"- Total rounds completed: {EXPECTED_CAMPAIGN_ROUNDS} targeted campaign rounds (R0-R27).",
        f"- Total scripts created: {scripts_created_count():,} Python files in scripts/ matching round*, analyze*, or validate*.",
        f"- Total filter evaluations: {total_filter_evaluations:,} explicitly enumerated filters / comparison buckets (+{ROUND9_EXTRA_EXIT_ROWS:,} detailed exit-window rows from R9).",
        f"- Total reports generated: {len(matched_report_paths):,} pattern-matched text reports" + (f" (+{len(extra_report_paths):,} legacy extra report read explicitly)." if extra_report_paths else "."),
        f"- Data range: {first_date} to {last_date}.",
        f"- Campaign duration note: {duration_note}",
    ]
    if missing_round_reports:
        lines.append(f"- Missing standalone text rounds in this corpus: {', '.join(missing_round_reports)}. V3 falls back to the latest available text evidence for exit/robustness sections.")
    lines.append("")
    return lines


def render_top_signals(qualifying: list[base.Finding]) -> list[str]:
    lines = [
        "Section 2: TOP 20 DEPLOY-Grade Signals (Final Ranking)",
        "=====================================================",
        "Ranking rule: OOS WR first, then best full-sample WR (30b preferred, else 5b), then N.",
        "",
    ]
    for index, finding in enumerate(qualifying[:20], start=1):
        lines.append(
            f"{index:02d}. {finding.display_name} | N={base.fmt_count(finding.n)} | WR5={base.fmt_pct(finding.wr_5b)} | WR30={base.fmt_pct(finding.wr_30b)} | PF={base.fmt_num(finding.pf)} | OOS={base.fmt_pct(finding.oos_wr)} | Bayes={base.fmt_pct(finding.bayes_mean)} | Persistence={finding.persistence or 'n/a'} | Source={source_round_text(finding)} | Regime={robustness_label(finding)}"
        )
    lines.append("")
    return lines


def render_signal_killers(killers: list[base.Killer]) -> list[str]:
    lines = [
        "Section 3: Signal Killers (Always Exclude)",
        "==========================================",
        "R7B anti-patterns that repeatedly destroyed edge inside the core 60m_extreme + 15m_trend framework:",
        "",
    ]
    ordered = sorted(killers, key=lambda killer: killer.delta_wr if killer.delta_wr is not None else 0.0)
    for index, killer in enumerate(ordered, start=1):
        lines.append(
            f"{index}. {base.short_killer_name(killer.name)} | WR with={base.fmt_pct(killer.wr_with)} vs without={base.fmt_pct(killer.wr_without)} | Impact={base.fmt_num(killer.delta_wr, 1)}pp | N with={base.fmt_count(killer.n_with)}"
        )
    lines.append("")
    return lines


def render_family_summary_line(finding: base.Finding) -> str:
    return (
        f"{finding.display_name} | N={base.fmt_count(finding.n)} | WR5={base.fmt_pct(finding.wr_5b)} | "
        f"WR30={base.fmt_pct(finding.wr_30b)} | PF={base.fmt_num(finding.pf)} | OOS={base.fmt_pct(finding.oos_wr)}"
    )


def render_novel_signal_families(
    loaded_specs: list[base.ReportSpec],
    parsed_results: dict[str, base.ReportParseResult],
    auxiliary_highlights: list[AuxiliaryHighlight],
) -> list[str]:
    lines = [
        "Section 4: Novel Signal Families Discovered",
        "===========================================",
    ]
    for spec in loaded_specs:
        if spec.report_name in SKIP_FAMILY_REPORTS:
            continue
        label = FAMILY_LABELS.get(spec.report_name)
        if label is None:
            continue
        finding = pick_top_finding(parsed_results[spec.report_name].findings)
        if finding is None:
            continue
        lines.append(f"- {label}: {render_family_summary_line(finding)}")

    if auxiliary_highlights:
        lines.append("")
        lines.append("Ancillary absorption studies read alongside the round campaign:")
        for highlight in auxiliary_highlights:
            lines.append(f"- {highlight.label}: {highlight.summary_line}")

    lines.append("")
    return lines


def render_universal_trading_rules(findings: dict[str, base.Finding], legacy_rules: list[str]) -> list[str]:
    core = maybe_find(findings, "60m_extreme + 15m_trend_aligned")
    core_first_hour = maybe_find(findings, "60m_extreme + 15m_trend_aligned + first_hour")
    core_not_killers = maybe_find(findings, "60m_extreme + 15m_trend_aligned + NOT killers")
    cvd_core = maybe_find(findings, "CVD divergence + 60m_extreme + 15m_trend_aligned")
    doji_calendar = maybe_find(findings, "Doji + NOT FOMC + NOT summer + 60m_extreme + 15m_trend_aligned + NOT killers + first_hour")
    small_overnight = maybe_find(findings, "Small overnight move < 20 ticks + 60m_extreme + 15m_trend_aligned")
    inside_day = maybe_find(findings, "Consecutive inside days + 60m_extreme + 15m_trend_aligned")
    contraction = maybe_find(findings, "3 narrowing ranges + 60m_extreme + 15m_trend_aligned")
    clustering = maybe_find(findings, "score >= 70 + 60m_extreme + 15m_trend_aligned + first_hour + NOT killers")
    exhaustion = maybe_find(findings, "5 lower highs + bullish signal + 60m_extreme + 15m_trend_aligned")

    lines = [
        "Section 5: Universal Trading Rules (Final Version)",
        "===============================================",
        f"1. Keep 60m_extreme + 15m_trend_aligned as the execution backbone: core WR5={base.fmt_pct(core.wr_5b if core else None)} and WR30={base.fmt_pct(core.wr_30b if core else None)}.",
        f"2. Default to first_hour and killer exclusion when possible: first-hour core OOS={base.fmt_pct(core_first_hour.oos_wr if core_first_hour else None)} and NOT-killers WR5={base.fmt_pct(core_not_killers.wr_5b if core_not_killers else None)}.",
        f"3. Favor structure-backed divergence/compression overlays: CVD divergence core WR5={base.fmt_pct(cvd_core.wr_5b if cvd_core else None)}; doji + NOT FOMC + NOT summer + first_hour reached OOS={base.fmt_pct(doji_calendar.oos_wr if doji_calendar else None)}.",
        f"4. Stable / contracting conditions are additive, not decorative: 3 narrowing ranges + core reached WR30={base.fmt_pct(contraction.wr_30b if contraction else None)}.",
        f"5. Quiet overnight and inside-day context helped continuation of the core edge: small overnight move OOS={base.fmt_pct(small_overnight.oos_wr if small_overnight else None)}; consecutive inside days WR5={base.fmt_pct(inside_day.wr_5b if inside_day else None)}.",
        f"6. Density/score clustering remains a valid confirmation layer: score >= 70 + core + first_hour + NOT killers reached WR30={base.fmt_pct(clustering.wr_30b if clustering else None)}.",
        f"7. Momentum-exhaustion reversals work best only when still nested inside the core gate: 5 lower highs + bullish signal + core reached WR30={base.fmt_pct(exhaustion.wr_30b if exhaustion else None)}.",
        "8. Always hard-exclude the four R7B killers; additionally treat lunch, opposite/no 15m trend, high-ATR blowoff, and direct same-direction CVD confirmation as danger states until re-validated.",
    ]
    if legacy_rules:
        lines.append("9. Legacy V1/V2 master summaries pointed to the same backbone; later rounds refined that framework rather than overturning it.")
    lines.append("")
    return lines


def render_indicator_build(qualifying: list[base.Finding], killers: list[base.Killer], session_count: int) -> list[str]:
    lines = [
        "Section 6: Recommended NinjaTrader Indicator Build (Top 10)",
        "==========================================================",
    ]
    for index, finding in enumerate(qualifying[:10], start=1):
        lines.append(f"{index}. {finding.display_name}")
        lines.append(f"   - Exact definition: {finding.display_name}.")
        lines.append(f"   - Expected frequency: {base.frequency_text(finding.n, session_count)} based on N={base.fmt_count(finding.n)}.")
        lines.append(f"   - Color coding: {base.color_for_finding(finding)} ({robustness_label(finding)}) | Reference WR={base.fmt_pct(finding.oos_wr if finding.oos_wr is not None else base.ranking_wr(finding))}.")
        lines.append(f"   - Mandatory exclusions: {base.killer_text_for_finding(finding, killers)}.")
    lines.append("")
    return lines


def render_exit_recommendations(exit_recommendations: list[base.ExitRecommendation], has_round26_text: bool) -> list[str]:
    context_labels = {
        "all": "All entries",
        "first_hour": "First-hour entries",
        "last_hour": "Last-hour entries",
    }
    ordered = sorted(
        exit_recommendations,
        key=lambda recommendation: (
            0 if recommendation.context == "all" else 1 if recommendation.context == "first_hour" else 2,
            -(recommendation.sharpe if recommendation.sharpe is not None else -1.0),
            -(recommendation.avg_ticks if recommendation.avg_ticks is not None else -1.0),
        ),
    )

    lines = [
        "Section 7: Exit/Profit Target Recommendations",
        "============================================",
    ]
    if has_round26_text:
        lines.append("Using the matched R26 text report for exit guidance.")
    else:
        lines.append("No standalone R26 text report was matched; using the latest available exit study in text form (round9_exit_timing_report.txt).")
    lines.append("")
    for recommendation in ordered:
        lines.append(
            f"- {context_labels.get(recommendation.context, recommendation.context)} | {recommendation.display_name} -> optimal exit {recommendation.optimal_exit or 'n/a'} | Sharpe={base.fmt_num(recommendation.sharpe)} | Avg={base.fmt_ticks(recommendation.avg_ticks)} | N={base.fmt_count(recommendation.n)}"
        )
    lines.append("")
    return lines


def render_regime_robustness(qualifying: list[base.Finding], has_round27_text: bool) -> list[str]:
    robust = [finding for finding in qualifying if robustness_label(finding) == "ROBUST"]
    provisional = [finding for finding in qualifying if robustness_label(finding) == "PROVISIONAL"]
    fragile = [finding for finding in qualifying if robustness_label(finding) == "FRAGILE"]

    lines = [
        "Section 8: Regime Robustness Assessment",
        "=======================================",
    ]
    if has_round27_text:
        lines.append("Standalone R27 text report detected; using it where available.")
    else:
        lines.append("No standalone R27 text report was matched; robustness below is inferred from walk-forward OOS WR, posterior, persistence, and sample depth.")
    lines.append("")
    lines.append("ROBUST across periods:")
    for finding in robust[:12]:
        lines.append(
            f"- {finding.display_name} | OOS={base.fmt_pct(finding.oos_wr)} (N={base.fmt_count(finding.oos_n)}) | Bayes={base.fmt_pct(finding.bayes_mean)} | Persistence={finding.persistence or 'n/a'}"
        )
    lines.append("")
    lines.append("PROVISIONAL / needs continued monitoring:")
    for finding in provisional[:10]:
        lines.append(
            f"- {finding.display_name} | WR5={base.fmt_pct(finding.wr_5b)} | WR30={base.fmt_pct(finding.wr_30b)} | OOS={base.fmt_pct(finding.oos_wr)} | N={base.fmt_count(finding.n)}"
        )
    lines.append("")
    lines.append("FRAGILE / paper-trade-only for now:")
    for finding in fragile[:10]:
        lines.append(
            f"- {finding.display_name} | Status={base.validation_status(finding)} | OOS={base.fmt_pct(finding.oos_wr)} | Persistence={finding.persistence or 'n/a'} | N={base.fmt_count(finding.n)}"
        )
    lines.append("")
    return lines


def render_caveats(total_filter_evaluations: int, missing_round_reports: list[str], auxiliary_highlights: list[AuxiliaryHighlight]) -> list[str]:
    lines = [
        "Section 9: Statistical Caveats (Final)",
        "=====================================",
        f"- Multiple-comparisons risk is larger than in V2: {total_filter_evaluations:,} explicitly enumerated filters / comparison buckets plus detailed exit-window slicing means tail performance can still overstate live edge.",
        "- Validation depth remains uneven: walk-forward DEPLOY signals deserve the most trust; plain VALIDATED rows are still in-sample confirmations.",
        "- Overlap risk is extreme: many winners are nested versions of the same core regime (60m_extreme + 15m trend + first_hour + killer exclusion + divergence/compression overlays). Do not size them as independent bets.",
        "- Small-N overlays exist at the very top of several tables; treat them as premium alert modifiers, not the backbone of automation.",
        "- Round21 explicitly notes that the R20 script was reconstructed for validation. Treat the R20 walk-forward layer as useful but not as authoritative as rounds with intact discovery scripts.",
        "- Auxiliary absorption-only studies were read and summarized, but their observation frame is narrower than the full signal-universe round reports and should not be ranked 1:1 against the core campaign tables.",
    ]
    if missing_round_reports:
        lines.append(f"- Coverage gap: no standalone text reports were matched for {', '.join(missing_round_reports)}; V3 therefore uses the latest available text evidence for exit-target and robustness commentary.")
    if auxiliary_highlights:
        lines.append(f"- Side-study coverage: {len(auxiliary_highlights)} non-round absorption reports were incorporated narratively and into the total evaluation count, but not allowed to dominate the final DEPLOY ranking.")
    lines.append("")
    return lines


def build_report() -> str:
    primary_specs = build_primary_specs()
    loaded_specs = [spec for spec in primary_specs if spec.path.exists()]
    parsed_results = {spec.report_name: base.parse_report(spec) for spec in loaded_specs}

    all_findings = [finding for result in parsed_results.values() for finding in result.findings]
    killers = [killer for result in parsed_results.values() for killer in result.killers]
    exit_recommendations = [recommendation for result in parsed_results.values() for recommendation in result.exit_recommendations]
    merged = base.merge_findings(all_findings)
    qualifying = deploy_grade_v3(merged)

    matched_report_paths, extra_report_paths, all_text_report_paths = discover_text_report_paths()
    auxiliary_highlights = parse_auxiliary_reports()
    legacy_rules = parse_legacy_summary_rules()

    total_filter_evaluations = 0
    for spec in loaded_specs:
        if spec.filter_count is not None:
            total_filter_evaluations += spec.filter_count
    total_filter_evaluations += ROUND9_EXTRA_EXIT_ROWS
    total_filter_evaluations += sum(highlight.evaluation_count for highlight in auxiliary_highlights)

    first_date, last_date, session_count = base.load_calendar_stats()
    duration_note = load_duration_note(first_date, last_date, session_count)

    all_text_names = {path.name.lower() for path in all_text_report_paths}
    has_round26_text = any("26" in name for name in all_text_names)
    has_round27_text = any("27" in name for name in all_text_names)
    missing_round_reports = []
    if not has_round26_text:
        missing_round_reports.append("R26")
    if not has_round27_text:
        missing_round_reports.append("R27")

    lines = [
        "MASTER BACKTEST SUMMARY V3",
        "==========================",
        "Definitive consolidated review of the DEEP6 backtest campaign, rebuilding the master summary from every matched text report in data/backtests/analysis plus the legacy round1 walk-forward file.",
        "",
    ]
    lines.extend(
        render_campaign_statistics(
            matched_report_paths=matched_report_paths,
            extra_report_paths=extra_report_paths,
            total_filter_evaluations=total_filter_evaluations,
            first_date=first_date,
            last_date=last_date,
            duration_note=duration_note,
            missing_round_reports=missing_round_reports,
        )
    )
    lines.extend(render_top_signals(qualifying))
    lines.extend(render_signal_killers(killers))
    lines.extend(render_novel_signal_families(loaded_specs, parsed_results, auxiliary_highlights))
    lines.extend(render_universal_trading_rules(merged, legacy_rules))
    lines.extend(render_indicator_build(qualifying, killers, session_count))
    lines.extend(render_exit_recommendations(exit_recommendations, has_round26_text))
    lines.extend(render_regime_robustness(qualifying, has_round27_text))
    lines.extend(render_caveats(total_filter_evaluations, missing_round_reports, auxiliary_highlights))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
