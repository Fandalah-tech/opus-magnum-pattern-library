from __future__ import annotations

from collections import Counter
from typing import Any

PERIOD_OVERRIDE = "period_override"
REPEAT = "repeat"
RESET = "reset"


def _copy_instruction(item: dict[str, Any], cycle: int, *, generated_by: str | None = None) -> dict[str, Any]:
    copied = dict(item)
    copied["cycle"] = cycle
    if generated_by:
        copied["generatedBy"] = generated_by
        copied["sourceCycle"] = item.get("cycle")
    return copied


def _expand_repeat_macros(program: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand Opus Magnum repeat placeholders into scheduled instructions.

    A repeat placeholder copies the most recent instruction block. The block is
    the instructions since the previous repeat, or the previous repeated block
    when repeat placeholders are adjacent. Generated instructions begin at the
    repeat placeholder's cycle and preserve the source block's spacing.
    """
    ordered = sorted(program, key=lambda item: int(item.get("cycle", 0)))
    expanded: list[dict[str, Any]] = []
    current_block: list[dict[str, Any]] = []
    previous_block: list[dict[str, Any]] = []

    for item in ordered:
        instruction = item.get("instruction")
        cycle = int(item.get("cycle", 0))
        if instruction == PERIOD_OVERRIDE:
            continue
        if instruction == REPEAT:
            source = current_block or previous_block
            if not source:
                continue
            block_start = min(int(entry["cycle"]) for entry in source)
            for entry in source:
                generated_cycle = cycle + int(entry["cycle"]) - block_start
                expanded.append(_copy_instruction(entry, generated_cycle, generated_by=REPEAT))
            previous_block = [dict(entry) for entry in source]
            current_block = []
            continue

        expanded.append(dict(item))
        current_block.append(dict(item))

    return sorted(expanded, key=lambda item: int(item["cycle"]))


def _declared_global_period(programs: list[list[dict[str, Any]]]) -> tuple[int, str]:
    overrides = [
        int(item["cycle"]) + 1
        for program in programs
        for item in program
        if item.get("instruction") == PERIOD_OVERRIDE
    ]
    if overrides:
        return max(overrides), "period_override"

    expanded_ends = [
        int(item["cycle"]) + 1
        for program in programs
        for item in _expand_repeat_macros(program)
    ]
    return max(expanded_ends, default=1), "longest_tape"


def _expanded_actions(
    program: list[dict[str, Any]],
    period: int,
    horizon: int,
) -> dict[int, list[dict[str, Any]]]:
    explicit: dict[int, list[dict[str, Any]]] = {}
    for item in _expand_repeat_macros(program):
        if item.get("instruction") == PERIOD_OVERRIDE:
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
    """Build a macro-expanded, globally synchronized instruction timeline.

    Opus Magnum uses one global tape period: shorter arm programs are padded to
    the longest tape. Repeat placeholders generate physical instructions inside
    that tape; they are not loop boundaries by themselves.
    """
    arms = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    declared_cycles = solution.get("metrics", {}).get("cycles")
    programs = [sorted(arm.get("program", []), key=lambda item: item["cycle"]) for arm in arms]
    global_period, period_source = _declared_global_period(programs)

    default_horizon = max(int(declared_cycles or 0), global_period, 1)
    horizon = int(max_cycles) if max_cycles is not None else default_horizon
    horizon = max(1, horizon)

    cycles: list[dict[str, Any]] = []
    active_counts: Counter[int] = Counter()
    per_arm: list[dict[str, Any]] = []
    expanded_by_arm: dict[str, dict[int, list[dict[str, Any]]]] = {}

    for arm, program in zip(arms, programs):
        macro_expanded = _expand_repeat_macros(program)
        expanded = _expanded_actions(program, global_period, horizon)
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
            "period": global_period,
            "periodSource": period_source,
            "instructionCount": len(program),
            "expandedInstructionCount": len(macro_expanded),
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
        for arm in arms:
            for item in expanded_by_arm.get(arm["id"], {}).get(cycle, []):
                events.append({
                    "partId": arm["id"],
                    "type": arm["type"],
                    "armNumber": arm.get("armNumber"),
                    "instruction": item["instruction"],
                    "rawCode": item.get("rawCode"),
                    "tapeCycle": cycle % global_period,
                    "generatedBy": item.get("generatedBy"),
                    "sourceCycle": item.get("sourceCycle"),
                })
        cycles.append({"cycle": cycle, "activeArms": active_counts[cycle], "events": events})

    distribution = Counter(active_counts[cycle] for cycle in range(horizon))
    peak = max(active_counts.values(), default=0)
    active_cycle_count = sum(1 for cycle in range(horizon) if active_counts[cycle] > 0)

    return {
        "schemaVersion": "0.3.0",
        "analysisType": "macro-expanded-global-program-timeline",
        "limitations": [
            "Repeat placeholders are expanded; reset placeholders are still represented as reset events.",
            "No atom positions, collisions, grabs, drops or glyph effects are physically simulated.",
            "An instruction is counted as scheduled even if physical execution would later fail or be blocked.",
        ],
        "summary": {
            "horizon": horizon,
            "declaredCycles": declared_cycles,
            "globalPeriod": global_period,
            "periodSource": period_source,
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
