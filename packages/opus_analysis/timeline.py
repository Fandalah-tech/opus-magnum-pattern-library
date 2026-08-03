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


def _expanded_actions(
    program: list[dict[str, Any]],
    period: int,
    horizon: int,
) -> dict[int, list[dict[str, Any]]]:
    """Expand a repeating arm tape over a finite analysis horizon.

    Opus Magnum arm programs loop. Control markers define or document the tape
    period but are not physical actions, so they are excluded from activity.
    Multiple instructions on the same tape position are preserved.
    """
    explicit: dict[int, list[dict[str, Any]]] = {}
    for item in program:
        if item.get("instruction") in CONTROL_INSTRUCTIONS:
            continue
        explicit.setdefault(int(item["cycle"]), []).append(item)

    if not explicit or period <= 0:
        return {}

    expanded: dict[int, list[dict[str, Any]]] = {}
    for cycle in range(horizon):
        tape_cycle = cycle % period
        if tape_cycle in explicit:
            expanded[cycle] = explicit[tape_cycle]
    return expanded


def build_program_timeline(solution: dict[str, Any], *, max_cycles: int | None = None) -> dict[str, Any]:
    """Build a repeating static instruction timeline from a parsed solution.

    This is program analysis, not physical simulation. It expands each arm tape
    over the declared solution-cycle horizon and reports utilization and
    parallelism. It does not infer atom motion, collisions, grabs that fail, or
    production completion.
    """
    arms = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    declared_cycles = solution.get("metrics", {}).get("cycles")
    inferred_periods: list[int] = []
    arm_rows: list[tuple[dict[str, Any], list[dict[str, Any]], int, str]] = []

    for arm in arms:
        program = sorted(arm.get("program", []), key=lambda item: item["cycle"])
        period, period_source = _arm_period(program)
        inferred_periods.append(period)
        arm_rows.append((arm, program, period, period_source))

    default_horizon = max([declared_cycles or 0, *inferred_periods, 1])
    horizon = min(max_cycles, default_horizon) if max_cycles else default_horizon
    horizon = max(1, horizon)

    cycles: list[dict[str, Any]] = []
    active_counts: Counter[int] = Counter()
    per_arm: list[dict[str, Any]] = []
    expanded_by_arm: dict[str, dict[int, list[dict[str, Any]]]] = {}

    for arm, program, period, period_source in arm_rows:
        expanded = _expanded_actions(program, period, horizon)
        expanded_by_arm[arm["id"]] = expanded
        active = sorted(expanded)
        histogram = Counter(
            item["instruction"]
            for cycle in active
            for item in expanded[cycle]
        )
        per_arm.append({
            "partId": arm["id"],
            "type": arm["type"],
            "armNumber": arm.get("armNumber"),
            "period": period,
            "periodSource": period_source,
            "instructionCount": len(program),
            "actionCount": sum(len(expanded[cycle]) for cycle in active),
            "activeCycleCount": len(active),
            "idleCycles": horizon - len(active),
            "utilization": round(len(active) / horizon, 4),
            "firstActionCycle": min(active) if active else None,
            "lastActionCycle": max(active) if active else None,
            "histogram": dict(sorted(histogram.items())),
        })
        for cycle in active:
            active_counts[cycle] += 1

    for cycle in range(horizon):
        events: list[dict[str, Any]] = []
        for arm, _program, period, _period_source in arm_rows:
            for item in expanded_by_arm.get(arm["id"], {}).get(cycle, []):
                events.append({
                    "partId": arm["id"],
                    "type": arm["type"],
                    "armNumber": arm.get("armNumber"),
                    "instruction": item["instruction"],
                    "rawCode": item.get("rawCode"),
                    "tapeCycle": cycle % period if period else None,
                })
        cycles.append({"cycle": cycle, "activeArms": active_counts[cycle], "events": events})

    distribution = Counter(active_counts[cycle] for cycle in range(horizon))
    peak = max(active_counts.values(), default=0)
    active_cycle_count = sum(1 for cycle in range(horizon) if active_counts[cycle] > 0)

    return {
        "schemaVersion": "0.2.0",
        "analysisType": "repeating-static-program-timeline",
        "limitations": [
            "No atom positions, collisions, grabs, drops or glyph effects are simulated.",
            "Arm tapes are expanded by their inferred period across the declared solution-cycle horizon.",
            "An instruction is counted as scheduled even if physical execution would later fail or be blocked.",
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
