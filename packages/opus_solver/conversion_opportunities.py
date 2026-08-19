from __future__ import annotations

from collections import Counter
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS, rotate_hex


METAL_ORDER = ("lead", "tin", "iron", "copper", "silver", "gold")
PURIFIABLE_METALS = set(METAL_ORDER[:-1])


def _hex_distance(first: tuple[int, int], second: tuple[int, int]) -> int:
    dq = first[0] - second[0]
    dr = first[1] - second[1]
    return max(abs(dq), abs(dr), abs(dq + dr))


def _add(first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
    return first[0] + second[0], first[1] + second[1]


def conversion_opportunities_from_replay(replay: dict[str, Any]) -> dict[str, Any]:
    """Measure how close a replay comes to a valid purification input state.

    The metric intentionally stops before placing or activating a glyph. It
    rewards mechanical states that make two equal purifiable metals free
    (unheld and unbonded), then close, then adjacent with at least one empty
    triangular purification output cell. This gives blind search a useful
    gradient before an ``atom-purified`` event exists.
    """

    free_equal_observations = 0
    adjacent_free_observations = 0
    ready_pose_observations = 0
    frame_ready_counts: Counter[int] = Counter()
    element_ready_counts: Counter[str] = Counter()
    minimum_distance: int | None = None
    nearest_samples: list[dict[str, Any]] = []
    ready_samples: list[dict[str, Any]] = []

    for frame in replay.get("frames", []):
        cycle = int(frame.get("cycle") or 0)
        world = frame.get("world") or {}
        atoms = list(world.get("atoms", []))
        by_position = {
            tuple(int(value) for value in (atom.get("position") or (0, 0))): atom
            for atom in atoms
        }
        bonded_ids = {
            str(bond.get(key) or "")
            for bond in world.get("bonds", [])
            for key in ("fromAtomId", "toAtomId")
            if bond.get(key)
        }
        free_by_element: dict[str, list[dict[str, Any]]] = {}
        for atom in atoms:
            element = str(atom.get("element") or "")
            atom_id = str(atom.get("id") or "")
            if (
                element not in PURIFIABLE_METALS
                or atom_id in bonded_ids
                or atom.get("heldBy")
            ):
                continue
            free_by_element.setdefault(element, []).append(atom)

        for element, free_atoms in sorted(free_by_element.items()):
            for left_index, first in enumerate(free_atoms):
                first_position = tuple(int(value) for value in (first.get("position") or (0, 0)))
                for second in free_atoms[left_index + 1:]:
                    second_position = tuple(int(value) for value in (second.get("position") or (0, 0)))
                    distance = _hex_distance(first_position, second_position)
                    free_equal_observations += 1
                    if minimum_distance is None or distance < minimum_distance:
                        minimum_distance = distance
                        nearest_samples = []
                    if distance == minimum_distance and len(nearest_samples) < 12:
                        nearest_samples.append({
                            "cycle": cycle,
                            "element": element,
                            "distance": distance,
                            "atomIds": sorted((str(first.get("id") or ""), str(second.get("id") or ""))),
                            "positions": [list(first_position), list(second_position)],
                        })
                    if distance != 1:
                        continue

                    adjacent_free_observations += 1
                    ready_poses = []
                    for origin, target in ((first_position, second_position), (second_position, first_position)):
                        direction = (target[0] - origin[0], target[1] - origin[1])
                        try:
                            rotation = DIRECTIONS.index(direction)
                        except ValueError:
                            continue
                        output_position = _add(origin, rotate_hex((0, 1), rotation))
                        if output_position in by_position:
                            continue
                        ready_poses.append({
                            "position": list(origin),
                            "rotation": rotation,
                            "outputPosition": list(output_position),
                        })
                    if not ready_poses:
                        continue

                    ready_pose_observations += len(ready_poses)
                    frame_ready_counts[cycle] += len(ready_poses)
                    element_ready_counts[element] += len(ready_poses)
                    if len(ready_samples) < 20:
                        ready_samples.append({
                            "cycle": cycle,
                            "element": element,
                            "atomIds": sorted((str(first.get("id") or ""), str(second.get("id") or ""))),
                            "positions": [list(first_position), list(second_position)],
                            "poses": ready_poses,
                        })

    frames_with_ready = len(frame_ready_counts)
    return {
        "schemaVersion": "0.1.0",
        "kind": "purification-opportunity-gradient",
        "freeEqualPairObservationCount": free_equal_observations,
        "adjacentFreeEqualPairObservationCount": adjacent_free_observations,
        "readyPurificationPoseObservationCount": ready_pose_observations,
        "framesWithReadyPurificationPose": frames_with_ready,
        "maxReadyPurificationPosesInFrame": max(frame_ready_counts.values(), default=0),
        "minFreeEqualPairDistance": minimum_distance,
        "readyPoseCountsByElement": dict(sorted(element_ready_counts.items())),
        "nearestFreeEqualPairSamples": nearest_samples,
        "readyPurificationSamples": ready_samples,
    }


def replay_conversion_opportunities(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int,
) -> dict[str, Any]:
    """Replay one candidate and return the target-free conversion gradient."""

    timeline = build_program_timeline(solution, max_cycles=max(1, int(max_cycles)))
    replay = Simulator.from_models(puzzle, solution).run_timeline(timeline)
    result = conversion_opportunities_from_replay(replay)
    result["requestedCycles"] = max(1, int(max_cycles))
    result["completedCycles"] = int((replay.get("summary") or {}).get("completedCycles") or 0)
    result["terminatedWithError"] = bool((replay.get("summary") or {}).get("terminatedWithError"))
    return result


__all__ = [
    "conversion_opportunities_from_replay",
    "replay_conversion_opportunities",
]
