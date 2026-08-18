from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_analysis.canonical import rotate_hex

from .candidate_solution import serialize_candidate_roundtrip
from .chemistry_transplant import arm_grab_sites, mechanical_fingerprint
from .solver import validate_generated_solution


def _hex_distance(first: tuple[int, int], second: tuple[int, int]) -> int:
    dq = first[0] - second[0]
    dr = first[1] - second[1]
    return max(abs(dq), abs(dr), abs(dq + dr))


def _candidate_input_placements(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    input_part: dict[str, Any],
    *,
    max_grab_cycles: int,
    placement_limit: int,
) -> list[dict[str, Any]]:
    reagent_index = int(input_part.get("which") or 0)
    reagents = list(puzzle.get("reagents") or [])
    if not 0 <= reagent_index < len(reagents):
        return []
    atoms = list(reagents[reagent_index].get("atoms") or [])
    if not atoms:
        return []

    original_position = tuple(int(value) for value in (input_part.get("position") or (0, 0)))
    original_rotation = int(input_part.get("rotation") or 0) % 6
    placements: dict[tuple[tuple[int, int], int], dict[str, Any]] = {}
    for grab in arm_grab_sites(solution, max_cycles=max_grab_cycles):
        tip = tuple(int(value) for value in (grab.get("position") or (0, 0)))
        for rotation in range(6):
            for atom_index, atom in enumerate(atoms):
                local = tuple(int(value) for value in (atom.get("position") or (0, 0)))
                offset = rotate_hex(local, rotation)
                origin = (tip[0] - offset[0], tip[1] - offset[1])
                signature = (origin, rotation)
                if signature == (original_position, original_rotation):
                    continue
                distance = _hex_distance(origin, original_position)
                item = placements.get(signature)
                evidence = {
                    "grabCycle": int(grab.get("cycle") or 0),
                    "armId": str(grab.get("partId") or ""),
                    "branchIndex": int(grab.get("branchIndex") or 0),
                    "grabPosition": list(tip),
                    "anchoredAtomIndex": atom_index,
                    "anchoredAtomElement": str(atom.get("element") or ""),
                }
                if item is None:
                    placements[signature] = {
                        "position": list(origin),
                        "rotation": rotation,
                        "translationDistance": distance,
                        "reagentIndex": reagent_index,
                        "evidence": [evidence],
                    }
                elif len(item["evidence"]) < 4:
                    item["evidence"].append(evidence)

    ranked = sorted(
        placements.values(),
        key=lambda item: (
            int(item["translationDistance"]),
            min(int(e["grabCycle"]) for e in item["evidence"]),
            tuple(item["position"]),
            int(item["rotation"]),
        ),
    )
    limit = max(0, int(placement_limit))
    if limit <= 0 or len(ranked) <= limit:
        return ranked

    # Preserve both conservative nearby placements and a spread across the
    # mechanism's later grab sites so long tracks are not reduced to the reset
    # neighborhood. The second half is sampled deterministically by rank.
    near_count = max(1, limit // 2)
    selected = list(ranked[:near_count])
    remaining = ranked[near_count:]
    slots = limit - len(selected)
    if slots > 0 and remaining:
        if slots >= len(remaining):
            selected.extend(remaining)
        else:
            for index in range(slots):
                sample_index = round(index * (len(remaining) - 1) / max(1, slots - 1))
                selected.append(remaining[sample_index])
    deduped = []
    seen = set()
    for item in selected:
        signature = (tuple(item["position"]), int(item["rotation"]))
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    return deduped[:limit]


def _rank(validation: dict[str, Any], *, distance: int) -> tuple[Any, ...]:
    counts = validation.get("eventCounts") or {}
    target_transform_count = sum(
        int(counts.get(kind) or 0)
        for kind in (
            "atom-purified",
            "atom-projected",
            "atom-duplicated",
            "atom-calcified",
            "atoms-animated",
            "atoms-unified",
            "atom-divided",
        )
    )
    return (
        int(bool(validation.get("complete"))),
        int(validation.get("totalDelivered") or 0),
        target_transform_count,
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        int(validation.get("requiredChemistryEventCount") or 0),
        int(validation.get("chemistryEventCount") or 0),
        int(validation.get("manipulationEventCount") or 0),
        -int(distance),
    )


def search_input_feed_lanes(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_grab_cycles: int = 256,
    validation_cycles: int = 320,
    placement_limit_per_input: int = 72,
    result_limit: int = 20,
) -> dict[str, Any]:
    """Move one input glyph onto alternative learned grab lanes and replay it.

    This keeps the entire arm/track program frozen. Candidate input poses are
    derived only from the target reagent's local atom coordinates and grab-tip
    cells observed from the learned mechanism, which makes the repair useful for
    molecules whose footprint differs from the donor feed.
    """

    inputs = [
        part for part in solution.get("parts", [])
        if str(part.get("type") or "") == "input"
    ]
    before_mechanics = mechanical_fingerprint(solution)
    variants: list[dict[str, Any]] = []
    placement_counts: dict[str, int] = {}

    for input_part in inputs:
        input_id = str(input_part.get("id") or "")
        placements = _candidate_input_placements(
            puzzle,
            solution,
            input_part,
            max_grab_cycles=max_grab_cycles,
            placement_limit=placement_limit_per_input,
        )
        placement_counts[input_id] = len(placements)
        original_position = list(input_part.get("position") or (0, 0))
        original_rotation = int(input_part.get("rotation") or 0) % 6
        for placement in placements:
            candidate = deepcopy(solution)
            target_input = next(
                part for part in candidate.get("parts", [])
                if str(part.get("id") or "") == input_id
            )
            target_input["position"] = list(placement["position"])
            target_input["rotation"] = int(placement["rotation"])
            if mechanical_fingerprint(candidate) != before_mechanics:
                raise AssertionError("Feed lane repair changed arm/track mechanics")
            try:
                roundtrip = serialize_candidate_roundtrip(candidate)
                validation = validate_generated_solution(
                    puzzle,
                    roundtrip["parsed"],
                    max_cycles=max(1, int(validation_cycles)),
                )
                record = {
                    "inputId": input_id,
                    "reagentIndex": int(input_part.get("which") or 0),
                    "originalPosition": original_position,
                    "originalRotation": original_rotation,
                    "position": list(placement["position"]),
                    "rotation": int(placement["rotation"]),
                    "translationDistance": int(placement["translationDistance"]),
                    "grabEvidence": deepcopy(placement["evidence"]),
                    "serialization": roundtrip["diagnostics"],
                    "validation": validation,
                    "solution": candidate,
                    "mechanicsPreserved": True,
                }
                record["rank"] = _rank(
                    validation,
                    distance=int(placement["translationDistance"]),
                )
            except Exception as error:
                record = {
                    "inputId": input_id,
                    "position": list(placement["position"]),
                    "rotation": int(placement["rotation"]),
                    "translationDistance": int(placement["translationDistance"]),
                    "grabEvidence": deepcopy(placement["evidence"]),
                    "errorType": type(error).__name__,
                    "error": str(error),
                    "rank": (0, 0, 0, 0, 0, 0, 0, 0, 0, -int(placement["translationDistance"])),
                }
            variants.append(record)

    variants.sort(key=lambda item: tuple(item.get("rank") or ()), reverse=True)
    selected = variants[:max(0, int(result_limit))]
    for item in selected:
        item.pop("rank", None)

    complete_count = sum(bool((item.get("validation") or {}).get("complete")) for item in variants)
    target_transform_count = sum(
        any(
            int(((item.get("validation") or {}).get("eventCounts") or {}).get(kind) or 0) > 0
            for kind in (
                "atom-purified",
                "atom-projected",
                "atom-duplicated",
                "atom-calcified",
                "atoms-animated",
                "atoms-unified",
                "atom-divided",
            )
        )
        for item in variants
    )
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "inputCount": len(inputs),
            "maxGrabCycles": max(1, int(max_grab_cycles)),
            "validationCycles": max(1, int(validation_cycles)),
            "placementLimitPerInput": max(0, int(placement_limit_per_input)),
            "placementCounts": placement_counts,
            "testedVariantCount": len(variants),
            "returnedVariantCount": len(selected),
            "targetTransformReachedVariantCount": target_transform_count,
            "completeVariantCount": complete_count,
            "hasCompleteSolution": complete_count > 0,
            "mechanicsFingerprint": before_mechanics,
        },
        "variants": selected,
    }


__all__ = ["search_input_feed_lanes"]
