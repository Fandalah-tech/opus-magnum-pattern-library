from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_METRIC_LINE = re.compile(
    r"(?P<cost>\d+)g/(?P<instructions>\d+)i@0\s+"
    r"(?P<cycles>\d+)c/(?P<area>\d+)a@V"
)
_PRODUCT_METRIC_LINE = re.compile(
    r"^product (?P<count>\d+) (?P<metric>[a-z][a-z0-9-]*):\s*(?P<value>-?\d+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def build_command(binary: str, puzzle_path: Path, solution_path: Path) -> list[str]:
    """Build the current omsim CLI invocation.

    omsim requires the puzzle to be supplied through --puzzle-file; remaining
    positional arguments are solution files.
    """
    return [binary, "--puzzle-file", str(puzzle_path), str(solution_path)]


def build_product_command(
    binary: str,
    puzzle_path: Path,
    solution_path: Path,
    *,
    product_count: int = 1,
    metric: str = "cycles",
) -> list[str]:
    """Build an omsim command that proves delivery of ``product_count`` products."""
    if product_count < 1:
        raise ValueError("product_count must be positive")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", metric, re.IGNORECASE):
        raise ValueError("metric must be an omsim metric name")
    return [
        binary,
        "--puzzle-file",
        str(puzzle_path),
        "--metric",
        f"product {product_count} {metric}",
        str(solution_path),
    ]


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


def parse_product_metric(
    output: str,
    *,
    product_count: int = 1,
    metric: str = "cycles",
) -> int | None:
    """Return the requested product metric only when omsim printed an exact match."""
    for match in _PRODUCT_METRIC_LINE.finditer(output):
        if (
            int(match.group("count")) == product_count
            and match.group("metric").lower() == metric.lower()
        ):
            return int(match.group("value"))
    return None


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


def classify_product_result(
    return_code: int,
    output: str,
    *,
    product_count: int = 1,
    metric: str = "cycles",
) -> dict[str, Any]:
    """Classify omsim's product metric as an explicit delivery proof.

    A regular cycle-limit result only proves that the machine did not collide.
    This contract is intentionally stricter: success requires both exit code 0
    and omsim's exact ``product N metric`` line.
    """
    normalized = output.strip()
    value = parse_product_metric(
        normalized,
        product_count=product_count,
        metric=metric,
    )
    if return_code == 0 and value is not None:
        return {
            "status": "product-complete",
            "valid": True,
            "productCount": product_count,
            "metric": metric,
            "value": value,
            "issues": [],
        }

    if return_code == 0:
        return {
            "status": "validator-error",
            "valid": None,
            "productCount": product_count,
            "metric": metric,
            "value": None,
            "issues": [{
                "severity": "error",
                "code": "OMSIM_PRODUCT_METRIC_MISSING",
                "message": normalized or "omsim returned no product metric",
            }],
        }

    failure = classify_result(return_code, normalized)
    return {
        **failure,
        "productCount": product_count,
        "metric": metric,
        "value": None,
    }
