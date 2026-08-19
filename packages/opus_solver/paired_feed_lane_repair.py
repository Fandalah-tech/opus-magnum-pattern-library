from __future__ import annotations

from copy import deepcopy
from typing import Any

from .candidate_solution import serialize_candidate_roundtrip
from .chemistry_transplant import mechanical_fingerprint
from .conversion_opportunities import replay_conversion_opportunities
from .feed_lane_repair import (
    _candidate_input_placements,
    _rank,
    search_input_feed_lanes,
)
from .solver import validate_generated_solution


def search_paired_input_feed_lanes(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_grab_cycles: int = 256,
    validation_cycles: int = 256,
    first_stage_placement_limit: int = 72,
    first_stage_result_limit: int = 6,
    second_stage_placement_limit: int = 48,
    result_limit: int = 20,
) -> dict[str, Any]:
    """Compose two independently learned feed-lane moves with replay feedback.

    Exhaustively pairing every input pose is unnecessary. The first stage keeps
    only single-input moves that already improve the target-free conversion
    gradient. For each surviving seed, the second stage moves one *other* input
    through a bounded spread of learned grab lanes. This turns an N² search into
    a small evidence-guided frontier while preserving the original arm/track
    mechanics and using no target solution geometry.
    """

    inputs = [
        part for part in solution.get("parts", [])
        if str(part.get("type") or "") == "input"
    ]
    input_ids = [str(part.get("id") or "") for part in inputs]
    if len(input_ids) < 2:
        return {
            "schemaVersion": "0.1.0",
            "summary": {
                "inputCount": len(input_ids),
                "firstStageSeedCount": 0,
                "testedVariantCount": 0,
                "returnedVariantCount": 0,
                "readyPurificationPoseReachedVariantCount": 0,
                "bestMinFreeEqualPairDistance": None,
                "completeVariantCount": 0,
                "hasCompleteSolution": False,
            },
            "firstStage": None,
            "variants": [],
        }

    before_mechanics = mechanical_fingerprint(solution)
    first_stage = search_input_feed_lanes(
        puzzle,
        solution,
        max_grab_cycles=max_grab_cycles,
        validation_cycles=validation_cycles,
        placement_limit_per_input=first_stage_placement_limit,
        result_limit=first_stage_result_limit,
    )
    seeds = [
        item
        for item in first_stage.get("variants", [])
        if item.get("solution") is not None
        and not (item.get("validation") or {}).get("blockedInputsAtStart")
    ]

    variants: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, tuple[int, int], int], ...]] = set()
    second_stage_counts: dict[str, int] = {}

    for seed_index, seed in enumerate(seeds, start=1):
        seed_solution = seed["solution"]
        changed_input = str(seed.get("inputId") or "")
        other_inputs = [
            part for part in seed_solution.get("parts", [])
            if str(part.get("type") or "") == "input"
            and str(part.get("id") or "") != changed_input
        ]
        for other_input in other_inputs:
            other_id = str(other_input.get("id") or "")
            placements = _candidate_input_placements(
                puzzle,
                seed_solution,
                other_input,
                max_grab_cycles=max_grab_cycles,
                placement_limit=second_stage_placement_limit,
            )
            second_stage_counts[f"seed-{seed_index}:{other_id}"] = len(placements)
            for placement in placements:
                candidate = deepcopy(seed_solution)
                target_input = next(
                    part for part in candidate.get("parts", [])
                    if str(part.get("id") or "") == other_id
                )
                target_input["position"] = list(placement["position"])
                target_input["rotation"] = int(placement["rotation"])
                if mechanical_fingerprint(candidate) != before_mechanics:
                    raise AssertionError("Paired feed lane repair changed arm/track mechanics")

                signature = tuple(sorted(
                    (
                        str(part.get("id") or ""),
                        tuple(int(value) for value in (part.get("position") or (0, 0))),
                        int(part.get("rotation") or 0) % 6,
                    )
                    for part in candidate.get("parts", [])
                    if str(part.get("type") or "") == "input"
                ))
                if signature in seen:
                    continue
                seen.add(signature)

                try:
                    roundtrip = serialize_candidate_roundtrip(candidate)
                    validation = validate_generated_solution(
                        puzzle,
                        roundtrip["parsed"],
                        max_cycles=max(1, int(validation_cycles)),
                    )
                    if validation.get("blockedInputsAtStart"):
                        conversion = {
                            "kind": "purification-opportunity-gradient",
                            "skipped": True,
                            "skipReason": "blocked-input-at-start",
                            "freeEqualPairObservationCount": 0,
                            "adjacentFreeEqualPairObservationCount": 0,
                            "readyPurificationPoseObservationCount": 0,
                            "framesWithReadyPurificationPose": 0,
                            "minFreeEqualPairDistance": None,
                        }
                    else:
                        conversion = replay_conversion_opportunities(
                            puzzle,
                            roundtrip["parsed"],
                            max_cycles=max(1, int(validation_cycles)),
                        )
                    record = {
                        "seedRank": seed_index,
                        "firstChangedInputId": changed_input,
                        "firstPosition": list(next(
                            part.get("position") or (0, 0)
                            for part in candidate.get("parts", [])
                            if str(part.get("id") or "") == changed_input
                        )),
                        "firstRotation": int(next(
                            part.get("rotation") or 0
                            for part in candidate.get("parts", [])
                            if str(part.get("id") or "") == changed_input
                        )),
                        "secondChangedInputId": other_id,
                        "secondPosition": list(placement["position"]),
                        "secondRotation": int(placement["rotation"]),
                        "secondTranslationDistance": int(placement["translationDistance"]),
                        "secondGrabEvidence": deepcopy(placement["evidence"]),
                        "validation": validation,
                        "conversionOpportunity": conversion,
                        "serialization": roundtrip["diagnostics"],
                        "solution": candidate,
                        "mechanicsPreserved": True,
                    }
                    record["rank"] = _rank(
                        validation,
                        conversion,
                        distance=int(placement["translationDistance"]),
                    )
                except Exception as error:
                    record = {
                        "seedRank": seed_index,
                        "firstChangedInputId": changed_input,
                        "secondChangedInputId": other_id,
                        "secondPosition": list(placement["position"]),
                        "secondRotation": int(placement["rotation"]),
                        "secondTranslationDistance": int(placement["translationDistance"]),
                        "errorType": type(error).__name__,
                        "error": str(error),
                        "rank": (0,) * 14 + (-int(placement["translationDistance"]),),
                    }
                variants.append(record)

    variants.sort(key=lambda item: tuple(item.get("rank") or ()), reverse=True)
    selected = variants[:max(0, int(result_limit))]
    for item in selected:
        item.pop("rank", None)

    finite_distances = [
        int(value)
        for item in variants
        if (value := (item.get("conversionOpportunity") or {}).get("minFreeEqualPairDistance")) is not None
    ]
    ready_count = sum(
        int((item.get("conversionOpportunity") or {}).get("readyPurificationPoseObservationCount") or 0) > 0
        for item in variants
    )
    free_pair_count = sum(
        int((item.get("conversionOpportunity") or {}).get("freeEqualPairObservationCount") or 0) > 0
        for item in variants
    )
    blocked_count = sum(bool((item.get("validation") or {}).get("blockedInputsAtStart")) for item in variants)
    transform_count = sum(
        int(((item.get("validation") or {}).get("eventCounts") or {}).get("atom-purified") or 0) > 0
        for item in variants
    )
    complete_count = sum(bool((item.get("validation") or {}).get("complete")) for item in variants)
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "inputCount": len(input_ids),
            "firstStageSeedCount": len(seeds),
            "secondStagePlacementCounts": second_stage_counts,
            "testedVariantCount": len(variants),
            "returnedVariantCount": len(selected),
            "blockedInputVariantCount": blocked_count,
            "fullySpawnedVariantCount": len(variants) - blocked_count,
            "freeEqualPairReachedVariantCount": free_pair_count,
            "readyPurificationPoseReachedVariantCount": ready_count,
            "purificationReachedVariantCount": transform_count,
            "bestMinFreeEqualPairDistance": min(finite_distances) if finite_distances else None,
            "completeVariantCount": complete_count,
            "hasCompleteSolution": complete_count > 0,
            "mechanicsFingerprint": before_mechanics,
            "rankingPolicy": "staged-single-then-other-input-conversion-gradient",
        },
        "firstStage": {
            "summary": deepcopy(first_stage.get("summary") or {}),
            "seedCount": len(seeds),
            "seedFrontier": [
                {
                    "inputId": item.get("inputId"),
                    "position": item.get("position"),
                    "rotation": item.get("rotation"),
                    "conversionOpportunity": deepcopy(item.get("conversionOpportunity") or {}),
                    "validation": {
                        "completedCycles": int((item.get("validation") or {}).get("completedCycles") or 0),
                        "blockedInputsAtStart": list((item.get("validation") or {}).get("blockedInputsAtStart") or []),
                    },
                }
                for item in seeds
            ],
        },
        "variants": selected,
    }


__all__ = ["search_paired_input_feed_lanes"]
