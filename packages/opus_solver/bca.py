from __future__ import annotations

from copy import deepcopy
from typing import Any

BCA_OBJECTIVE = "bca"
BCA_PROXY_OBJECTIVE = "cycles"
BCA_MINIMUM_HEXAGON_METRIC = "minimum hexagon"
BCA_RESTRICTIONS_METRIC = "default restrictions"
BCA_OMSIM_METRICS = (
    "cost",
    "instructions",
    "cycles",
    "area",
    BCA_MINIMUM_HEXAGON_METRIC,
    BCA_RESTRICTIONS_METRIC,
)


def bca_key(metrics: dict[str, Any]) -> tuple[int, ...]:
    """Critelli BCA ordering: minimum hexagon > cycles > area.

    Cost and instructions are deterministic fallbacks only; they do not alter
    the event's three declared ranking dimensions.
    """

    fallback = 10**12
    minimum_hexagon = (
        int(metrics.get("minimumHexagon"))
        if isinstance(metrics.get("minimumHexagon"), int)
        else fallback
    )
    cycles = int(metrics.get("cycles")) if isinstance(metrics.get("cycles"), int) else fallback
    area = int(metrics.get("area")) if isinstance(metrics.get("area"), int) else fallback
    cost = int(metrics.get("cost")) if isinstance(metrics.get("cost"), int) else fallback
    instructions = (
        int(metrics.get("instructions"))
        if isinstance(metrics.get("instructions"), int)
        else fallback
    )
    return minimum_hexagon, cycles, area, cost, instructions


def bca_metrics_from_omsim(validation: dict[str, Any]) -> dict[str, int] | None:
    base = validation.get("metrics") or {}
    extras = validation.get("extraMetrics") or {}
    minimum_hexagon = extras.get(BCA_MINIMUM_HEXAGON_METRIC)
    restrictions = extras.get(BCA_RESTRICTIONS_METRIC)
    if not isinstance(minimum_hexagon, int):
        return None
    if restrictions != 0:
        return None
    required = ("cost", "cycles", "area", "instructions")
    if not all(isinstance(base.get(key), int) for key in required):
        return None
    result = {
        "minimumHexagon": int(minimum_hexagon),
        "cost": int(base["cost"]),
        "cycles": int(base["cycles"]),
        "area": int(base["area"]),
        "instructions": int(base["instructions"]),
    }
    if isinstance(validation.get("rate"), int):
        result["rate"] = int(validation["rate"])
    return result


def bca_proxy_validation(validation: dict[str, Any]) -> dict[str, Any]:
    """Map official BCA dimensions onto the existing cycle objective tuple.

    `objective_key("cycles")` sorts `(cycles, rate, cost, area, instructions)`.
    For one BCA scoring pass only, map that tuple to
    `(minimum hexagon, actual cycles, actual area, actual cost, instructions)`.
    The authoritative unmodified values remain attached as `bcaMetrics` and
    `authoritativeMetrics` and are restored in the final solver report.
    """

    result = deepcopy(validation)
    metrics = bca_metrics_from_omsim(validation)
    if not validation.get("valid") or metrics is None:
        result["valid"] = False
        result.setdefault("issues", []).append({
            "severity": "error",
            "code": "BCA_METRICS_UNAVAILABLE",
            "message": (
                "BCA requires OMSim metrics cost, instructions, cycles, area, "
                "minimum hexagon and default restrictions == 0"
            ),
        })
        return result

    result["authoritativeMetrics"] = deepcopy(validation.get("metrics") or {})
    result["bcaMetrics"] = metrics
    result["bcaObjectiveKey"] = list(bca_key(metrics))
    result["rankingProxy"] = {
        "objective": BCA_PROXY_OBJECTIVE,
        "mapping": {
            "cycles": "minimum hexagon",
            "rate": "cycles",
            "cost": "area",
            "area": "cost",
            "instructions": "instructions",
        },
    }
    result["metrics"] = {
        "cycles": metrics["minimumHexagon"],
        "cost": metrics["area"],
        "area": metrics["cost"],
        "instructions": metrics["instructions"],
    }
    result["rate"] = metrics["cycles"]
    return result


def normalize_bca_selection(validation: dict[str, Any]) -> dict[str, Any]:
    """Restore authoritative metric names after proxy-based portfolio ranking."""

    result = deepcopy(validation)
    oracle = result.get("oracleValidation") or {}
    metrics = oracle.get("bcaMetrics")
    if not isinstance(metrics, dict):
        raise ValueError("Selected BCA candidate does not carry authoritative bcaMetrics")

    result["optimizationObjective"] = BCA_OBJECTIVE
    result["optimizationMetricSource"] = "omsim-minimum-hexagon"
    result["bcaMetrics"] = deepcopy(metrics)
    result["objectiveKey"] = list(bca_key(metrics))
    result["proxyObjective"] = BCA_PROXY_OBJECTIVE
    result["proxyObjectiveKey"] = deepcopy(validation.get("objectiveKey"))
    result["oracleMetrics"] = {
        key: int(value)
        for key, value in metrics.items()
        if isinstance(value, int)
    }
    return result
