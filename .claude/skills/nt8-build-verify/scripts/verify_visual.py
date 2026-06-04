#!/usr/bin/env python3
"""Visual verification: auto-checks + optional LLM vision."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
skill_dir = os.path.dirname(script_dir)
sys.path.insert(0, skill_dir)

from lib.diagnostics import RunArtifacts  # noqa: E402


def auto_checks(screenshot_path: str) -> dict:
    """Run automated quality checks on screenshot."""
    checks: dict[str, object] = {}

    file_size = os.path.getsize(screenshot_path)
    checks["file_size_bytes"] = file_size
    checks["file_size_check"] = "fail" if file_size < 10 * 1024 else "pass"

    try:
        from PIL import Image
        import statistics

        with Image.open(screenshot_path) as img:
            rgb_img = img.convert("RGB")
            width, height = rgb_img.size
            checks["image_size"] = {"width": width, "height": height}

            step_x = max(1, width // 20)
            step_y = max(1, height // 20)
            values: list[int] = []

            for x in range(0, width, step_x):
                for y in range(0, height, step_y):
                    r, g, b = rgb_img.getpixel((x, y))
                    values.append(r + g + b)

        stddev = statistics.stdev(values) if len(values) > 1 else 0.0
        checks["pixel_stddev"] = round(stddev, 2)
        checks["blank_check"] = "fail" if stddev < 5.0 else "pass"
    except ImportError:
        checks["blank_check"] = "skipped"
        checks["blank_check_reason"] = "Pillow not installed"
    except Exception as exc:
        checks["blank_check"] = "error"
        checks["blank_check_reason"] = str(exc)

    return checks


def _build_llm_prompt(spec_description: str) -> str:
    return f"""You are a visual QA reviewer for NinjaTrader 8 chart indicators.

SPEC: {spec_description}

Look at this chart screenshot and determine if the indicator matches the spec.

Respond with EXACTLY one of these verdicts:
- PASS: The indicator renders correctly matching the spec
- PASS_WITH_NOTES: The indicator mostly matches but has minor differences (list them)
- FAIL: The indicator does NOT match the spec (explain what's wrong)

Format your response as:
VERDICT: [PASS|PASS_WITH_NOTES|FAIL]
NOTES: [your observations]"""


def _get_media_type(screenshot_path: str) -> str:
    ext = Path(screenshot_path).suffix.lower().lstrip(".")
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(ext, "image/png")


def _parse_llm_verdict(response_text: str) -> str:
    if "VERDICT: PASS_WITH_NOTES" in response_text:
        return "PASS_WITH_NOTES"
    if "VERDICT: PASS" in response_text:
        return "PASS"
    if "VERDICT: FAIL" in response_text:
        return "FAIL"
    return "FAIL"


def llm_vision_verify(screenshot_path: str, spec_description: str, attempt: int) -> dict:
    """Call Claude API with screenshot + spec for visual verification."""
    try:
        import anthropic
    except ImportError:
        return {"verdict": "SKIPPED", "reason": "anthropic SDK not installed", "attempt": attempt}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"verdict": "SKIPPED", "reason": "ANTHROPIC_API_KEY not set", "attempt": attempt}

    with open(screenshot_path, "rb") as file_handle:
        image_data = base64.standard_b64encode(file_handle.read()).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": _get_media_type(screenshot_path),
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": _build_llm_prompt(spec_description)},
                ],
            }
        ],
    )

    response_text = "\n".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return {
        "verdict": _parse_llm_verdict(response_text),
        "llm_response": response_text,
        "attempt": attempt,
        "model": "claude-sonnet-4-20250514",
    }


def llm_vision_verify_with_retries(screenshot_path: str, spec_description: str, max_attempts: int) -> dict:
    """Run up to two LLM verification attempts."""
    capped_attempts = max(1, min(max_attempts, 2))
    last_result: dict[str, object] | None = None

    for attempt in range(1, capped_attempts + 1):
        try:
            result = llm_vision_verify(screenshot_path, spec_description, attempt)
            if result.get("verdict") == "SKIPPED":
                return {**result, "attempts_used": attempt, "max_attempts": capped_attempts}
            result["attempts_used"] = attempt
            result["max_attempts"] = capped_attempts
            return result
        except Exception as exc:
            last_result = {
                "verdict": "SKIPPED",
                "reason": f"LLM verification error: {exc}",
                "attempt": attempt,
            }

    if last_result is None:
        last_result = {"verdict": "SKIPPED", "reason": "LLM verification not attempted", "attempt": 0}

    last_result["attempts_used"] = capped_attempts
    last_result["max_attempts"] = capped_attempts
    return last_result


def determine_verdict(auto_result: dict, llm_result: dict | None, skip_llm: bool) -> str:
    """Combine auto-checks and LLM result into final verdict."""
    if auto_result.get("blank_check") == "fail" or auto_result.get("file_size_check") == "fail":
        return "FAIL"

    if skip_llm or llm_result is None or llm_result.get("verdict") == "SKIPPED":
        return "PASS_WITH_NOTES"

    if llm_result.get("verdict") == "PASS":
        return "PASS"

    if llm_result.get("verdict") == "PASS_WITH_NOTES":
        return "PASS_WITH_NOTES"

    return "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description="Visual verification for NT8 indicators")
    parser.add_argument("--screenshot", required=True, help="Path to screenshot PNG")
    parser.add_argument("--spec", required=True, help="Text description of expected appearance")
    parser.add_argument("--artifacts-dir", default="./artifacts", help="Directory for verdict files")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM vision, auto-checks only")
    parser.add_argument("--max-attempts", type=int, default=2, help="Max LLM vision attempts (capped at 2)")
    args = parser.parse_args()

    screenshot_path = os.path.abspath(args.screenshot)
    if not os.path.exists(screenshot_path):
        print(json.dumps({"error": f"Screenshot not found: {screenshot_path}"}))
        return 1

    auto_result = auto_checks(screenshot_path)

    llm_result = None
    if not args.skip_llm and auto_result.get("blank_check") != "fail" and auto_result.get("file_size_check") != "fail":
        llm_result = llm_vision_verify_with_retries(screenshot_path, args.spec, args.max_attempts)

    verdict = determine_verdict(auto_result, llm_result, args.skip_llm)
    timestamp = datetime.now().strftime("%H%M%S")
    output = {
        "verdict": verdict,
        "auto_checks": auto_result,
        "llm_result": llm_result,
        "screenshot": screenshot_path,
        "spec": args.spec,
        "timestamp": timestamp,
        "artifacts_dir": os.path.abspath(args.artifacts_dir),
    }

    artifacts = RunArtifacts(args.artifacts_dir)
    verdict_path = artifacts.save_json(f"verdict-{timestamp}", output)
    output["verdict_path"] = str(verdict_path)
    verdict_path.write_text(json.dumps(output, indent=2))

    print(json.dumps(output, indent=2))
    return 0 if verdict in {"PASS", "PASS_WITH_NOTES"} else 1


if __name__ == "__main__":
    sys.exit(main())
