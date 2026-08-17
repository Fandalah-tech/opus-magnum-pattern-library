#!/usr/bin/env python3
"""Run omsim and emit an Opus Codex validation-result JSON document."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from packages.opus_validator import classify_product_result

SUMMARY_RE = re.compile(
    r"^(?P<cost>\d+)g/(?P<instructions>\d+)i@0\s+"
    r"(?P<cycles>\d+)c/(?P<area>\d+)a@V(?:\s+.*)?$"
)
METRIC_RE = re.compile(r"^(cost|instructions|cycles|area):\s*(\d+)\s*$")
OUTPUT_INTERVALS_RE = re.compile(r"^output intervals:\s*(.*?)\s*(?:\[([^]]*)\])?\s*$")
CYCLE_RE = re.compile(r"\bon cycle (?P<cycle>\d+) at (?P<u>-?\d+) (?P<v>-?\d+)\b")
NUMBER_RE = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")
BASE_METRICS = ("cost", "instructions", "cycles", "area")


def _issue(text: str, returncode: int) -> dict[str, Any]:
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
    return issue


def _output_intervals(text: str) -> dict[str, list[int]]:
    result = {"warmup": [], "steadyState": []}
    for line in text.splitlines():
        interval_match = OUTPUT_INTERVALS_RE.match(line.strip())
        if not interval_match:
            continue
        result = {
            "warmup": [int(value) for value in re.findall(r"\d+", interval_match.group(1) or "")],
            "steadyState": [int(value) for value in re.findall(r"\d+", interval_match.group(2) or "")],
        }
    return result


def parse_omsim_output(stdout: str, returncode: int) -> dict[str, Any]:
    text = stdout.strip()
    metrics = {"cost": None, "cycles": None, "area": None, "instructions": None}
    output_intervals = _output_intervals(text)
    issues: list[dict[str, Any]] = []

    for line in text.splitlines():
        metric_match = METRIC_RE.match(line.strip())
        if metric_match:
            metrics[metric_match.group(1)] = int(metric_match.group(2))

    for line in reversed(text.splitlines()):
        match = SUMMARY_RE.match(line.strip())
        if match:
            metrics = {key: int(value) for key, value in match.groupdict().items()}
            break

    valid = returncode == 0 and all(value is not None for value in metrics.values())
    if not valid:
        issues.append(_issue(text, returncode))

    return {
        "schemaVersion": "0.1.0",
        "validator": {"name": "omsim", "version": None, "commit": None},
        "valid": valid,
        "metrics": metrics,
        "extraMetrics": {},
        "rate": output_intervals["steadyState"][0] if output_intervals["steadyState"] else None,
        "outputIntervals": output_intervals,
        "issues": issues,
        "knownDivergence": False,
        "rawOutput": text or None,
    }


def parse_omsim_metrics_output(
    stdout: str,
    returncode: int,
    requested_metrics: Iterable[str],
) -> dict[str, Any]:
    """Parse arbitrary `omsim --metric` values while preserving base schema fields."""

    text = stdout.strip()
    requested = tuple(str(value) for value in requested_metrics)
    values: dict[str, int | float | None] = {name: None for name in requested}
    output_intervals = _output_intervals(text)

    for line in text.splitlines():
        stripped = line.strip()
        for name in requested:
            prefix = f"{name}:"
            if not stripped.startswith(prefix):
                continue
            raw_value = stripped[len(prefix):].strip()
            if not NUMBER_RE.match(raw_value):
                continue
            numeric = float(raw_value)
            values[name] = int(numeric) if numeric.is_integer() else numeric
            break

    base = {
        key: values.get(key) if isinstance(values.get(key), int) else None
        for key in BASE_METRICS
    }
    extras = {
        name: value
        for name, value in values.items()
        if name not in BASE_METRICS
    }
    missing = [name for name, value in values.items() if value is None]
    valid = returncode == 0 and not missing
    issues: list[dict[str, Any]] = []
    if not valid:
        issue = _issue(text, returncode)
        if missing:
            issue["details"]["missingMetrics"] = missing
        issues.append(issue)

    return {
        "schemaVersion": "0.2.0",
        "validator": {"name": "omsim", "version": None, "commit": None},
        "valid": valid,
        "metrics": base,
        "extraMetrics": extras,
        "requestedMetrics": list(requested),
        "rate": output_intervals["steadyState"][0] if output_intervals["steadyState"] else None,
        "outputIntervals": output_intervals,
        "issues": issues,
        "knownDivergence": False,
        "rawOutput": text or None,
    }


def _run(command: list[str], timeout: int) -> tuple[str, int]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return f"omsim binary not found: {command[0]}", 127
    except subprocess.TimeoutExpired:
        return f"omsim timed out after {timeout} seconds", 124

    combined = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return combined, completed.returncode


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
    combined, returncode = _run(command, timeout)
    return parse_omsim_output(combined, returncode)


def run_omsim_metrics(
    binary: Path,
    puzzle: Path,
    solution: Path,
    timeout: int,
    *,
    metrics: Iterable[str],
    output_intervals: bool = False,
) -> dict[str, Any]:
    """Evaluate arbitrary libverify metric names through OMSim's public CLI."""

    requested = tuple(dict.fromkeys(str(metric) for metric in metrics))
    if not requested:
        raise ValueError("At least one OMSim metric must be requested")
    command = [str(binary), "--puzzle-file", str(puzzle)]
    if output_intervals:
        command.append("--output-intervals")
    for metric in requested:
        command.extend(("--metric", metric))
    command.append(str(solution))
    combined, returncode = _run(command, timeout)
    return parse_omsim_metrics_output(combined, returncode, requested)


def run_omsim_product(
    binary: Path,
    puzzle: Path,
    solution: Path,
    timeout: int,
    *,
    product_count: int = 1,
    metric: str = "cycles",
) -> dict[str, Any]:
    """Ask omsim to stop only after it has accepted an exact product."""
    command = [
        str(binary),
        "--puzzle-file",
        str(puzzle),
        "--metric",
        f"product {product_count} {metric}",
        str(solution),
    ]
    combined, returncode = _run(command, timeout)
    return {
        **classify_product_result(
            returncode,
            combined,
            product_count=product_count,
            metric=metric,
        ),
        "rawOutput": combined or None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("solution", type=Path)
    parser.add_argument(
        "--omsim", type=Path, default=Path("omsim"), help="path to omsim executable"
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-intervals", action="store_true")
    parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Evaluate this OMSim/libverify metric; may be supplied more than once.",
    )
    parser.add_argument("--output", type=Path, help="write JSON to this file instead of stdout")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.metric:
        result = run_omsim_metrics(
            args.omsim,
            args.puzzle,
            args.solution,
            args.timeout,
            metrics=args.metric,
            output_intervals=args.output_intervals,
        )
    else:
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
