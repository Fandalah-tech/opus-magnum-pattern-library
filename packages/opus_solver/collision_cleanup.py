from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from packages.opus_engine.builder import DIRECTIONS

from .input_footprint_repair import replay_summary


_STATIONARY_COLLISION_RE = re.compile(
    r"Atom (?P<moving>\S+) collides with stationary atom (?P<stationary>\S+) at \((?P<q>-?\d+), (?P<r>-?\d+)\)"
)


def first_stationary_collision(summary: dict[str, Any]) -> dict[str, Any] | None:
    """Parse the first engine stationary-atom collision into a repair target."""

    error = summary.get("firstError") or {}
    message = str(error.get("message") or "")
    match = _STATIONARY_COLLISION_RE.search(message)
    if match is None:
        return None
    return {
        "cycle": int(error.get("cycle") or 0),
        "movingAtomId": match.group("moving"),
        "stationaryAtomId": match.group("stationary"),
        "position": [int(match.group("q")), int(match.group("r"))],
        "evidence": "engine-stationary-collision",
    }


def _frame_at_or_before(replay: dict[str, Any], cycle: int) -> dict[str, Any] | None:
    frames = [
        frame for frame in replay.get("frames", []) or []
        if int(frame.get("cycle") or 0) <= int(cycle)
    ]
    return max(frames, key=lambda frame: int(frame.get("cycle") or 0), default=None)


def collision_molecule(replay: dict[str, Any], collision: dict[str, Any]) -> dict[str, Any] | None:
    """Return the stationary molecule present immediately before the failed motion."""

    frame = _frame_at_or_before(replay, int(collision.get("cycle") or 0))
    if frame is None:
        return None
    world = frame.get("world") or {}
    atom_id = str(collision.get("stationaryAtomId") or "")
    atoms = {
        str(atom.get("id") or ""): atom
        for atom in world.get("atoms", []) or []
    }
    atom = atoms.get(atom_id)
    if atom is None:
        return None
    molecule = next(
        (
            item for item in world.get("molecules", []) or []
            if atom_id in {str(value) for value in item.get("atomIds", []) or []}
        ),
        None,
    )
    atom_ids = [str(value) for value in (molecule or {}).get("atomIds", []) or [atom_id]]
    return {
        "cycle": int(frame.get("cycle") or 0),
        "stationaryAtomId": atom_id,
        "stationaryPosition": list(atom.get("position") or collision.get("position") or (0, 0)),
        "atomIds": atom_ids,
        "atoms": [
            {
                "id": item_id,
                "element": str(atoms[item_id].get("element") or ""),
                "position": list(atoms[item_id].get("position") or (0, 0)),
                "heldBy": list(atoms[item_id].get("heldBy") or []),
            }
            for item_id in atom_ids
            if item_id in atoms
        ],
    }


def _next_arm_number(solution: dict[str, Any]) -> int:
    return 1 + max(
        (
            int(part.get("armNumber") or 0)
            for part in solution.get("parts", []) or []
            if str(part.get("type") or "").startswith("arm")
            or str(part.get("type") or "") in {"piston", "baron"}
        ),
        default=0,
    )


def add_cleanup_arm(
    solution: dict[str, Any],
    *,
    grab_position: tuple[int, int],
    base_direction_index: int,
    rotation_instruction: str,
    grab_cycle: int,
    motion_cycle: int,
) -> dict[str, Any]:
    """Add one arm that grabs a collision blocker and rotates it out of the path."""

    result = deepcopy(solution)
    direction_index = int(base_direction_index) % 6
    tip_direction = DIRECTIONS[direction_index]
    base = (grab_position[0] - tip_direction[0], grab_position[1] - tip_direction[1])
    existing_ids = {str(part.get("id") or "") for part in result.get("parts", []) or []}
    serial = 0
    while f"cleanup-arm-{serial}" in existing_ids:
        serial += 1
    part_id = f"cleanup-arm-{serial}"
    result.setdefault("parts", []).append({
        "id": part_id,
        "type": "arm1",
        "enabled": True,
        "position": [base[0], base[1]],
        "length": 1,
        "rotation": direction_index,
        "which": 0,
        "armNumber": _next_arm_number(result),
        "program": [
            {"cycle": int(grab_cycle), "instruction": "grab"},
            {"cycle": int(motion_cycle), "instruction": str(rotation_instruction)},
            {"cycle": int(motion_cycle) + 1, "instruction": "drop"},
        ],
    })
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/trace-guided-collision-cleanup-v1"
    source.setdefault("collisionCleanupRepairs", []).append({
        "partId": part_id,
        "grabPosition": [grab_position[0], grab_position[1]],
        "basePosition": [base[0], base[1]],
        "baseRotation": direction_index,
        "grabCycle": int(grab_cycle),
        "motionCycle": int(motion_cycle),
        "motionInstruction": str(rotation_instruction),
        "targetSolutionBytesUsed": 0,
    })
    return result


def _rank(record: dict[str, Any]) -> tuple[Any, ...]:
    summary = record.get("summary") or {}
    return (
        int(summary.get("productDeliveredCount") or 0),
        int(summary.get("purificationCount") or 0),
        int(not bool(summary.get("terminatedWithError"))),
        int(summary.get("completedCycles") or 0),
        int(summary.get("chemistryEventCount") or 0),
        int(summary.get("manipulationEventCount") or 0),
        -int(record.get("grabLead") or 0),
    )


def search_collision_cleanup_arms(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 256,
    grab_leads: tuple[int, ...] = (1, 2, 3, 4),
    result_limit: int = 12,
) -> dict[str, Any]:
    """Move the first stationary collision blocker with one synthesized cleanup arm."""

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
        for lead in sorted({max(1, int(value)) for value in grab_leads}):
            grab_cycle = max(0, error_cycle - lead)
            # The blocking molecule may itself move before the collision.  Only
            # a one-cycle lead is guaranteed to use the error-frame coordinate;
            # longer leads are nevertheless replay-validated as cheap timing alternatives.
            motion_cycle = error_cycle
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
                        "grabLead": lead,
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
        "grabLead": None,
        "baseDirectionIndex": None,
        "motionInstruction": None,
    }
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-stationary-collision-cleanup-search",
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
            "targetSolutionBytesUsed": 0,
        },
        "collision": collision,
        "collisionMolecule": molecule,
        "baseline": baseline,
        "variants": selected,
        "best": best,
    }


__all__ = [
    "add_cleanup_arm",
    "collision_molecule",
    "first_stationary_collision",
    "search_collision_cleanup_arms",
]
