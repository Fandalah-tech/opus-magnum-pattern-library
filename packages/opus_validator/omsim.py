from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_METRIC_LINE = re.compile(
    r"(?P<cost>\d+)g/(?P<instructions>\d+)i@0\s+"
    r"(?P<cycles>\d+)c/(?P<area>\d+)a@V"
)


def build_command(binary: str, puzzle_path: Path, solution_path: Path) -> list[str]:
    """Build the current omsim CLI invocation.

    omsim requires the puzzle to be supplied through --puzzle-file; remaining
    positional arguments are solution files.
    """
    return [binary, "--puzzle-file", str(puzzle_path), str(solution_path)]


def parse_metrics(output: str) -> dict[str, int | None]:
    match = _METRIC_LINE.search(output)
    if not match:
        return {"cost": None, "cycles": None, "area": None, "instructions": None}
    values = {key: int(value) for key, value in match.groupdict().items()}
    return {
        "cost": values["cost"],
        "cycles": values["cycles"],
        "area": values["area"],
        "instructions": values["instructions"],
    }


def classify_result(return_code: int, output: str) -> dict[str, Any]:
    normalized = output.strip()
    metrics = parse_metrics(normalized)

    if return_code == 0:
        return {
            "status": "valid",
            "valid": True,
            "metrics": metrics,
            "issues": [],
        }

    lowered = normalized.lower()
    invocation_markers = (
        "usage: omsim",
        "must specify either -p|--puzzle-file",
        "cannot specify both -p|--puzzle-file",
        "too many metrics",
    )
    if any(marker in lowered for marker in invocation_markers):
        return {
            "status": "validator-error",
            "valid": None,
            "metrics": metrics,
            "issues": [{
                "severity": "error",
                "code": "OMSIM_INVOCATION_FAILED",
                "message": normalized or f"omsim exited with code {return_code}",
            }],
        }

    return {
        "status": "invalid",
        "valid": False,
        "metrics": metrics,
        "issues": [{
            "severity": "error",
            "code": "OMSIM_VALIDATION_FAILED",
            "message": normalized or f"omsim exited with code {return_code}",
        }],
    }
