from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import rotate_hex

from .intermediate_convergence import intermediate_pair_observations
from .purification_chain import METAL_ORDER, purification_profile
from .solver import validate_generated_solution


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
        poses.append({
            "origin": [origin[0], origin[1]],
            "rotation": rotation,
            "second": [other[0], other[1]],
            "output": [origin[0] + output_delta[0], origin[1] + output_delta[1]],
        })
    return poses


def add_adjacent_pair_purifier(
    solution: dict[str, Any],
    *,
    observation: dict[str, Any],
    purifier_pose: dict[str, Any],
) -> dict[str, Any]:
    """Append a purifier on an already-adjacent replayed intermediate pair.

    Appending the glyph after existing reaction stations is intentional: if two
    lower-metal purification stations create the pair during one instantaneous
    glyph pass, the new purifier is evaluated later in the same solution-file
    order and may consume that pair in the same cycle.  No arm motion or target
    solution geometry is introduced.
    """

    result = deepcopy(solution)
    existing = {str(part.get("id") or "") for part in result.get("parts", []) or []}
    serial = 0
    while f"adjacent-purifier-{serial}" in existing:
        serial += 1
    part_id = f"adjacent-purifier-{serial}"
    result.setdefault("parts", []).append({
        "id": part_id,
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
    source["generator"] = "opus_solver/adjacent-intermediate-purification-v1"
    source.setdefault("adjacentIntermediatePurificationRepairs", []).append({
        "purifierPartId": part_id,
        "element": observation.get("element"),
        "observationCycle": int(observation.get("cycle") or 0),
        "firstAtomId": str(observation.get("firstAtomId") or ""),
        "secondAtomId": str(observation.get("secondAtomId") or ""),
        "firstPosition": list(observation.get("firstPosition") or []),
        "secondPosition": list(observation.get("secondPosition") or []),
        "purifierPose": deepcopy(purifier_pose),
        "targetSolutionBytesUsed": 0,
    })
    return result


def _rank(record: dict[str, Any]) -> tuple[Any, ...]:
    profile = record.get("purificationProfile") or {}
    validation = record.get("validation") or {}
    observation = record.get("observation") or {}
    return (
        int((profile.get("countsByElement") or {}).get("gold", 0)),
        int(profile.get("frontierIndex") if profile.get("frontierIndex") is not None else -1),
        int(profile.get("count") or 0),
        int(validation.get("totalDelivered") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        -int(observation.get("cycle") or 0),
    )


def search_adjacent_intermediate_purification(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    element: str | None = None,
    max_cycles: int = 1500,
    observation_limit: int = 120,
    result_limit: int = 24,
) -> dict[str, Any]:
    """Exploit an already-adjacent free pair without spending another motion cycle."""

    horizon = max(1, int(max_cycles))
    baseline_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    target_element = str(element or baseline_profile.get("frontierElement") or "")
    if target_element not in METAL_ORDER[:-1]:
        return {
            "schemaVersion": "0.1.0",
            "kind": "trace-guided-adjacent-intermediate-purification-search",
            "summary": {
                "maxCycles": horizon,
                "element": target_element or None,
                "observationCount": 0,
                "freeAdjacentObservationCount": 0,
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
    usable = [
        item for item in observations
        if bool(item.get("alreadyAdjacent"))
        and not bool(item.get("firstHeld"))
        and not bool(item.get("secondHeld"))
        and not bool(item.get("firstBonded"))
        and not bool(item.get("secondBonded"))
    ]
    baseline_gold = int((baseline_profile.get("countsByElement") or {}).get("gold", 0))
    baseline_count = int(baseline_profile.get("count") or 0)
    records: list[dict[str, Any]] = []
    searched = 0

    for observation in usable:
        first = tuple(int(value) for value in observation.get("firstPosition") or (0, 0))
        second = tuple(int(value) for value in observation.get("secondPosition") or (0, 0))
        for pose in _purifier_poses(first, second):
            searched += 1
            candidate = add_adjacent_pair_purifier(
                solution,
                observation=observation,
                purifier_pose=pose,
            )
            profile = purification_profile(puzzle, candidate, max_cycles=horizon)
            gold = int((profile.get("countsByElement") or {}).get("gold", 0))
            if gold <= baseline_gold and int(profile.get("count") or 0) <= baseline_count:
                continue
            validation = validate_generated_solution(puzzle, candidate, max_cycles=horizon)
            records.append({
                "observation": deepcopy(observation),
                "purifierPose": deepcopy(pose),
                "purificationProfile": profile,
                "validation": validation,
                "solution": candidate,
            })

    records.sort(key=_rank, reverse=True)
    selected = records[:max(0, int(result_limit))]
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-adjacent-intermediate-purification-search",
        "summary": {
            "maxCycles": horizon,
            "element": target_element,
            "observationCount": len(observations),
            "freeAdjacentObservationCount": len(usable),
            "searchedVariantCount": searched,
            "advancingVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "goldReached": any(
                int(((item.get("purificationProfile") or {}).get("countsByElement") or {}).get("gold", 0)) > baseline_gold
                for item in selected
            ),
            "targetSolutionBytesUsed": 0,
        },
        "baselinePurificationProfile": baseline_profile,
        "observations": observations,
        "variants": selected,
    }


__all__ = [
    "add_adjacent_pair_purifier",
    "search_adjacent_intermediate_purification",
]
