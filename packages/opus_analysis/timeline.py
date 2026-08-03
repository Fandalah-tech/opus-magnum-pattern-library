from __future__ import annotations

from collections import Counter
from typing import Any

CONTROL_INSTRUCTIONS = {"period_override", "repeat"}


def _arm_period(program: list[dict[str, Any]]) -> tuple[int, str]:
    if not program:
        return 0, "empty"
    overrides = [item["cycle"] + 1 for item in program if item.get("instruction") == "period_override"]
    if overrides:
        return max(overrides), "period_override"
    repeats = [item["cycle"] + 1 for item in program if item.get("instruction") == "repeat"]
    if repeats:
        return max(repeats), "repeat"
    return max(item["cycle"] for item in program) + 1, "last_instruction"


def build_program_timeline(solution: dict[str, Any], *, max_cycles: int | None = None) -> dict[str, Any]:
    """Build a static instruction timeline from a parsed solution.

    This is program analysis, not physical simulation. It expands explicit arm
    instructions over a finite horizon and reports utilization and parallelism.
    """
    arms = [part for part in solution.get("parts", []) if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}]
    declared_cycles = solution.get("metrics", {}).get("cycles")
    inferred_periods = []
    arm_rows = []

    for arm in arms:
        program = sorted(arm.get("program", []), key=lambda item: item["cycle"])
        period, period_source = _arm_period(program)
        inferred_periods.append(period)
        arm_rows.append((arm, program, period, period_source))

    default_horizon = max([declared_cycles or 0, *inferred_periods, 1])
    horizon = min(max_cycles, default_horizon) if max_cycles else default_horizon
    horizon = max(1, horizon)

    cycles: list[dict[str, Any]] = []
    active_counts = Counter()
    per_arm = []

    for arm, program, period, period_source in arm_rows:
        explicit = {item["cycle"]: item for item in program if item.get("instruction") not in CONTROL_INSTRUCTIONS}
        active = [cycle for cycle in range(horizon) if cycle in explicit]
        histogram = Counter(explicit[cycle]["instruction"] for cycle in active)
        per_arm.append({
            "partId": arm["id"],
            "type": arm["type"],
            "armNumber": arm.get("armNumber"),
            "period": period,
            "periodSource": period_source,
            "instructionCount": len(program),
            "actionCount": len(active),
            "idleCycles": horizon - len(active),
            "utilization": round(len(active) / horizon, 4),
            "firstActionCycle": min(active) if active else None,
            "lastActionCycle": max(active) if active else None,
            "histogram": dict(sorted(histogram.items())),
        })
        for cycle in active:
            active_counts[cycle] += 1

    for cycle in range(horizon):
        events = []
        for arm, program, period, period_source in arm_rows:
            for item in program:
                if item["cycle"] == cycle:
                    events.append({
                        "partId": arm["id"],
                        "type": arm["type"],
                        "instruction": item["instruction"],
                        "rawCode": item.get("rawCode"),
                    })
        cycles.append({"cycle": cycle, "activeArms": active_counts[cycle], "events": events})

    distribution = Counter(active_counts[cycle] for cycle in range(horizon))
    peak = max(active_counts.values(), default=0)
    active_cycle_count = sum(1 for cycle in range(horizon) if active_counts[cycle] > 0)

    return {
        "schemaVersion": "0.1.0",
        "analysisType": "static-program-timeline",
        "limitations": [
            "No atom positions or collisions are simulated.",
            "Wait cycles are inferred from absent explicit instructions.",
            "Program periods are inferred from override/repeat markers or the last instruction.",
        ],
        "summary": {
            "horizon": horizon,
            "declaredCycles": declared_cycles,
            "armCount": len(arms),
            "activeCycleCount": active_cycle_count,
            "globalIdleCycles": horizon - active_cycle_count,
            "peakParallelArms": peak,
            "averageParallelArms": round(sum(active_counts.values()) / horizon, 4),
            "parallelismDistribution": {str(key): value for key, value in sorted(distribution.items())},
        },
        "arms": per_arm,
        "cycles": cycles,
    }
