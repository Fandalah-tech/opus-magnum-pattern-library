from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS, rotate_hex

from .purification_chain import METAL_ORDER, purification_profile
from .solver import validate_generated_solution


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _adjacent(first: tuple[int, int], second: tuple[int, int]) -> bool:
    delta = (second[0] - first[0], second[1] - first[1])
    return delta in set(DIRECTIONS)


def _bonded_atom_ids(world: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for bond in world.get("bonds", []) or []:
        first = str(bond.get("fromAtomId") or "")
        second = str(bond.get("toAtomId") or "")
        if first:
            result.add(first)
        if second:
            result.add(second)
    return result


def intermediate_pair_observations(
    replay: dict[str, Any],
    *,
    element: str,
) -> list[dict[str, Any]]:
    """Return trace frames where two free copies of one intermediate coexist."""

    observations: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for frame in replay.get("frames", []) or []:
        cycle = int(frame.get("cycle") or 0)
        world = frame.get("world") or {}
        bonded = _bonded_atom_ids(world)
        atoms = [
            atom for atom in world.get("atoms", []) or []
            if str(atom.get("element") or "") == str(element)
        ]
        atoms.sort(key=lambda atom: str(atom.get("id") or ""))
        for index, first in enumerate(atoms):
            for second in atoms[index + 1:]:
                first_id = str(first.get("id") or "")
                second_id = str(second.get("id") or "")
                first_position = _position(first.get("position"))
                second_position = _position(second.get("position"))
                key = (first_id, second_id, first_position, second_position)
                if key in seen:
                    continue
                seen.add(key)
                observations.append({
                    "cycle": cycle,
                    "element": str(element),
                    "firstAtomId": first_id,
                    "secondAtomId": second_id,
                    "firstPosition": list(first_position),
                    "secondPosition": list(second_position),
                    "firstHeld": bool(first.get("heldBy") or []),
                    "secondHeld": bool(second.get("heldBy") or []),
                    "firstBonded": first_id in bonded,
                    "secondBonded": second_id in bonded,
                    "alreadyAdjacent": _adjacent(first_position, second_position),
                })
    return sorted(
        observations,
        key=lambda item: (
            int(item.get("firstHeld") or item.get("secondHeld")),
            int(item.get("firstBonded") or item.get("secondBonded")),
            int(item.get("alreadyAdjacent")),
            int(item.get("cycle") or 0),
            tuple(item.get("firstPosition") or (0, 0)),
            tuple(item.get("secondPosition") or (0, 0)),
        ),
    )


def _rotation_moves(
    source: tuple[int, int],
    stationary: tuple[int, int],
) -> list[dict[str, Any]]:
    """Enumerate one arm1 rotation that makes source adjacent to stationary."""

    records: list[dict[str, Any]] = []
    for base_rotation, direction in enumerate(DIRECTIONS):
        base = (source[0] - direction[0], source[1] - direction[1])
        relative = (source[0] - base[0], source[1] - base[1])
        for instruction, steps in (("rotate_cw", -1), ("rotate_ccw", 1)):
            moved_relative = rotate_hex(relative, steps)
            destination = (base[0] + moved_relative[0], base[1] + moved_relative[1])
            if destination == stationary or not _adjacent(destination, stationary):
                continue
            records.append({
                "basePosition": [base[0], base[1]],
                "baseRotation": base_rotation,
                "instruction": instruction,
                "destination": [destination[0], destination[1]],
            })
    return records


def _purifier_poses(first: tuple[int, int], second: tuple[int, int]) -> list[dict[str, Any]]:
    poses: list[dict[str, Any]] = []
    for origin, other in ((first, second), (second, first)):
        delta = (other[0] - origin[0], other[1] - origin[1])
        rotation = next(
            (value for value in range(6) if rotate_hex((1, 0), value) == delta),
            None,
        )
        if rotation is None:
            continue
        output_delta = rotate_hex((0, 1), rotation)
        output = (origin[0] + output_delta[0], origin[1] + output_delta[1])
        poses.append({
            "origin": [origin[0], origin[1]],
            "rotation": rotation,
            "second": [other[0], other[1]],
            "output": [output[0], output[1]],
        })
    return poses


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


def add_intermediate_convergence_station(
    solution: dict[str, Any],
    *,
    observation: dict[str, Any],
    moving_atom: str,
    move: dict[str, Any],
    purifier_pose: dict[str, Any],
    grab_cycle: int,
) -> dict[str, Any]:
    """Add one arm and one purifier to converge two trace-produced atoms."""

    result = deepcopy(solution)
    existing = {str(part.get("id") or "") for part in result.get("parts", []) or []}
    serial = 0
    while f"convergence-arm-{serial}" in existing:
        serial += 1
    arm_id = f"convergence-arm-{serial}"
    purifier_id = f"convergence-purifier-{serial}"
    motion_cycle = int(grab_cycle) + 1
    drop_cycle = motion_cycle + 1
    result.setdefault("parts", []).append({
        "id": arm_id,
        "type": "arm1",
        "enabled": True,
        "position": [int(value) for value in move.get("basePosition", (0, 0))],
        "length": 1,
        "rotation": int(move.get("baseRotation") or 0) % 6,
        "which": 0,
        "armNumber": _next_arm_number(result),
        "program": [
            {"cycle": int(grab_cycle), "instruction": "grab"},
            {"cycle": motion_cycle, "instruction": str(move.get("instruction") or "rotate_cw")},
            {"cycle": drop_cycle, "instruction": "drop"},
        ],
    })
    result["parts"].append({
        "id": purifier_id,
        "type": "glyph-purification",
        "enabled": True,
        "position": [int(value) for value in purifier_pose.get("origin", (0, 0))],
        "length": 1,
        "rotation": int(purifier_pose.get("rotation") or 0) % 6,
        "which": 0,
        "armNumber": 0,
        "program": [],
    })
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/intermediate-convergence-v1"
    source.setdefault("intermediateConvergenceRepairs", []).append({
        "armPartId": arm_id,
        "purifierPartId": purifier_id,
        "element": observation.get("element"),
        "observationCycle": int(observation.get("cycle") or 0),
        "movingAtomId": str(moving_atom),
        "move": deepcopy(move),
        "purifierPose": deepcopy(purifier_pose),
        "grabCycle": int(grab_cycle),
        "motionCycle": motion_cycle,
        "dropCycle": drop_cycle,
        "targetSolutionBytesUsed": 0,
    })
    return result


def _rank(record: dict[str, Any]) -> tuple[Any, ...]:
    profile = record.get("purificationProfile") or {}
    validation = record.get("validation") or {}
    return (
        int(profile.get("countsByElement", {}).get("gold", 0)),
        int(profile.get("frontierIndex") if profile.get("frontierIndex") is not None else -1),
        int(profile.get("count") or 0),
        int(validation.get("totalDelivered") or 0),
        int(not bool(profile.get("terminatedWithError"))),
        int(profile.get("completedCycles") or 0),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        -int(record.get("grabDelay") or 0),
    )


def search_intermediate_convergence(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    element: str | None = None,
    max_cycles: int = 500,
    observation_limit: int = 80,
    result_limit: int = 20,
) -> dict[str, Any]:
    """Converge two produced intermediates with a synthesized one-step arm.

    The search consumes only the generated machine's own replay.  It identifies
    two simultaneously present, unheld and unbonded frontier atoms, enumerates
    one arm1 rotation that makes them adjacent, places the next purification
    glyph on that pair, and keeps only replay-proven chemistry advances.
    """

    horizon = max(1, int(max_cycles))
    baseline_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    target_element = str(element or baseline_profile.get("frontierElement") or "")
    if target_element not in METAL_ORDER[:-1]:
        return {
            "schemaVersion": "0.1.0",
            "kind": "trace-guided-intermediate-convergence-search",
            "summary": {
                "maxCycles": horizon,
                "element": target_element or None,
                "observationCount": 0,
                "searchedVariantCount": 0,
                "advancingVariantCount": 0,
                "returnedVariantCount": 0,
                "goldReached": bool(baseline_profile.get("goldReached")),
                "targetSolutionBytesUsed": 0,
            },
            "baselinePurificationProfile": baseline_profile,
            "observations": [],
            "variants": [],
        }

    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    observations = intermediate_pair_observations(replay, element=target_element)
    observations = observations[:max(0, int(observation_limit))]
    baseline_gold = int((baseline_profile.get("countsByElement") or {}).get("gold", 0))

    records: list[dict[str, Any]] = []
    searched = 0
    for observation in observations:
        if observation.get("firstHeld") or observation.get("secondHeld"):
            continue
        if observation.get("firstBonded") or observation.get("secondBonded"):
            continue
        cycle = int(observation.get("cycle") or 0)
        first_id = str(observation.get("firstAtomId") or "")
        second_id = str(observation.get("secondAtomId") or "")
        first_position = tuple(int(value) for value in observation.get("firstPosition") or (0, 0))
        second_position = tuple(int(value) for value in observation.get("secondPosition") or (0, 0))

        choices = (
            (first_id, first_position, second_position),
            (second_id, second_position, first_position),
        )
        for moving_id, moving_position, stationary_position in choices:
            for move in _rotation_moves(moving_position, stationary_position):
                destination = tuple(int(value) for value in move.get("destination") or (0, 0))
                for purifier_pose in _purifier_poses(stationary_position, destination):
                    # Try grabbing at the observed frame and one cycle later;
                    # replay decides whether the intermediate remains available.
                    for delay in (0, 1):
                        searched += 1
                        candidate = add_intermediate_convergence_station(
                            solution,
                            observation=observation,
                            moving_atom=moving_id,
                            move=move,
                            purifier_pose=purifier_pose,
                            grab_cycle=cycle + delay,
                        )
                        profile = purification_profile(puzzle, candidate, max_cycles=horizon)
                        gold = int((profile.get("countsByElement") or {}).get("gold", 0))
                        if gold <= baseline_gold:
                            continue
                        validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
                        records.append({
                            "observation": deepcopy(observation),
                            "movingAtomId": moving_id,
                            "move": deepcopy(move),
                            "purifierPose": deepcopy(purifier_pose),
                            "grabDelay": delay,
                            "purificationProfile": profile,
                            "validation": validation,
                            "solution": candidate,
                        })

    records.sort(key=_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-intermediate-convergence-search",
        "summary": {
            "maxCycles": horizon,
            "element": target_element,
            "observationCount": len(observations),
            "freePairObservationCount": sum(
                not item.get("firstHeld")
                and not item.get("secondHeld")
                and not item.get("firstBonded")
                and not item.get("secondBonded")
                for item in observations
            ),
            "searchedVariantCount": searched,
            "advancingVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "goldReached": bool(selected),
            "targetSolutionBytesUsed": 0,
        },
        "baselinePurificationProfile": baseline_profile,
        "observations": observations,
        "variants": selected,
    }


__all__ = [
    "add_intermediate_convergence_station",
    "intermediate_pair_observations",
    "search_intermediate_convergence",
]
