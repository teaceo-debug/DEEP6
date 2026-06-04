#!/usr/bin/env python3
"""Fix router: CS#### error → fix strategy dispatch + surgical file edits."""

import argparse
import difflib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
skill_dir = os.path.dirname(script_dir)
sys.path.insert(0, skill_dir)

from lib.diagnostics import CompileError, FixResult  # noqa: E402


LOCKED_FIX_CODES = {
    "CS0103",
    "CS0246",
    "CS1061",
    "CS0019",
    "CS0101",
    "CS0535",
    "BRACE_MISMATCH",
    "MISSING_ATTRIBUTE",
}


TYPE_NAMESPACE_MAP = {
    "Indicator": ["NinjaTrader.NinjaScript.Indicators"],
    "Strategy": ["NinjaTrader.NinjaScript.Strategies"],
    "AddOnBase": ["NinjaTrader.NinjaScript.AddOns"],
    "DrawingTool": ["NinjaTrader.NinjaScript.DrawingTools"],
    "MarketAnalyzerColumn": ["NinjaTrader.NinjaScript.MarketAnalyzerColumns"],
    "Brush": ["System.Windows.Media", "SharpDX.Direct2D1"],
    "SolidColorBrush": ["System.Windows.Media"],
    "Color": ["System.Windows.Media"],
    "RenderTarget": ["SharpDX.Direct2D1"],
    "Factory": ["SharpDX.Direct2D1"],
    "Color4": ["SharpDX"],
    "RectangleF": ["SharpDX"],
    "Vector2": ["SharpDX"],
    "TextFormat": ["SharpDX.DirectWrite"],
    "TextLayout": ["SharpDX.DirectWrite"],
    "Series": ["NinjaTrader.NinjaScript"],
    "ISeries": ["NinjaTrader.NinjaScript"],
    "NinjaScriptBase": ["NinjaTrader.NinjaScript"],
    "Instrument": ["NinjaTrader.Data"],
    "MarketPosition": ["NinjaTrader.NinjaScript.Strategies"],
    "Order": ["NinjaTrader.Cbi"],
    "Account": ["NinjaTrader.Cbi"],
    "ChartControl": ["NinjaTrader.Gui.Chart"],
    "ChartPanel": ["NinjaTrader.Gui.Chart"],
    "DEEP6Footprint": ["NinjaTrader.NinjaScript.Indicators.DEEP6"],
    "DataBridgeIndicator": ["NinjaTrader.NinjaScript.Indicators.DEEP6"],
    "CaptureHarness": ["NinjaTrader.NinjaScript.Indicators.DEEP6"],
    "DEEP6GexLevels": ["NinjaTrader.NinjaScript.Indicators.DEEP6"],
    "DEEP6Strategy": ["NinjaTrader.NinjaScript.Strategies.DEEP6"],
    "Browsable": ["System.ComponentModel"],
    "XmlIgnore": ["System.Xml.Serialization"],
}


COMMON_USINGS = [
    "NinjaTrader.NinjaScript",
    "NinjaTrader.NinjaScript.Indicators",
    "NinjaTrader.NinjaScript.Strategies",
    "NinjaTrader.NinjaScript.Indicators.DEEP6",
    "NinjaTrader.NinjaScript.Strategies.DEEP6",
    "NinjaTrader.Gui",
    "NinjaTrader.Gui.Chart",
    "NinjaTrader.Data",
    "NinjaTrader.Cbi",
    "System.Linq",
    "System.Windows.Media",
    "System.ComponentModel",
    "System.Xml.Serialization",
    "SharpDX",
    "SharpDX.Direct2D1",
    "SharpDX.DirectWrite",
]


LINQ_EXTENSION_NAMES = {
    "Where",
    "Select",
    "Any",
    "All",
    "First",
    "FirstOrDefault",
    "Last",
    "LastOrDefault",
    "Single",
    "SingleOrDefault",
    "Count",
    "OrderBy",
    "OrderByDescending",
    "ThenBy",
    "ThenByDescending",
    "ToList",
    "ToArray",
    "Sum",
    "Min",
    "Max",
    "Average",
}


def extract_quoted_symbol(message: str) -> str | None:
    match = re.search(r"'([^']+)'", message)
    return match.group(1) if match else None


def normalize_type_name(symbol: str) -> str:
    return re.sub(r"<.*>", "", symbol).strip()


def using_exists(lines: list[str], namespace: str) -> bool:
    using_line = f"using {namespace};"
    return any(line.strip() == using_line for line in lines)


def insert_using(lines: list[str], namespace: str) -> str | None:
    using_line = f"using {namespace};"
    if using_exists(lines, namespace):
        return None

    insert_at = 0
    last_using = -1
    namespace_idx = None

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("using "):
            last_using = idx
            continue
        if namespace_idx is None and (stripped.startswith("namespace ") or stripped.startswith("public ") or stripped.startswith("internal ") or stripped.startswith("class ")):
            namespace_idx = idx
            break
        if stripped and not stripped.startswith("//"):
            if namespace_idx is None:
                namespace_idx = idx
                break

    if last_using >= 0:
        insert_at = last_using + 1
    elif namespace_idx is not None:
        insert_at = namespace_idx

    lines.insert(insert_at, using_line + "\n")
    return using_line


def infer_namespace_for_type(type_name: str, lines: list[str]) -> str | None:
    candidates = TYPE_NAMESPACE_MAP.get(type_name)
    if candidates:
        if len(candidates) == 1:
            return candidates[0]
        joined = "".join(lines)
        if type_name == "Brush":
            if any(token in joined for token in ("OnRender(", "RenderTarget", "Direct2D1", "SharpDX")):
                return "SharpDX.Direct2D1"
            if any(token in joined for token in ("SolidColorBrush", "Colors.", "Brushes.")):
                return "System.Windows.Media"
        return None

    lowered_type = type_name.lower()
    for namespace in COMMON_USINGS:
        if lowered_type in namespace.lower():
            return namespace
    return None


def build_fix_result(error: CompileError, original_lines: list[str], updated_lines: list[str], fix_applied: str) -> FixResult | None:
    if original_lines == updated_lines:
        return None

    diff = "\n".join(
        difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile=error.file,
            tofile=error.file,
            lineterm="",
        )
    )
    return FixResult(
        error=error,
        fix_applied=fix_applied,
        diff=diff,
        success=True,
        rollback_needed=False,
    )


def find_line_index(lines: list[str], target_line: str, start: int = 0) -> int | None:
    for idx in range(max(0, start), len(lines)):
        if lines[idx] == target_line:
            return idx
    for idx, line in enumerate(lines):
        if line == target_line:
            return idx
    return None


def fix_cs0246(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    original_lines = list(lines)
    symbol = extract_quoted_symbol(error.message)
    if not symbol:
        return None

    type_name = normalize_type_name(symbol)
    namespace = infer_namespace_for_type(type_name, lines)
    if not namespace:
        return None

    added_using = insert_using(lines, namespace)
    if not added_using:
        return None

    return build_fix_result(error, original_lines, lines, f"Added '{added_using}'")


def fix_cs0103(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    original_lines = list(lines)
    symbol = extract_quoted_symbol(error.message)
    if not symbol:
        return None

    if symbol in LINQ_EXTENSION_NAMES:
        added_using = insert_using(lines, "System.Linq")
        if added_using:
            return build_fix_result(error, original_lines, lines, f"Added '{added_using}' for extension method resolution")
        return None

    type_name = normalize_type_name(symbol)
    namespace = infer_namespace_for_type(type_name, lines)
    if namespace:
        added_using = insert_using(lines, namespace)
        if added_using:
            return build_fix_result(error, original_lines, lines, f"Added '{added_using}' as CS0103 fallback")

    return None


def fix_cs0019(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    return None


def fix_cs0101(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    return None


def fix_cs0535(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    return None


def fix_brace_mismatch(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    original_lines = list(lines)
    open_count = sum(line.count("{") for line in lines)
    close_count = sum(line.count("}") for line in lines)

    if open_count <= close_count:
        return None

    if lines and lines[-1].endswith("\n"):
        lines.append("}\n")
    else:
        lines.append("\n}\n")

    return build_fix_result(
        error,
        original_lines,
        lines,
        f"Added closing brace (open={open_count}, close={close_count})",
    )


def fix_cs1061(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    return None


def fix_missing_attribute(error: CompileError, lines: list[str], file_path: Path) -> FixResult | None:
    original_lines = list(lines)
    error_line_idx = max(0, error.line - 1)
    if error_line_idx >= len(lines):
        return None

    target_line = lines[error_line_idx]
    if "Series<" not in target_line and "ISeries<" not in target_line:
        return None

    previous_lines = [line.strip() for line in lines[max(0, error_line_idx - 3) : error_line_idx]]
    attrs_to_add = []
    if "[Browsable(false)]" not in previous_lines:
        attrs_to_add.append("[Browsable(false)]")
    if "[XmlIgnore]" not in previous_lines:
        attrs_to_add.append("[XmlIgnore]")

    if not attrs_to_add:
        return None

    added_usings = []
    for namespace in ("System.ComponentModel", "System.Xml.Serialization"):
        added_using = insert_using(lines, namespace)
        if added_using:
            added_usings.append(added_using)

    indent = target_line[: len(target_line) - len(target_line.lstrip())]
    insertion = [f"{indent}{attr}\n" for attr in attrs_to_add]
    current_line_index = find_line_index(lines, target_line, start=error_line_idx)
    if current_line_index is None:
        return None
    lines[current_line_index:current_line_index] = insertion

    applied_bits = []
    if added_usings:
        applied_bits.append("added usings: " + ", ".join(added_usings))
    applied_bits.append("added attributes: " + ", ".join(attrs_to_add))
    return build_fix_result(error, original_lines, lines, "; ".join(applied_bits))


FIX_HANDLERS = {
    "CS0246": fix_cs0246,
    "CS0103": fix_cs0103,
    "CS1061": fix_cs1061,
    "CS0019": fix_cs0019,
    "CS0101": fix_cs0101,
    "CS0535": fix_cs0535,
    "BRACE_MISMATCH": fix_brace_mismatch,
    "MISSING_ATTRIBUTE": fix_missing_attribute,
}


def load_error_entries(errors_path: Path) -> list[dict]:
    payload = json.loads(errors_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        entries = payload.get("errors", [])
    elif isinstance(payload, list):
        entries = payload
    else:
        raise ValueError("Unsupported error JSON payload")

    if not isinstance(entries, list):
        raise ValueError("Error JSON must contain a list of errors")
    return entries


def compile_error_from_entry(entry: dict) -> CompileError:
    return CompileError(
        code=entry.get("code", ""),
        message=entry.get("message", ""),
        file=entry.get("file", ""),
        line=int(entry.get("line", 0) or 0),
        col=int(entry.get("col", 0) or 0),
        severity=entry.get("severity", "error"),
    )


def resolve_source_path(error: CompileError, source_dir: Path) -> Path:
    raw_path = Path(error.file)
    if raw_path.is_absolute():
        return raw_path
    return source_dir / raw_path


def apply_fix(error: CompileError, source_dir: Path, dry_run: bool) -> dict:
    if error.code not in LOCKED_FIX_CODES:
        return {
            "status": "UNFIXABLE",
            "reason": f"Unsupported error code: {error.code}",
            "error": error_to_dict(error),
        }

    handler = FIX_HANDLERS.get(error.code)
    if handler is None:
        return {
            "status": "UNFIXABLE",
            "reason": f"No handler registered for {error.code}",
            "error": error_to_dict(error),
        }

    file_path = resolve_source_path(error, source_dir)
    if not file_path.exists():
        return {
            "status": "NEEDS_HUMAN",
            "reason": f"Source file not found: {file_path}",
            "error": error_to_dict(error),
        }

    original_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
    mutable_lines = list(original_lines)
    fix_result = handler(error, mutable_lines, file_path)
    if fix_result is None or not fix_result.success:
        return {
            "status": "NEEDS_HUMAN",
            "reason": f"No safe surgical fix for {error.code}",
            "error": error_to_dict(error),
        }

    if not dry_run:
        file_path.write_text("".join(mutable_lines), encoding="utf-8")

    return {
        "status": "FIX_APPLIED",
        "file": str(file_path),
        "error": error_to_dict(error),
        "fix_applied": fix_result.fix_applied,
        "diff": fix_result.diff,
        "dry_run": dry_run,
    }


def process_errors(entries: list[dict], source_dir: Path, dry_run: bool) -> dict:
    summary = {
        "fixes_applied": 0,
        "fixes_failed": 0,
        "unfixable": [],
        "needs_human": [],
        "diffs": [],
    }

    for entry in entries:
        error = compile_error_from_entry(entry)
        result = apply_fix(error, source_dir, dry_run)
        status = result["status"]

        if status == "FIX_APPLIED":
            summary["fixes_applied"] += 1
            summary["diffs"].append(
                {
                    "file": result["file"],
                    "code": error.code,
                    "fix_applied": result["fix_applied"],
                    "diff": result["diff"],
                    "dry_run": result["dry_run"],
                }
            )
        elif status == "UNFIXABLE":
            summary["fixes_failed"] += 1
            summary["unfixable"].append(result)
        else:
            summary["fixes_failed"] += 1
            summary["needs_human"].append(result)

    return summary


def error_to_dict(error: CompileError) -> dict:
    return {
        "code": error.code,
        "message": error.message,
        "file": error.file,
        "line": error.line,
        "col": error.col,
        "severity": error.severity,
    }


def run_self_test() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        source_file = temp_root / "TestIndicator.cs"
        source_file.write_text(
            "using System;\n"
            "namespace NinjaTrader.NinjaScript.Indicators.DEEP6\n"
            "{\n"
            "    public class TestIndicator : Indicator\n"
            "    {\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        sample_errors = [
            {
                "code": "CS0246",
                "message": "The type or namespace name 'Indicator' could not be found (are you missing a using directive or an assembly reference?)",
                "file": source_file.name,
                "line": 4,
                "col": 34,
                "severity": "error",
            }
        ]

        result = process_errors(sample_errors, temp_root, dry_run=True)
        result["test"] = {
            "source_file": str(source_file),
            "sample_error_code": "CS0246",
        }
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route enriched NT8 compile errors to surgical fixes")
    parser.add_argument("--errors", help="Path to enriched error JSON from parse_errors.py")
    parser.add_argument("--source-dir", default=".", help="Base directory for relative source file paths")
    parser.add_argument("--dry-run", action="store_true", help="Show fixes without writing files")
    parser.add_argument("--test", action="store_true", help="Run built-in CS0246 self-test")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.test:
        print(json.dumps(run_self_test(), indent=2))
        return 0

    if not args.errors:
        raise SystemExit("--errors is required unless --test is used")

    errors_path = Path(args.errors)
    source_dir = Path(args.source_dir).resolve()
    entries = load_error_entries(errors_path)
    result = process_errors(entries, source_dir, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
