#!/usr/bin/env python3
"""Parse and enrich NT8 compile errors with fix recipe metadata."""

import sys
import os
import json
import argparse

# Add lib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
skill_dir = os.path.dirname(script_dir)
sys.path.insert(0, skill_dir)

from lib.diagnostics import CompileError

# Known warning codes (should NOT enter fix loop)
WARNING_CODES = {"CS0168", "CS0219", "CS0414", "CS0649", "CS0169", "CS0067"}

# Known fixable error codes (have fix recipes in fixes/)
FIXABLE_CODES = {
    "CS0103",
    "CS0246",
    "CS1061",
    "CS0019",
    "CS0101",
    "CS0535",
    "BRACE_MISMATCH",
    "MISSING_ATTRIBUTE",
}


def parse_errors(error_json: list[dict]) -> dict:
    """Parse error list, separate warnings, enrich with fix metadata."""
    errors = []
    warnings = []

    for item in error_json:
        code = item.get("code", "")
        severity = "warning" if code in WARNING_CODES else "error"

        ce = CompileError(
            code=code,
            message=item.get("message", ""),
            file=item.get("file", ""),
            line=item.get("line", 0),
            col=item.get("col", 0),
            severity=severity,
        )

        if severity == "warning":
            warnings.append(ce)
        else:
            errors.append(ce)

    # Enrich errors with fix recipe info
    enriched_errors = []
    fixable_count = 0
    unfixable_count = 0

    for err in errors:
        fix_recipe_path = os.path.join(skill_dir, "fixes", f"{err.code}.md")
        has_recipe = os.path.exists(fix_recipe_path)

        enriched = {
            "code": err.code,
            "message": err.message,
            "file": err.file,
            "line": err.line,
            "col": err.col,
            "severity": err.severity,
            "fixable": has_recipe and err.code in FIXABLE_CODES,
            "fix_recipe": f"fixes/{err.code}.md" if has_recipe else None,
        }
        enriched_errors.append(enriched)

        if enriched["fixable"]:
            fixable_count += 1
        else:
            unfixable_count += 1

    # Sort: fixable first, then unfixable
    enriched_errors.sort(key=lambda e: (not e["fixable"], e["code"]))

    # Detect cascade groups: multiple errors referencing same type/namespace
    cascade_groups = detect_cascades(enriched_errors)

    return {
        "errors": enriched_errors,
        "warnings": [
            {
                "code": w.code,
                "message": w.message,
                "file": w.file,
                "line": w.line,
                "col": w.col,
            }
            for w in warnings
        ],
        "fixable_count": fixable_count,
        "unfixable_count": unfixable_count,
        "cascade_groups": cascade_groups,
    }


def detect_cascades(errors: list[dict]) -> list[dict]:
    """Group errors that likely share a root cause."""
    # Group by: same file + same error code
    groups = {}
    for err in errors:
        key = f"{err['file']}:{err['code']}"
        if key not in groups:
            groups[key] = {
                "file": err["file"],
                "code": err["code"],
                "count": 0,
                "lines": [],
            }
        groups[key]["count"] += 1
        groups[key]["lines"].append(err["line"])

    # Only return groups with 2+ errors (actual cascades)
    return [g for g in groups.values() if g["count"] >= 2]


def main():
    parser = argparse.ArgumentParser(description="Parse and enrich NT8 compile errors")
    parser.add_argument("--file", help="JSON file path (default: stdin)")
    parser.add_argument("--test", action="store_true", help="Run with sample data")
    args = parser.parse_args()

    if args.test:
        sample = [
            {
                "file": "test.cs",
                "message": "type not found",
                "code": "CS0246",
                "line": 10,
                "col": 5,
            },
            {
                "file": "test.cs",
                "message": "type not found again",
                "code": "CS0246",
                "line": 20,
                "col": 5,
            },
            {
                "file": "b.cs",
                "message": "unused var",
                "code": "CS0168",
                "line": 5,
                "col": 1,
            },
        ]
        result = parse_errors(sample)
    elif args.file:
        with open(args.file) as f:
            data = json.load(f)
        result = parse_errors(data)
    else:
        data = json.load(sys.stdin)
        result = parse_errors(data)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
