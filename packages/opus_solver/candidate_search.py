from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Any, Iterable

from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .manufacturing import ManufacturingPlan
from .scheduling import synchronize_layout_programs
from .solver import validate_generated_solution


def _instance_group(instance_id: str) -> str | None:
    value = str(instance_id or "")
    if value.startswith("branch-"):
        return value.split(":", 1)[0]
    if value.startswith("tail-"):
        return value.split(":", 1)[0]
    if value.startswith("chain-") and value != "chain-0":
        return value
    return None


def _normalise_starts(starts: dict[str, int]) -> tuple[dict[str, int], int]:
    if not starts:
        return {}, 0
    minimum = min(starts.values())
    shift = -minimum if minimum < 0 else 0
    return {key: int(value) + shift for key, value in starts.items()}, shift


def apply_schedule_group_offsets(
    schedule: dict[str, Any],
    offsets: dict[str, int],
) -> dict[str, Any]:
    """Shift whole fragment branches/tails while preserving local timing."""
    result = deepcopy(schedule)
    starts = {
        str(key): int(value)
        for key, value in schedule.get("instanceStartCycles", {}).items()
    }
    for instance_id in list(starts):
        group = _instance_group(instance_id)
        if group is not None:
            starts[instance_id] += int(offsets.get(group, 0))
    starts, normalization = _normalise_starts(starts)
    result["instanceStartCycles"] = starts
    result.setdefault("summary", {})["variantOffsets"] = dict(sorted((str(key), int(value)) for key, value in offsets.items()))
    result["summary"]["variantNormalizationShift"] = normalization
    return result


def enumerate_schedule_variants(
    schedule: dict[str, Any],
    *,
    radius: int = 2,
    limit: int = 81,
) -> list[dict[str, Any]]:
    """Enumerate low-distance relative timing variants deterministically.

    Every branch and tail fragment group moves as a unit. `convergence` stays
    fixed except for a final normalization shift that keeps cycles nonnegative.
    Variants are ordered by total absolute displacement so the historical
    timing is always tried first.
    """
    radius = max(0, int(radius))
    limit = max(0, int(limit))
    starts = schedule.get("instanceStartCycles", {})
    groups = sorted({
        group
        for instance_id in starts
        for group in [_instance_group(str(instance_id))]
        if group is not None
    })
    if not groups or limit == 0:
        return [apply_schedule_group_offsets(schedule, {})] if limit else []

    raw = list(product(range(-radius, radius + 1), repeat=len(groups)))
    raw.sort(key=lambda values: (sum(abs(value) for value in values), values))
    variants = []
    seen_starts: set[tuple[tuple[str, int], ...]] = set()
    for values in raw:
        offsets = dict(zip(groups, values))
        variant = apply_schedule_group_offsets(schedule, offsets)
        signature = tuple(sorted((str(key), int(value)) for key, value in variant.get("instanceStartCycles", {}).items()))
        if signature in seen_starts:
            continue
        seen_starts.add(signature)
        variants.append(variant)
        if len(variants) >= limit:
            break
    return variants


def validation_rank(validation: dict[str, Any], *, displacement: int = 0) -> tuple[Any, ...]:
    """Return a sortable progress key; larger values are better."""
    return (
        int(bool(validation.get("complete"))),
        int(validation.get("totalDelivered") or 0),
        -int(validation.get("totalDeficit") or 0),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(validation.get("requiredChemistryEventCount") or 0),
        int(validation.get("distinctChemistryEventCount") or 0),
        int(validation.get("chemistryEventCount") or 0),
        int(validation.get("manipulationEventCount") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        -int(displacement),
    )


def invalid_candidate_rank(*, displacement: int = 0) -> tuple[Any, ...]:
    """Return a rank below every replayed candidate."""
    return (0, -10**9, -10**9, 0, 0, 0, 0, 0, 0, 0, -int(displacement))


def search_temporal_candidates(
    puzzle: dict[str, Any],
    plan: ManufacturingPlan,
    assembly: dict[str, Any],
    layout: dict[str, Any],
    base_schedule: dict[str, Any],
    *,
    radius: int = 2,
    variant_limit: int = 81,
    result_limit: int = 10,
) -> dict[str, Any]:
    """Search small relative timing shifts and retain the best engine results."""
    results = []
    complete_count = 0
    for variant_index, schedule in enumerate(enumerate_schedule_variants(base_schedule, radius=radius, limit=variant_limit)):
        offsets = schedule.get("summary", {}).get("variantOffsets", {})
        displacement = sum(abs(int(value)) for value in offsets.values())
        record: dict[str, Any] = {
            "variantIndex": variant_index,
            "offsets": offsets,
            "displacement": displacement,
        }
        try:
            synchronized = synchronize_layout_programs(layout, schedule)
            if not synchronized.get("summary", {}).get("scheduleComplete"):
                record["failureMode"] = "program-conflict"
                record["programConflicts"] = synchronized.get("programConflicts", [])
                record["rank"] = invalid_candidate_rank(displacement=displacement)
                results.append(record)
                continue

            solution = build_candidate_solution(puzzle, plan, assembly, synchronized)
            roundtrip = serialize_candidate_roundtrip(solution)
            validation = validate_generated_solution(puzzle, roundtrip["parsed"])
            record["serialization"] = roundtrip["diagnostics"]
            record["validation"] = validation
            record["solution"] = solution
            record["rank"] = validation_rank(validation, displacement=displacement)
            complete_count += int(bool(validation.get("complete")))
        except Exception as exc:
            record["failureMode"] = "generation-error"
            record["generationError"] = {"errorType": type(exc).__name__, "message": str(exc)}
            record["rank"] = invalid_candidate_rank(displacement=displacement)
        results.append(record)

    results.sort(key=lambda item: tuple(item.get("rank", ())), reverse=True)
    selected = results[:max(0, int(result_limit))]
    for item in selected:
        item.pop("rank", None)
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "searchedVariantCount": len(results),
            "returnedVariantCount": len(selected),
            "completeVariantCount": complete_count,
            "hasCompleteSolution": complete_count > 0,
            "radius": max(0, int(radius)),
        },
        "variants": selected,
    }
