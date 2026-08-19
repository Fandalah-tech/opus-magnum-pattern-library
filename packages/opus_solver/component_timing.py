from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable

from .candidate_search import invalid_candidate_rank, validation_rank
from .candidate_solution import serialize_candidate_roundtrip
from .geometry_search import select_search_portfolio
from .solver import validate_generated_solution


PROGRAMMABLE_ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
OracleValidator = Callable[[dict[str, Any]], dict[str, Any]]


def _program_cycles(part: dict[str, Any]) -> list[int]:
    return sorted({int(item.get("cycle") or 0) for item in part.get("program", [])})


def _nearest_cycle(cycles: list[int], target: int) -> int | None:
    if not cycles:
        return None
    return min(cycles, key=lambda cycle: (abs(cycle - int(target)), cycle))


def component_program_cutpoints(
    part: dict[str, Any],
    validation: dict[str, Any] | None = None,
    *,
    limit: int = 16,
) -> list[int]:
    """Choose deterministic instruction boundaries near active/failing cycles."""
    cycles = _program_cycles(part)
    limit = max(0, int(limit))
    if not cycles or limit == 0:
        return []

    validation = validation or {}
    targets: list[int] = list(range(1, 7))
    for item in validation.get("requiredChemistryEventTimeline", []):
        cycle = int(item.get("cycle") or 0)
        targets.extend((cycle - 1, cycle, cycle + 1))
    first_error = validation.get("firstError") or {}
    if first_error.get("cycle") is not None:
        cycle = int(first_error["cycle"])
        targets.extend((cycle - 2, cycle - 1, cycle, cycle + 1, cycle + 2))

    # A negative suffix shift is only possible at an existing wait. Include
    # those boundaries even when no local chemistry happened before failure.
    targets.extend(
        cycle
        for previous, cycle in zip(cycles, cycles[1:])
        if cycle - previous > 1
    )
    targets.extend(cycles)

    cutpoints: list[int] = []
    seen: set[int] = set()
    for target in targets:
        nearest = _nearest_cycle(cycles, target)
        if nearest is None or nearest in seen:
            continue
        seen.add(nearest)
        cutpoints.append(nearest)
        if len(cutpoints) >= limit:
            break
    return cutpoints


def apply_component_timing_edit(
    solution: dict[str, Any],
    *,
    part_id: str,
    cut_cycle: int,
    delta: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Shift one physical arm's program suffix, inserting/removing tempo."""
    delta = int(delta)
    if delta == 0:
        raise ValueError("A component timing edit requires a non-zero delta")
    edited = deepcopy(solution)
    part = next(
        (item for item in edited.get("parts", []) if str(item.get("id")) == str(part_id)),
        None,
    )
    if part is None:
        raise ValueError(f"Unknown programmable component: {part_id}")
    program = part.get("program", [])
    prefix = [item for item in program if int(item.get("cycle") or 0) < int(cut_cycle)]
    shifted = [item for item in program if int(item.get("cycle") or 0) >= int(cut_cycle)]
    if not shifted:
        raise ValueError(f"No instruction at or after cycle {cut_cycle} for {part_id}")
    for item in shifted:
        item["cycle"] = int(item.get("cycle") or 0) + delta

    cycles = [int(item.get("cycle") or 0) for item in program]
    if min(cycles, default=0) < 0:
        raise ValueError("A component timing edit cannot create negative cycles")
    if len(cycles) != len(set(cycles)):
        raise ValueError("A component timing edit cannot overlap instructions")
    if prefix and min(int(item.get("cycle") or 0) for item in shifted) <= max(
        int(item.get("cycle") or 0) for item in prefix
    ):
        raise ValueError("A component timing edit cannot reorder instructions")
    part["program"] = sorted(program, key=lambda item: int(item.get("cycle") or 0))
    return edited, {
        "partId": str(part_id),
        "partType": str(part.get("type") or "unknown"),
        "cutCycle": int(cut_cycle),
        "delta": delta,
        "shiftedInstructionCount": len(shifted),
    }


def enumerate_component_timing_variants(
    solution: dict[str, Any],
    validation: dict[str, Any] | None = None,
    *,
    radius: int = 2,
    cutpoint_limit: int = 16,
    limit: int = 64,
) -> list[dict[str, Any]]:
    """Enumerate bounded suffix edits on unique physical arm programs."""
    radius = max(0, int(radius))
    limit = max(0, int(limit))
    if radius == 0 or limit == 0:
        return []
    deltas = [value for step in range(1, radius + 1) for value in (step, -step)]
    variants: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[tuple[int, str], ...]]] = set()

    programmable = sorted(
        (
            part for part in solution.get("parts", [])
            if str(part.get("type") or "") in PROGRAMMABLE_ARM_TYPES and part.get("program")
        ),
        key=lambda part: str(part.get("id") or ""),
    )
    for part in programmable:
        part_id = str(part.get("id") or "")
        for cut_cycle in component_program_cutpoints(
            part,
            validation,
            limit=cutpoint_limit,
        ):
            for delta in deltas:
                try:
                    variant_solution, edit = apply_component_timing_edit(
                        solution,
                        part_id=part_id,
                        cut_cycle=cut_cycle,
                        delta=delta,
                    )
                except ValueError:
                    continue
                edited_part = next(
                    item for item in variant_solution.get("parts", [])
                    if str(item.get("id")) == part_id
                )
                signature = (
                    part_id,
                    tuple(
                        (int(item.get("cycle") or 0), str(item.get("instruction") or ""))
                        for item in edited_part.get("program", [])
                    ),
                )
                if signature in seen:
                    continue
                seen.add(signature)
                variants.append({"solution": variant_solution, "edit": edit})
                if len(variants) >= limit:
                    return variants
    return variants


def _source_records(
    sources: list[dict[str, Any]],
    *,
    limit: int,
) -> list[tuple[dict[str, Any], list[str]]]:
    ranked = []
    for source_index, source in enumerate(sources):
        if not source.get("solution"):
            continue
        validation = source.get("validation") or source.get("engineValidation") or {}
        record = dict(source)
        record["_sourceIndex"] = source_index
        record["validation"] = validation
        record["rank"] = validation_rank(
            validation,
            displacement=int(source.get("displacement") or 0),
        )
        ranked.append(record)
    return select_search_portfolio(ranked, limit=max(0, int(limit)))


def oracle_outcome(validation: dict[str, Any] | None) -> str:
    validation = validation or {}
    if validation.get("valid"):
        return "complete"
    raw = str(validation.get("rawOutput") or "").lower()
    if "did not complete within cycle limit" in raw or "maximum cycle" in raw:
        return "cycle-limit"
    if "collision" in raw:
        return "collision"
    if "isn't on a track" in raw or "not on a track" in raw:
        return "track-error"
    if "instruction conflict" in raw:
        return "instruction-conflict"
    return "other"


def _oracle_progress_key(record: dict[str, Any]) -> tuple[Any, ...]:
    outcome = str(record.get("oracleOutcome") or "other")
    return (
        int(outcome == "complete"),
        int(outcome == "cycle-limit"),
        tuple(record.get("rank", ())),
    )


def _oracle_survival_key(record: dict[str, Any]) -> tuple[Any, ...]:
    outcome = str(record.get("oracleOutcome") or "other")
    outcome_rank = {
        "complete": 5,
        "cycle-limit": 4,
        "collision": 3,
        "track-error": 2,
        "instruction-conflict": 1,
        "other": 0,
    }
    oracle = record.get("oracleValidation") or {}
    issue = next(iter(oracle.get("issues", [])), {})
    cycle = issue.get("cycle")
    return (
        outcome_rank.get(outcome, 0),
        int(cycle if cycle is not None else 10**9),
        int((record.get("validation") or {}).get("completedCycles") or 0),
        tuple(record.get("rank", ())),
    )


def select_oracle_portfolio(
    records: list[dict[str, Any]],
    *,
    limit: int,
) -> list[tuple[dict[str, Any], list[str]]]:
    """Select progress/survival fronts with the external oracle authoritative."""
    limit = max(0, int(limit))
    if not records or limit == 0:
        return []
    progress = sorted(records, key=_oracle_progress_key, reverse=True)
    survival = sorted(records, key=_oracle_survival_key, reverse=True)
    selected: list[dict[str, Any]] = []
    objectives: dict[int, set[str]] = {}

    def add(record: dict[str, Any], objective: str) -> bool:
        key = id(record)
        objectives.setdefault(key, set()).add(objective)
        if any(id(item) == key for item in selected):
            return False
        selected.append(record)
        return True

    quotas = {"progress": (limit + 1) // 2, "survival": limit // 2}
    for objective, ordered in (("progress", progress), ("survival", survival)):
        added = 0
        for record in ordered:
            if add(record, objective):
                added += 1
            if added >= quotas[objective]:
                break
    for objective, ordered in (("progress", progress), ("survival", survival)):
        for record in ordered:
            if len(selected) >= limit:
                break
            add(record, objective)
    return [(record, sorted(objectives[id(record)])) for record in selected[:limit]]


def search_component_timing_candidates(
    puzzle: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    source_limit: int = 6,
    radius: int = 2,
    cutpoint_limit: int = 16,
    variants_per_source: int = 64,
    result_limit: int = 20,
    preflight_cycles: int = 0,
    promotion_limit: int = 40,
    oracle_validator: OracleValidator | None = None,
    oracle_workers: int = 1,
) -> dict[str, Any]:
    """Repair retained geometries by editing physical-component program tempo."""
    results: list[dict[str, Any]] = []
    complete_count = 0
    selected_sources = _source_records(sources, limit=source_limit)
    source_objectives = {"progress": 0, "survival": 0}

    for source, objectives in selected_sources:
        for objective in objectives:
            source_objectives[objective] += 1
        source_validation = source.get("validation") or {}
        for variant in enumerate_component_timing_variants(
            source["solution"],
            source_validation,
            radius=radius,
            cutpoint_limit=cutpoint_limit,
            limit=variants_per_source,
        ):
            edit = variant["edit"]
            record: dict[str, Any] = {
                "variantIndex": len(results),
                "sourceIndex": int(source.get("_sourceIndex") or 0),
                "sourceVariantIndex": source.get("variantIndex"),
                "sourceKind": str(source.get("sourceKind") or "candidate"),
                "sourceSelectionObjectives": objectives,
                "programEdit": edit,
                "displacement": abs(int(edit["delta"])),
                "supportScore": float(source.get("supportScore") or 0.0),
                "staticConflictPenalty": int(source.get("staticConflictPenalty") or 0),
            }
            try:
                roundtrip = serialize_candidate_roundtrip(variant["solution"])
                validation = validate_generated_solution(
                    puzzle,
                    roundtrip["parsed"],
                    max_cycles=preflight_cycles if preflight_cycles > 0 else None,
                )
                record["serialization"] = roundtrip["diagnostics"]
                record["validation"] = validation
                record["solution"] = variant["solution"]
                record["validationScope"] = "preflight" if preflight_cycles > 0 else "full"
                record["_parsedSolution"] = roundtrip["parsed"]
                record["rank"] = validation_rank(
                    validation,
                    displacement=int(record["displacement"]),
                )
                if preflight_cycles <= 0:
                    complete_count += int(bool(validation.get("complete")))
            except Exception as exc:
                record["failureMode"] = "generation-error"
                record["generationError"] = {
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                }
                record["rank"] = invalid_candidate_rank(
                    displacement=int(record["displacement"]),
                )
            results.append(record)

    promoted_count = 0
    promoted_objectives = {"progress": 0, "survival": 0}
    if preflight_cycles > 0:
        promotable = [record for record in results if record.get("_parsedSolution")]
        for record, objectives in select_search_portfolio(
            promotable,
            limit=max(0, int(promotion_limit)),
        ):
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

    oracle_outcomes: Counter[str] = Counter()
    oracle_complete_count = 0
    if oracle_validator is not None:
        oracle_records = [record for record in results if record.get("solution")]

        def validate_with_oracle(record: dict[str, Any]) -> dict[str, Any]:
            try:
                return oracle_validator(record["solution"])
            except Exception as exc:
                return {
                    "valid": False,
                    "rawOutput": f"oracle validation error: {type(exc).__name__}: {exc}",
                    "issues": [{"cycle": None, "message": str(exc)}],
                }

        with ThreadPoolExecutor(max_workers=max(1, min(10, int(oracle_workers)))) as executor:
            validations = list(executor.map(validate_with_oracle, oracle_records))
        for record, oracle_validation in zip(oracle_records, validations):
            outcome = oracle_outcome(oracle_validation)
            record["oracleValidation"] = oracle_validation
            record["oracleOutcome"] = outcome
            oracle_outcomes[outcome] += 1
            oracle_complete_count += int(bool(oracle_validation.get("valid")))

    if oracle_validator is not None:
        selected_portfolio = select_oracle_portfolio(
            results,
            limit=max(0, int(result_limit)),
        )
    else:
        selected_portfolio = select_search_portfolio(
            results,
            limit=max(0, int(result_limit)),
        )
    selected = []
    returned_objectives = {"progress": 0, "survival": 0}
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
        "schemaVersion": "0.1.0",
        "summary": {
            "searchedSourceCount": len(selected_sources),
            "searchedVariantCount": len(results),
            "returnedVariantCount": len(selected),
            "completeVariantCount": complete_count,
            "hasCompleteSolution": complete_count > 0 or oracle_complete_count > 0,
            "sourceLimit": max(0, int(source_limit)),
            "radius": max(0, int(radius)),
            "cutpointLimit": max(0, int(cutpoint_limit)),
            "variantsPerSource": max(0, int(variants_per_source)),
            "preflightCycles": max(0, int(preflight_cycles)),
            "promotedVariantCount": promoted_count,
            "promotionLimit": max(0, int(promotion_limit)),
            "selectionPolicy": (
                "oracle-progress-survival-portfolio"
                if oracle_validator is not None
                else "progress-survival-portfolio"
            ),
            "oracleValidatedVariantCount": sum(oracle_outcomes.values()),
            "oracleCompleteVariantCount": oracle_complete_count,
            "oracleOutcomeCounts": dict(sorted(oracle_outcomes.items())),
            "sourceObjectiveCounts": source_objectives,
            "promotedObjectiveCounts": promoted_objectives,
            "returnedObjectiveCounts": returned_objectives,
        },
        "variants": selected,
    }
