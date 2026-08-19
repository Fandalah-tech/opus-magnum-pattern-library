from __future__ import annotations

from copy import deepcopy
from typing import Any

from .collision_cleanup import (
    add_cleanup_arm,
    collision_molecule,
    first_stationary_collision,
)
from .input_footprint_repair import replay_summary


def _rank(record: dict[str, Any]) -> tuple[Any, ...]:
    summary = record.get("summary") or {}
    return (
        int(summary.get("productDeliveredCount") or 0),
        int(summary.get("purificationCount") or 0),
        int(not bool(summary.get("terminatedWithError"))),
        int(summary.get("completedCycles") or 0),
        int(summary.get("chemistryEventCount") or 0),
        int(summary.get("manipulationEventCount") or 0),
        -int(record.get("motionLead") or 0),
        -int(record.get("grabLead") or 0),
    )


def search_phase_aware_cleanup_arms(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 400,
    motion_leads: tuple[int, ...] = (0, 1, 2, 3, 4),
    grab_leads: tuple[int, ...] = (1, 2, 3, 4),
    result_limit: int = 16,
) -> dict[str, Any]:
    """Search both cleanup-arm geometry and its phase relative to a collision.

    Moving the blocker one or more cycles before the observed collision changes
    the cleanup arm's repeating phase relative to the inherited transport tape.
    This can preserve the first repair while avoiding a later repeat collision,
    and every timing choice is verified by full local replay.
    """

    horizon = max(1, int(max_cycles))
    baseline_full = replay_summary(puzzle, solution, max_cycles=horizon)
    replay = baseline_full.pop("replay")
    baseline = baseline_full
    collision = first_stationary_collision(baseline)
    molecule = collision_molecule(replay, collision) if collision is not None else None
    records: list[dict[str, Any]] = []

    if collision is not None and molecule is not None:
        position = tuple(int(value) for value in molecule.get("stationaryPosition") or collision.get("position") or (0, 0))
        error_cycle = int(collision.get("cycle") or 0)
        for motion_lead in sorted({max(0, int(value)) for value in motion_leads}):
            motion_cycle = max(1, error_cycle - motion_lead)
            for grab_lead in sorted({max(1, int(value)) for value in grab_leads}):
                grab_cycle = max(0, motion_cycle - grab_lead)
                for direction_index in range(6):
                    for instruction in ("rotate_cw", "rotate_ccw"):
                        candidate = add_cleanup_arm(
                            solution,
                            grab_position=position,
                            base_direction_index=direction_index,
                            rotation_instruction=instruction,
                            grab_cycle=grab_cycle,
                            motion_cycle=motion_cycle,
                        )
                        replayed = replay_summary(puzzle, candidate, max_cycles=horizon)
                        replayed.pop("replay", None)
                        if int(replayed.get("purificationCount") or 0) < int(baseline.get("purificationCount") or 0):
                            continue
                        records.append({
                            "motionLead": motion_lead,
                            "grabLead": grab_lead,
                            "baseDirectionIndex": direction_index,
                            "motionInstruction": instruction,
                            "summary": replayed,
                            "solution": candidate,
                        })

    records.sort(key=_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    best = selected[0] if selected else {
        "summary": baseline,
        "solution": deepcopy(solution),
        "motionLead": None,
        "grabLead": None,
        "baseDirectionIndex": None,
        "motionInstruction": None,
    }
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-phase-aware-collision-cleanup-search",
        "summary": {
            "maxCycles": horizon,
            "baselineCompletedCycles": int(baseline.get("completedCycles") or 0),
            "baselinePurificationCount": int(baseline.get("purificationCount") or 0),
            "collisionDetected": collision is not None,
            "searchedVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "bestCompletedCycles": int((best.get("summary") or {}).get("completedCycles") or 0),
            "bestPurificationCount": int((best.get("summary") or {}).get("purificationCount") or 0),
            "bestTerminatedWithError": bool((best.get("summary") or {}).get("terminatedWithError")),
            "bestMotionLead": best.get("motionLead"),
            "targetSolutionBytesUsed": 0,
        },
        "collision": collision,
        "collisionMolecule": molecule,
        "baseline": baseline,
        "variants": selected,
        "best": best,
    }


__all__ = ["search_phase_aware_cleanup_arms"]
