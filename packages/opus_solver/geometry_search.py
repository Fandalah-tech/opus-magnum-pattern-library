from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any

from .candidate_search import invalid_candidate_rank, validation_rank
from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .layout import materialize_candidate_layout
from .manufacturing import ManufacturingPlan
from .scheduling import materialize_candidate_schedule, synchronize_layout_programs
from .solver import validate_generated_solution


def _json_key(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hex_offsets(radius: int) -> list[tuple[int, int]]:
    radius = max(0, int(radius))
    offsets = [
        (q, r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(q + r)) <= radius
    ]
    return sorted(offsets, key=lambda value: (max(abs(value[0]), abs(value[1]), abs(sum(value))), value))


def _add_local_perturbations(
    choices: list[dict[str, Any]],
    *,
    translation_radius: int,
    rotation_radius: int,
) -> list[dict[str, Any]]:
    if not choices or (translation_radius <= 0 and rotation_radius <= 0):
        return choices
    preferred = choices[0].get("transform") or {}
    base_delta = [int(value) for value in preferred.get("delta", [0, 0])]
    base_rotation = int(preferred.get("rotationDelta") or 0)
    seen = {_json_key(choice.get("transform") or {}) for choice in choices}
    rotation_offsets = sorted(range(-max(0, int(rotation_radius)), max(0, int(rotation_radius)) + 1), key=lambda value: (abs(value), value))
    for offset in _hex_offsets(translation_radius):
        for rotation_offset in rotation_offsets:
            if offset == (0, 0) and rotation_offset == 0:
                continue
            transform = deepcopy(preferred)
            transform["delta"] = [base_delta[0] + offset[0], base_delta[1] + offset[1]]
            transform["rotationDelta"] = (base_rotation + rotation_offset) % 6
            key = _json_key(transform)
            if key in seen:
                continue
            seen.add(key)
            choices.append({
                "transform": transform,
                "observationCount": 0,
                "preferred": False,
                "repairEvidence": "local-geometric-perturbation",
                "translationOffset": list(offset),
                "rotationOffset": rotation_offset,
            })
    return choices


def _edge_transform_choices(
    edge: dict[str, Any],
    *,
    synthetic_translation_radius: int = 0,
    synthetic_rotation_radius: int = 0,
) -> list[dict[str, Any]]:
    summary = edge.get("relativeTransforms") or {}
    preferred = summary.get("preferred") if isinstance(summary, dict) else None
    raw_variants = summary.get("variants", []) if isinstance(summary, dict) else []
    choices = []
    seen = set()

    if preferred:
        key = _json_key(preferred)
        seen.add(key)
        preferred_count = next(
            (int(item.get("observationCount") or 0) for item in raw_variants if _json_key(item.get("relativeTransform") or {}) == key),
            0,
        )
        choices.append({"transform": preferred, "observationCount": preferred_count, "preferred": True})

    for item in raw_variants:
        transform = item.get("relativeTransform")
        if not transform:
            continue
        key = _json_key(transform)
        if key in seen:
            continue
        seen.add(key)
        choices.append({
            "transform": transform,
            "observationCount": int(item.get("observationCount") or 0),
            "preferred": False,
        })
    repair_summary = edge.get("repairRelativeTransforms") or {}
    repair_variants = repair_summary.get("variants", []) if isinstance(repair_summary, dict) else []
    for item in repair_variants:
        transform = item.get("relativeTransform")
        if not transform:
            continue
        key = _json_key(transform)
        if key in seen:
            continue
        seen.add(key)
        choices.append({
            "transform": transform,
            "observationCount": int(item.get("observationCount") or 0),
            "preferred": False,
            "repairEvidence": "other-engine-complete-source",
        })
    if not choices and edge.get("relativeTransform"):
        choices.append({"transform": edge["relativeTransform"], "observationCount": 1, "preferred": True})
    return _add_local_perturbations(
        choices,
        translation_radius=synthetic_translation_radius,
        rotation_radius=synthetic_rotation_radius,
    )


def _motif_transform_choices(
    convergence: dict[str, Any],
    input_item: dict[str, Any],
    occurrence: int,
    *,
    synthetic_translation_radius: int = 0,
    synthetic_rotation_radius: int = 0,
) -> list[dict[str, Any]]:
    role = str(input_item.get("sourceRole") or "")
    mechanism = str(input_item.get("sourceMechanismHash") or "")
    counts: dict[str, int] = {}
    payloads: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    samples = list(convergence.get("samples", [])) + list(convergence.get("repairSamples", []))
    for sample in samples:
        matches = [
            item for item in sample.get("inputs", [])
            if str(item.get("sourceRole") or "") == role
            and str(item.get("sourceMechanismHash") or "") == mechanism
        ]
        if occurrence >= len(matches):
            continue
        for transform in matches[occurrence].get("relativeTransforms", []):
            if not transform:
                continue
            key = _json_key(transform)
            if key not in payloads:
                payloads[key] = transform
                order.append(key)
            counts[key] = counts.get(key, 0) + 1

    if not order:
        return []
    preferred_key = order[0]
    remainder = sorted(order[1:], key=lambda key: (-counts.get(key, 0), key))
    ordered = [preferred_key] + remainder
    choices = [
        {
            "transform": payloads[key],
            "observationCount": counts.get(key, 0),
            "preferred": key == preferred_key,
        }
        for key in ordered
    ]
    return _add_local_perturbations(
        choices,
        translation_radius=synthetic_translation_radius,
        rotation_radius=synthetic_rotation_radius,
    )


def transform_slots(
    candidate: dict[str, Any],
    *,
    synthetic_translation_radius: int = 0,
    synthetic_rotation_radius: int = 0,
) -> list[dict[str, Any]]:
    slots = []
    if candidate.get("candidateKind") == "linear-chain" or (candidate.get("nodes") and candidate.get("steps")):
        for step_index, edge in enumerate(candidate.get("steps", [])):
            choices = _edge_transform_choices(
                edge,
                synthetic_translation_radius=synthetic_translation_radius,
                synthetic_rotation_radius=synthetic_rotation_radius,
            )
            if choices:
                slots.append({"slot": f"chain-{step_index}:edge", "choices": choices})
        return slots

    convergence = candidate.get("convergence") or {}
    motif_inputs = list(convergence.get("inputs", []))
    occurrence_counter: dict[tuple[str, str], int] = {}

    for branch_index, branch in enumerate(candidate.get("branches", [])):
        input_item = motif_inputs[branch_index] if branch_index < len(motif_inputs) else {}
        key = (str(input_item.get("sourceRole") or ""), str(input_item.get("sourceMechanismHash") or ""))
        occurrence = occurrence_counter.get(key, 0)
        occurrence_counter[key] = occurrence + 1
        choices = _motif_transform_choices(
            convergence,
            input_item,
            occurrence,
            synthetic_translation_radius=synthetic_translation_radius,
            synthetic_rotation_radius=synthetic_rotation_radius,
        )
        if choices:
            slots.append({"slot": f"branch-{branch_index}:convergence-input", "choices": choices})

        for reverse_index, edge in enumerate(reversed(branch)):
            choices = _edge_transform_choices(
                edge,
                synthetic_translation_radius=synthetic_translation_radius,
                synthetic_rotation_radius=synthetic_rotation_radius,
            )
            if choices:
                slots.append({"slot": f"branch-{branch_index}:edge-{reverse_index}", "choices": choices})

    for tail_index, edge in enumerate(candidate.get("tail", [])):
        choices = _edge_transform_choices(
            edge,
            synthetic_translation_radius=synthetic_translation_radius,
            synthetic_rotation_radius=synthetic_rotation_radius,
        )
        if choices:
            slots.append({"slot": f"tail-{tail_index}:edge", "choices": choices})
    return slots


def enumerate_transform_variants(
    candidate: dict[str, Any],
    *,
    per_slot_limit: int = 3,
    limit: int = 81,
    synthetic_translation_radius: int = 0,
    synthetic_rotation_radius: int = 0,
) -> list[dict[str, Any]]:
    per_slot_limit = max(1, int(per_slot_limit))
    limit = max(0, int(limit))
    if limit == 0:
        return []

    slots = transform_slots(
        candidate,
        synthetic_translation_radius=synthetic_translation_radius,
        synthetic_rotation_radius=synthetic_rotation_radius,
    )
    if not slots:
        return [{"overrides": {}, "displacement": 0, "supportScore": 0.0, "choices": {}}]

    beam = [{"overrides": {}, "displacement": 0, "supportScore": 0.0, "choices": {}}]
    beam_width = max(limit * 4, 100)
    for slot_info in slots:
        slot = str(slot_info["slot"])
        choices = list(slot_info.get("choices", []))[:per_slot_limit]
        expanded = []
        for state in beam:
            for choice_index, choice in enumerate(choices):
                preferred = bool(choice.get("preferred")) or choice_index == 0
                observation_count = max(0, int(choice.get("observationCount") or 0))
                next_state = {
                    "overrides": deepcopy(state["overrides"]),
                    "displacement": int(state["displacement"]) + (0 if preferred else 1),
                    "supportScore": float(state["supportScore"]) + math.log1p(observation_count),
                    "choices": deepcopy(state["choices"]),
                }
                next_state["choices"][slot] = {
                    "observationCount": observation_count,
                    "preferred": preferred,
                    "transform": deepcopy(choice["transform"]),
                }
                if not preferred:
                    next_state["overrides"][slot] = deepcopy(choice["transform"])
                expanded.append(next_state)
        expanded.sort(
            key=lambda item: (
                int(item["displacement"]),
                -float(item["supportScore"]),
                _json_key(item["overrides"]),
            )
        )
        beam = expanded[:beam_width]

    variants = []
    seen = set()
    for item in beam:
        key = _json_key(item["overrides"])
        if key in seen:
            continue
        seen.add(key)
        variants.append(item)
        if len(variants) >= limit:
            break
    return variants


def _progress_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(item.get("rank", ())),
        -int(item.get("staticConflictPenalty") or 0),
        float(item.get("supportScore") or 0.0),
    )


def _survival_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    validation = item.get("validation") or {}
    return (
        int(bool(validation.get("complete"))),
        int(validation.get("totalDelivered") or 0),
        -int(validation.get("totalDeficit") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        -int(item.get("displacement") or 0),
        -int(item.get("staticConflictPenalty") or 0),
        float(item.get("supportScore") or 0.0),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(validation.get("requiredChemistryEventCount") or 0),
        int(validation.get("distinctChemistryEventCount") or 0),
        int(validation.get("chemistryEventCount") or 0),
        int(validation.get("manipulationEventCount") or 0),
    )


def select_search_portfolio(
    records: list[dict[str, Any]],
    *,
    limit: int,
) -> list[tuple[dict[str, Any], list[str]]]:
    """Retain complementary chemical-progress and mechanical-survival fronts."""
    limit = max(0, int(limit))
    if not records or limit == 0:
        return []
    progress = sorted(records, key=_progress_sort_key, reverse=True)
    survival = sorted(records, key=_survival_sort_key, reverse=True)
    progress_quota = (limit + 1) // 2
    survival_quota = limit // 2
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    objectives: dict[int, set[str]] = {}

    def add(record: dict[str, Any], objective: str) -> bool:
        record_key = id(record)
        objectives.setdefault(record_key, set()).add(objective)
        if record_key in selected_ids:
            return False
        selected.append(record)
        selected_ids.add(record_key)
        return True

    progress_added = 0
    for record in progress:
        if progress_added >= progress_quota:
            break
        if add(record, "progress"):
            progress_added += 1

    survival_added = 0
    for record in survival:
        if survival_added >= survival_quota:
            break
        if add(record, "survival"):
            survival_added += 1

    # When the two fronts overlap, fill the remaining capacity while retaining
    # objective labels for any record seen by both lists.
    for progress_record, survival_record in zip(progress, survival):
        if len(selected) >= limit:
            break
        add(progress_record, "progress")
        if len(selected) >= limit:
            break
        add(survival_record, "survival")
    for objective, ordered in (("progress", progress), ("survival", survival)):
        for record in ordered:
            if len(selected) >= limit:
                break
            add(record, objective)

    return [
        (record, sorted(objectives[id(record)]))
        for record in selected[:limit]
    ]


def search_geometric_candidates(
    puzzle: dict[str, Any],
    plan: ManufacturingPlan,
    assembly: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    per_slot_limit: int = 3,
    variant_limit: int = 81,
    result_limit: int = 10,
    synthetic_translation_radius: int = 0,
    synthetic_rotation_radius: int = 0,
    preflight_cycles: int = 0,
    promotion_limit: int = 25,
) -> dict[str, Any]:
    """Search relative transforms with optional short-replay preselection."""
    base_schedule = materialize_candidate_schedule(assembly)
    results = []
    complete_count = 0

    for variant_index, variant in enumerate(
        enumerate_transform_variants(
            assembly,
            per_slot_limit=per_slot_limit,
            limit=variant_limit,
            synthetic_translation_radius=synthetic_translation_radius,
            synthetic_rotation_radius=synthetic_rotation_radius,
        )
    ):
        displacement = int(variant.get("displacement") or 0)
        record: dict[str, Any] = {
            "variantIndex": variant_index,
            "transformOverrides": variant.get("overrides", {}),
            "transformChoices": variant.get("choices", {}),
            "displacement": displacement,
            "supportScore": round(float(variant.get("supportScore") or 0.0), 6),
        }
        try:
            layout = materialize_candidate_layout(
                assembly,
                fragment_index,
                transform_overrides=variant.get("overrides", {}),
            )
            layout_summary = layout.get("summary", {})
            record["layoutSummary"] = layout_summary
            exact_conflicts = int(layout_summary.get("exactStaticConflictCount") or 0)
            approximate_conflicts = int(layout_summary.get("approximateStaticConflictCount") or 0)
            record["staticConflictPenalty"] = exact_conflicts * 100 + approximate_conflicts
            if not layout_summary.get("layoutComplete"):
                record["failureMode"] = "layout-incomplete"
                record["rank"] = invalid_candidate_rank(displacement=displacement)
                results.append(record)
                continue

            synchronized = synchronize_layout_programs(layout, base_schedule)
            record["synchronizedSummary"] = synchronized.get("summary", {})
            if not synchronized.get("summary", {}).get("scheduleComplete"):
                record["failureMode"] = "program-conflict"
                record["programConflicts"] = synchronized.get("programConflicts", [])
                record["rank"] = invalid_candidate_rank(displacement=displacement)
                results.append(record)
                continue

            solution = build_candidate_solution(puzzle, plan, assembly, synchronized)
            roundtrip = serialize_candidate_roundtrip(solution)
            validation = validate_generated_solution(
                puzzle,
                roundtrip["parsed"],
                max_cycles=preflight_cycles if preflight_cycles > 0 else None,
            )
            record["serialization"] = roundtrip["diagnostics"]
            record["validation"] = validation
            record["solution"] = solution
            record["validationScope"] = "preflight" if preflight_cycles > 0 else "full"
            record["_parsedSolution"] = roundtrip["parsed"]
            record["rank"] = validation_rank(validation, displacement=displacement)
            if preflight_cycles <= 0:
                complete_count += int(bool(validation.get("complete")))
        except Exception as exc:
            record["failureMode"] = "generation-error"
            record["generationError"] = {"errorType": type(exc).__name__, "message": str(exc)}
            record["staticConflictPenalty"] = 10**9
            record["rank"] = invalid_candidate_rank(displacement=displacement)
        results.append(record)

    promoted_count = 0
    promoted_objectives: dict[str, int] = {"progress": 0, "survival": 0}
    if preflight_cycles > 0:
        promotable = [record for record in results if record.get("_parsedSolution")]
        promotion_portfolio = select_search_portfolio(
            promotable,
            limit=max(0, int(promotion_limit)),
        )
        for record, objectives in promotion_portfolio:
            record["promotionObjectives"] = objectives
            for objective in objectives:
                promoted_objectives[objective] += 1
            validation = validate_generated_solution(puzzle, record["_parsedSolution"])
            record["validation"] = validation
            record["validationScope"] = "full"
            record["promotedFromPreflight"] = True
            record["rank"] = validation_rank(
                validation,
                displacement=int(record.get("displacement") or 0),
            )
            complete_count += int(bool(validation.get("complete")))
            promoted_count += 1

    selected_portfolio = select_search_portfolio(
        results,
        limit=max(0, int(result_limit)),
    )
    selected = []
    returned_objectives: dict[str, int] = {"progress": 0, "survival": 0}
    for item, objectives in selected_portfolio:
        item["selectionObjectives"] = objectives
        for objective in objectives:
            returned_objectives[objective] += 1
        selected.append(item)
    for item in results:
        item.pop("_parsedSolution", None)
    for item in selected:
        item.pop("rank", None)
    return {
        "schemaVersion": "0.3.0",
        "summary": {
            "searchedVariantCount": len(results),
            "returnedVariantCount": len(selected),
            "completeVariantCount": complete_count,
            "hasCompleteSolution": complete_count > 0,
            "perSlotLimit": per_slot_limit,
            "syntheticTranslationRadius": max(0, int(synthetic_translation_radius)),
            "syntheticRotationRadius": max(0, int(synthetic_rotation_radius)),
            "preflightCycles": max(0, int(preflight_cycles)),
            "promotedVariantCount": promoted_count,
            "promotionLimit": max(0, int(promotion_limit)),
            "selectionPolicy": "progress-survival-portfolio",
            "promotedObjectiveCounts": promoted_objectives,
            "returnedObjectiveCounts": returned_objectives,
        },
        "variants": selected,
    }
