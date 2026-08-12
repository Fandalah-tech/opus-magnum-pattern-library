#!/usr/bin/env python3
"""Run omsim and emit an Opus Codex validation-result JSON document."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SUMMARY_RE = re.compile(
    r"^(?P<cost>\d+)g/(?P<instructions>\d+)i@0\s+"
    r"(?P<cycles>\d+)c/(?P<area>\d+)a@V(?:\s+.*)?$"
)
METRIC_RE = re.compile(r"^(cost|instructions|cycles|area):\s*(\d+)\s*$")
OUTPUT_INTERVALS_RE = re.compile(r"^output intervals:\s*(.*?)\s*(?:\[([^]]*)\])?\s*$")
CYCLE_RE = re.compile(r"\bon cycle (?P<cycle>\d+) at (?P<u>-?\d+) (?P<v>-?\d+)\b")


def parse_omsim_output(stdout: str, returncode: int) -> dict[str, Any]:
    text = stdout.strip()
    metrics = {"cost": None, "cycles": None, "area": None, "instructions": None}
    output_intervals = {"warmup": [], "steadyState": []}
    issues: list[dict[str, Any]] = []

    for line in text.splitlines():
        metric_match = METRIC_RE.match(line.strip())
        if metric_match:
            metrics[metric_match.group(1)] = int(metric_match.group(2))
        interval_match = OUTPUT_INTERVALS_RE.match(line.strip())
        if interval_match:
            output_intervals = {
                "warmup": [int(value) for value in re.findall(r"\d+", interval_match.group(1) or "")],
                "steadyState": [int(value) for value in re.findall(r"\d+", interval_match.group(2) or "")],
            }

    for line in reversed(text.splitlines()):
        match = SUMMARY_RE.match(line.strip())
        if match:
            metrics = {key: int(value) for key, value in match.groupdict().items()}
            break

    valid = returncode == 0 and all(value is not None for value in metrics.values())

    if not valid:
        message = text or f"omsim exited with status {returncode} without output"
        issue: dict[str, Any] = {
            "severity": "error",
            "code": "OMSIM_VALIDATION_FAILED",
            "message": message,
            "cycle": None,
            "partId": None,
            "details": {"returnCode": returncode},
        }
        cycle_match = CYCLE_RE.search(message)
        if cycle_match:
            issue["cycle"] = int(cycle_match.group("cycle"))
            issue["details"].update(
                {
                    "location": {
                        "u": int(cycle_match.group("u")),
                        "v": int(cycle_match.group("v")),
                    }
                }
            )
        issues.append(issue)

    return {
        "schemaVersion": "0.1.0",
        "validator": {"name": "omsim", "version": None, "commit": None},
        "valid": valid,
        "metrics": metrics,
        "rate": output_intervals["steadyState"][0] if output_intervals["steadyState"] else None,
        "outputIntervals": output_intervals,
        "issues": issues,
        "knownDivergence": False,
        "rawOutput": text or None,
    }


def run_omsim(
    binary: Path,
    puzzle: Path,
    solution: Path,
    timeout: int,
    *,
    output_intervals: bool = False,
) -> dict[str, Any]:
    command = [str(binary), "--puzzle-file", str(puzzle), str(solution)]
    if output_intervals:
        command = [
            str(binary),
            "--puzzle-file",
            str(puzzle),
            "--output-intervals",
            "--metric",
            "cost",
            "--metric",
            "instructions",
            "--metric",
            "cycles",
            "--metric",
            "area",
            str(solution),
        ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return parse_omsim_output(f"omsim binary not found: {binary}", 127)
    except subprocess.TimeoutExpired:
        return parse_omsim_output(f"omsim timed out after {timeout} seconds", 124)

    combined = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return parse_omsim_output(combined, completed.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("solution", type=Path)
    parser.add_argument(
        "--omsim", type=Path, default=Path("omsim"), help="path to omsim executable"
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-intervals", action="store_true")
    parser.add_argument("--output", type=Path, help="write JSON to this file instead of stdout")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_omsim(
        args.omsim,
        args.puzzle,
        args.solution,
        args.timeout,
        output_intervals=args.output_intervals,
    )
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
