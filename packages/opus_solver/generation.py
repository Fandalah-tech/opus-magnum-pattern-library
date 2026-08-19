from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Callable

from .assembly import rank_fragment_assemblies
from .candidate_search import search_temporal_candidates, validation_rank
from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .chemistry_composition import manufacturing_requirements, rank_chains_for_manufacturing_plan
from .chemistry_transplant import search_chemistry_transplant_candidates
from .component_timing import search_component_timing_candidates, select_oracle_portfolio
from .geometry_search import search_geometric_candidates
from .layout import materialize_candidate_layout
from .manufacturing import build_manufacturing_plan
from .ordered_chemistry import search_ordered_chemistry_candidates
from .product_completion import (
    search_repeating_product_completions,
    search_single_product_completions,
)
from .repair_policy import recommend_repair_order
from .scheduling import materialize_candidate_schedule, synchronize_layout_programs
from .solver import validate_generated_solution


def _global_component_timing_portfolio(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> dict[str, Any]:
    """Reallocate oracle result capacity across assembly families globally."""
    records = []
    for candidate in candidates:
        for variant in candidate.get("componentTimingSearch", {}).get("variants", []):
            record = deepcopy(variant)
            record["candidateRank"] = int(candidate.get("rank") or 0)
            record["rank"] = validation_rank(
                record.get("validation") or {},
                displacement=int(record.get("displacement") or 0),
            )
            records.append(record)

    selected = []
    objective_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    for record, objectives in select_oracle_portfolio(
        records,
        limit=max(0, int(limit)),
    ):
        record.pop("rank", None)
        record["globalSelectionObjectives"] = objectives
        objective_counts.update(objectives)
        outcome_counts[str(record.get("oracleOutcome") or "unknown")] += 1
        selected.append(record)
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "candidateVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "selectionPolicy": "global-oracle-progress-survival-portfolio",
            "returnedObjectiveCounts": dict(sorted(objective_counts.items())),
            "returnedOracleOutcomeCounts": dict(sorted(outcome_counts.items())),
        },
        "variants": selected,
    }


def generate_composed_candidates(
    puzzle: dict[str, Any],
    flow_index: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    limit: int = 10,
    validate_engine: bool = True,
    temporal_search_radius: int = 0,
    temporal_variant_limit: int = 81,
    temporal_result_limit: int = 10,
    transform_search_limit: int = 0,
    transform_per_slot_limit: int = 3,
    transform_result_limit: int = 10,
    transform_synthetic_translation_radius: int = 0,
    transform_synthetic_rotation_radius: int = 0,
    transform_preflight_cycles: int = 0,
    transform_promotion_limit: int = 25,
    component_timing_search_limit: int = 0,
    component_timing_source_limit: int = 6,
    component_timing_radius: int = 2,
    component_timing_cutpoint_limit: int = 16,
    component_timing_result_limit: int = 20,
    component_timing_preflight_cycles: int = 0,
    component_timing_promotion_limit: int = 40,
    component_timing_oracle_validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    component_timing_oracle_workers: int = 1,
    component_timing_global_result_limit: int = 0,
    chemistry_transplant_variant_limit: int = 0,
    chemistry_transplant_source_limit: int = 4,
    chemistry_transplant_result_limit: int = 20,
    chemistry_transplant_max_grab_cycles: int = 256,
    chemistry_transplant_local_cycles: int = 160,
    chemistry_transplant_oracle_promotion_limit: int = 120,
    ordered_chemistry_variant_limit: int = 0,
    ordered_chemistry_source_limit: int = 8,
    ordered_chemistry_calcification_variant_limit: int = 256,
    ordered_chemistry_result_limit: int = 20,
    ordered_chemistry_local_cycles: int = 160,
    ordered_chemistry_persistence_frames: int = 2,
    ordered_chemistry_prism_oracle_promotion_limit: int = 32,
    ordered_chemistry_calcification_oracle_promotion_limit: int = 40,
    single_product_source_limit: int = 0,
    single_product_result_limit: int = 20,
    single_product_local_cycles: int = 100,
    single_product_oracle_promotion_limit: int = 20,
    single_product_oracle_validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    repeating_product_source_limit: int = 0,
    repeating_product_result_limit: int = 20,
    repeating_product_local_cycles: int = 400,
    repeating_product_oracle_promotion_limit: int = 20,
    full_product_oracle_validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    chain_max_depth: int = 8,
    min_engine_validated_solutions: int = 0,
) -> dict[str, Any]:
    """Run assembly generation and route bounded repair from diagnostics."""
    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        return {
            "schemaVersion": "0.4.0",
            "plan": plan.to_dict(),
            "summary": {
                "supported": False,
                "assemblyCandidateCount": 0,
                "serializableCount": 0,
                "engineCompleteCount": 0,
                "temporalVariantCount": 0,
                "temporalCompleteCount": 0,
                "geometricVariantCount": 0,
                "geometricCompleteCount": 0,
                "componentTimingVariantCount": 0,
                "componentTimingCompleteCount": 0,
                "chemistryTransplantVariantCount": 0,
                "chemistryTransplantOracleStableActiveCount": 0,
                "orderedChemistryPrismVariantCount": 0,
                "orderedChemistryCalcificationVariantCount": 0,
                "singleProductCompletionCount": 0,
                "oracleSingleProductCompleteCount": 0,
                "hasOracleSingleProduct": False,
                "bestSingleProductCycle": None,
                "repeatingProductCompletionCount": 0,
                "oracleFullProductCompleteCount": 0,
                "hasOracleFullPuzzle": False,
                "bestFullProductCycle": None,
            },
            "candidates": [],
        }

    requirements = manufacturing_requirements(plan)
    if requirements["requiresConvergence"]:
        assemblies = [
            {**item, "candidateKind": "convergent-assembly"}
            for item in rank_fragment_assemblies(plan, flow_index, limit=max(1, int(limit)))
        ]
    else:
        assemblies = [
            {**item, "candidateKind": "linear-chain"}
            for item in rank_chains_for_manufacturing_plan(
                plan,
                flow_index,
                fragment_index=fragment_index,
                max_depth=chain_max_depth,
                limit=max(1, int(limit)),
                min_engine_validated_solutions=min_engine_validated_solutions,
            )
        ]
    results = []
    serializable_count = 0
    engine_complete_count = 0
    temporal_variant_count = 0
    temporal_complete_count = 0
    geometric_variant_count = 0
    geometric_complete_count = 0
    component_timing_variant_count = 0
    component_timing_complete_count = 0
    component_timing_oracle_complete_count = 0
    failure_modes: Counter[str] = Counter()
    repair_routes: Counter[str] = Counter()

    for index, assembly in enumerate(assemblies):
        record: dict[str, Any] = {
            "rank": index + 1,
            "assemblyScore": assembly.get("score"),
            "assembly": assembly,
        }
        try:
            layout = materialize_candidate_layout(assembly, fragment_index)
            layout_summary = layout.get("summary", {})
            record["layoutSummary"] = layout_summary
            schedule = materialize_candidate_schedule(assembly)
            record["scheduleSummary"] = schedule.get("summary", {})
            synchronized = synchronize_layout_programs(layout, schedule)
            record["synchronizedSummary"] = synchronized.get("summary", {})

            solution = build_candidate_solution(puzzle, plan, assembly, synchronized)
            record["capabilityAdaptation"] = {
                "prunedUnavailableParts": list((solution.get("source") or {}).get("prunedUnavailableParts", [])),
            }
            roundtrip = serialize_candidate_roundtrip(solution)
            record["serialization"] = roundtrip["diagnostics"]
            record["solution"] = solution
            serializable_count += int(bool(roundtrip["diagnostics"].get("roundTripClean")))

            validation = None
            if validate_engine:
                try:
                    validation = validate_generated_solution(puzzle, roundtrip["parsed"])
                    record["engineValidation"] = validation
                    failure_modes[str(validation.get("failureMode") or "complete")] += 1
                    if validation.get("complete"):
                        engine_complete_count += 1
                except Exception as exc:
                    validation = {
                        "complete": False,
                        "failureMode": "validation-error",
                        "errorType": type(exc).__name__,
                        "message": str(exc),
                    }
                    record["engineValidation"] = validation
                    failure_modes["validation-error"] += 1

            if not validate_engine or bool((validation or {}).get("complete")):
                results.append(record)
                continue

            temporal_enabled = (
                temporal_search_radius > 0
                and bool(layout_summary.get("layoutComplete"))
                and bool(schedule.get("summary", {}).get("scheduleComplete"))
            )
            geometric_enabled = (
                transform_search_limit > 0
                and bool(schedule.get("summary", {}).get("scheduleComplete"))
            )
            policy = recommend_repair_order(
                validation,
                layout_summary,
                temporal_enabled=temporal_enabled,
                geometric_enabled=geometric_enabled,
            )
            record["repairPolicy"] = policy
            repair_routes[">".join(policy.get("order", [])) or "none"] += 1

            repaired = False
            for repair in policy.get("order", []):
                if repair == "timing":
                    search = search_temporal_candidates(
                        puzzle,
                        plan,
                        assembly,
                        layout,
                        schedule,
                        radius=temporal_search_radius,
                        variant_limit=temporal_variant_limit,
                        result_limit=temporal_result_limit,
                    )
                    record["temporalSearch"] = search
                    temporal_variant_count += int(search.get("summary", {}).get("searchedVariantCount") or 0)
                    temporal_complete_count += int(search.get("summary", {}).get("completeVariantCount") or 0)
                    repaired = bool(search.get("summary", {}).get("hasCompleteSolution"))
                elif repair == "geometry":
                    search = search_geometric_candidates(
                        puzzle,
                        plan,
                        assembly,
                        fragment_index,
                        per_slot_limit=transform_per_slot_limit,
                        variant_limit=transform_search_limit,
                        result_limit=transform_result_limit,
                        synthetic_translation_radius=transform_synthetic_translation_radius,
                        synthetic_rotation_radius=transform_synthetic_rotation_radius,
                        preflight_cycles=transform_preflight_cycles,
                        promotion_limit=transform_promotion_limit,
                    )
                    record["geometricSearch"] = search
                    geometric_variant_count += int(search.get("summary", {}).get("searchedVariantCount") or 0)
                    geometric_complete_count += int(search.get("summary", {}).get("completeVariantCount") or 0)
                    repaired = bool(search.get("summary", {}).get("hasCompleteSolution"))
                if repaired:
                    record["repairSucceededWith"] = repair
                    break

            if not repaired and component_timing_search_limit > 0:
                component_sources = []
                for source_kind, search_name in (
                    ("geometry", "geometricSearch"),
                    ("timing", "temporalSearch"),
                ):
                    for variant in record.get(search_name, {}).get("variants", []):
                        component_sources.append({**variant, "sourceKind": source_kind})
                component_sources.append({
                    "solution": solution,
                    "validation": validation,
                    "sourceKind": "base",
                    "variantIndex": None,
                })
                search = search_component_timing_candidates(
                    puzzle,
                    component_sources,
                    source_limit=component_timing_source_limit,
                    radius=component_timing_radius,
                    cutpoint_limit=component_timing_cutpoint_limit,
                    variants_per_source=component_timing_search_limit,
                    result_limit=max(
                        int(component_timing_result_limit),
                        int(component_timing_global_result_limit),
                    ),
                    preflight_cycles=component_timing_preflight_cycles,
                    promotion_limit=component_timing_promotion_limit,
                    oracle_validator=component_timing_oracle_validator,
                    oracle_workers=component_timing_oracle_workers,
                )
                record["componentTimingSearch"] = search
                component_timing_variant_count += int(
                    search.get("summary", {}).get("searchedVariantCount") or 0
                )
                component_timing_complete_count += int(
                    search.get("summary", {}).get("completeVariantCount") or 0
                )
                component_timing_oracle_complete_count += int(
                    search.get("summary", {}).get("oracleCompleteVariantCount") or 0
                )
                if search.get("summary", {}).get("hasCompleteSolution"):
                    record["repairSucceededWith"] = "component-timing"
        except Exception as exc:
            record["generationError"] = {"errorType": type(exc).__name__, "message": str(exc)}
            failure_modes["generation-error"] += 1
        results.append(record)

    global_component_portfolio = (
        _global_component_timing_portfolio(
            results,
            limit=component_timing_global_result_limit,
        )
        if component_timing_oracle_validator is not None
        else None
    )
    chemistry_transplant_search = None
    if (
        chemistry_transplant_variant_limit > 0
        and global_component_portfolio is not None
    ):
        chemistry_transplant_search = search_chemistry_transplant_candidates(
            puzzle,
            global_component_portfolio.get("variants", []),
            source_limit=chemistry_transplant_source_limit,
            variant_limit=chemistry_transplant_variant_limit,
            result_limit=chemistry_transplant_result_limit,
            max_grab_cycles=chemistry_transplant_max_grab_cycles,
            local_cycles=chemistry_transplant_local_cycles,
            oracle_promotion_limit=chemistry_transplant_oracle_promotion_limit,
            oracle_validator=component_timing_oracle_validator,
            oracle_workers=component_timing_oracle_workers,
        )
    chemistry_transplant_summary = (chemistry_transplant_search or {}).get("summary", {})
    ordered_chemistry_search = None
    if (
        ordered_chemistry_variant_limit > 0
        and chemistry_transplant_search is not None
    ):
        ordered_chemistry_search = search_ordered_chemistry_candidates(
            puzzle,
            chemistry_transplant_search.get("variants", []),
            source_limit=ordered_chemistry_source_limit,
            prism_variant_limit=ordered_chemistry_variant_limit,
            calcification_variant_limit=ordered_chemistry_calcification_variant_limit,
            result_limit=ordered_chemistry_result_limit,
            local_cycles=ordered_chemistry_local_cycles,
            persistence_frames=ordered_chemistry_persistence_frames,
            prism_oracle_promotion_limit=(
                ordered_chemistry_prism_oracle_promotion_limit
            ),
            calcification_oracle_promotion_limit=(
                ordered_chemistry_calcification_oracle_promotion_limit
            ),
            oracle_validator=component_timing_oracle_validator,
            oracle_workers=component_timing_oracle_workers,
        )
    ordered_chemistry_summary = (ordered_chemistry_search or {}).get("summary", {})
    product_completion_search = None
    if single_product_source_limit > 0 and ordered_chemistry_search is not None:
        product_sources = [
            *(ordered_chemistry_search.get("prismVariants") or []),
            *(ordered_chemistry_search.get("variants") or []),
        ]
        product_completion_search = search_single_product_completions(
            puzzle,
            product_sources,
            source_limit=single_product_source_limit,
            local_cycles=single_product_local_cycles,
            persistence_frames=ordered_chemistry_persistence_frames,
            result_limit=single_product_result_limit,
            oracle_promotion_limit=single_product_oracle_promotion_limit,
            product_oracle_validator=single_product_oracle_validator,
            oracle_workers=component_timing_oracle_workers,
        )
    product_completion_summary = (product_completion_search or {}).get("summary", {})
    repeating_product_search = None
    if repeating_product_source_limit > 0 and product_completion_search is not None:
        repeating_product_search = search_repeating_product_completions(
            puzzle,
            product_completion_search.get("variants", []),
            source_limit=repeating_product_source_limit,
            local_cycles=repeating_product_local_cycles,
            result_limit=repeating_product_result_limit,
            oracle_promotion_limit=repeating_product_oracle_promotion_limit,
            full_product_oracle_validator=full_product_oracle_validator,
            oracle_workers=component_timing_oracle_workers,
        )
    repeating_product_summary = (repeating_product_search or {}).get("summary", {})

    return {
        "schemaVersion": "0.10.0",
        "plan": plan.to_dict(),
        "summary": {
            "supported": True,
            "assemblyCandidateCount": len(assemblies),
            "serializableCount": serializable_count,
            "engineCompleteCount": engine_complete_count,
            "temporalVariantCount": temporal_variant_count,
            "temporalCompleteCount": temporal_complete_count,
            "geometricVariantCount": geometric_variant_count,
            "geometricCompleteCount": geometric_complete_count,
            "componentTimingVariantCount": component_timing_variant_count,
            "componentTimingCompleteCount": component_timing_complete_count,
            "componentTimingOracleCompleteCount": component_timing_oracle_complete_count,
            "chemistryTransplantVariantCount": int(
                chemistry_transplant_summary.get("searchedVariantCount") or 0
            ),
            "chemistryTransplantOracleStableActiveCount": int(
                chemistry_transplant_summary.get(
                    "oracleStableActiveFullOperationVariantCount"
                ) or 0
            ),
            "hasOracleStableActiveChemistryTransplant": bool(
                chemistry_transplant_summary.get("hasOracleStableActiveTransplant")
            ),
            "orderedChemistryPrismVariantCount": int(
                ordered_chemistry_summary.get("searchedPrismVariantCount") or 0
            ),
            "orderedChemistryCalcificationVariantCount": int(
                ordered_chemistry_summary.get("searchedCalcificationVariantCount") or 0
            ),
            "orderedChemistryOracleStableCompleteTriplexCount": int(
                ordered_chemistry_summary.get("oracleStableCompleteTriplexCount") or 0
            ),
            "orderedChemistryOracleStableCalcifiedCompleteTriplexCount": int(
                ordered_chemistry_summary.get(
                    "oracleStableCalcifiedCompleteTriplexCount"
                ) or 0
            ),
            "hasPersistentCompleteTriplex": bool(
                ordered_chemistry_summary.get("hasPersistentCompleteTriplex")
            ),
            "hasPersistentCalcifiedCompleteTriplex": bool(
                ordered_chemistry_summary.get(
                    "hasPersistentCalcifiedCompleteTriplex"
                )
            ),
            "singleProductCompletionCount": int(
                product_completion_summary.get("localSingleProductCompleteCount") or 0
            ),
            "oracleSingleProductCompleteCount": int(
                product_completion_summary.get("oracleSingleProductCompleteCount") or 0
            ),
            "hasOracleSingleProduct": bool(
                product_completion_summary.get("hasOracleSingleProduct")
            ),
            "bestSingleProductCycle": product_completion_summary.get(
                "bestSingleProductCycle"
            ),
            "repeatingProductCompletionCount": int(
                repeating_product_summary.get("localFullProductCompleteCount") or 0
            ),
            "oracleFullProductCompleteCount": int(
                repeating_product_summary.get("oracleFullProductCompleteCount") or 0
            ),
            "hasOracleFullPuzzle": bool(
                repeating_product_summary.get("hasOracleFullPuzzle")
            ),
            "bestFullProductCycle": repeating_product_summary.get(
                "bestFullProductCycle"
            ),
            "hasCompleteSolution": (
                engine_complete_count > 0
                or temporal_complete_count > 0
                or geometric_complete_count > 0
                or component_timing_complete_count > 0
                or component_timing_oracle_complete_count > 0
                or int(ordered_chemistry_summary.get("oracleCompleteVariantCount") or 0) > 0
                or bool(repeating_product_summary.get("hasOracleFullPuzzle"))
            ),
            "failureModes": dict(sorted(failure_modes.items())),
            "repairRoutes": dict(sorted(repair_routes.items())),
            "temporalSearchRadius": max(0, int(temporal_search_radius)),
            "transformSearchLimit": max(0, int(transform_search_limit)),
            "transformSyntheticTranslationRadius": max(0, int(transform_synthetic_translation_radius)),
            "transformSyntheticRotationRadius": max(0, int(transform_synthetic_rotation_radius)),
            "transformPreflightCycles": max(0, int(transform_preflight_cycles)),
            "transformPromotionLimit": max(0, int(transform_promotion_limit)),
            "componentTimingSearchLimit": max(0, int(component_timing_search_limit)),
            "componentTimingSourceLimit": max(0, int(component_timing_source_limit)),
            "componentTimingRadius": max(0, int(component_timing_radius)),
            "componentTimingCutpointLimit": max(0, int(component_timing_cutpoint_limit)),
            "componentTimingPreflightCycles": max(0, int(component_timing_preflight_cycles)),
            "componentTimingPromotionLimit": max(0, int(component_timing_promotion_limit)),
            "componentTimingOracleEnabled": component_timing_oracle_validator is not None,
            "componentTimingOracleWorkers": max(1, min(10, int(component_timing_oracle_workers))),
            "componentTimingGlobalResultLimit": max(0, int(component_timing_global_result_limit)),
            "chemistryTransplantVariantLimit": max(0, int(chemistry_transplant_variant_limit)),
            "chemistryTransplantSourceLimit": max(0, int(chemistry_transplant_source_limit)),
            "chemistryTransplantResultLimit": max(0, int(chemistry_transplant_result_limit)),
            "chemistryTransplantMaxGrabCycles": max(1, int(chemistry_transplant_max_grab_cycles)),
            "chemistryTransplantLocalCycles": max(1, int(chemistry_transplant_local_cycles)),
            "chemistryTransplantOraclePromotionLimit": max(
                0,
                int(chemistry_transplant_oracle_promotion_limit),
            ),
            "orderedChemistryVariantLimit": max(0, int(ordered_chemistry_variant_limit)),
            "orderedChemistrySourceLimit": max(0, int(ordered_chemistry_source_limit)),
            "orderedChemistryCalcificationVariantLimit": max(
                0,
                int(ordered_chemistry_calcification_variant_limit),
            ),
            "orderedChemistryResultLimit": max(0, int(ordered_chemistry_result_limit)),
            "orderedChemistryLocalCycles": max(1, int(ordered_chemistry_local_cycles)),
            "orderedChemistryPersistenceFrames": max(
                1,
                int(ordered_chemistry_persistence_frames),
            ),
            "orderedChemistryPrismOraclePromotionLimit": max(
                0,
                int(ordered_chemistry_prism_oracle_promotion_limit),
            ),
            "orderedChemistryCalcificationOraclePromotionLimit": max(
                0,
                int(ordered_chemistry_calcification_oracle_promotion_limit),
            ),
            "singleProductSourceLimit": max(0, int(single_product_source_limit)),
            "singleProductResultLimit": max(0, int(single_product_result_limit)),
            "singleProductLocalCycles": max(1, int(single_product_local_cycles)),
            "singleProductOraclePromotionLimit": max(
                0,
                int(single_product_oracle_promotion_limit),
            ),
            "singleProductOracleEnabled": single_product_oracle_validator is not None,
            "repeatingProductSourceLimit": max(
                0,
                int(repeating_product_source_limit),
            ),
            "repeatingProductResultLimit": max(
                0,
                int(repeating_product_result_limit),
            ),
            "repeatingProductLocalCycles": max(
                1,
                int(repeating_product_local_cycles),
            ),
            "repeatingProductOraclePromotionLimit": max(
                0,
                int(repeating_product_oracle_promotion_limit),
            ),
            "fullProductOracleEnabled": full_product_oracle_validator is not None,
            "candidateKinds": dict(sorted(Counter(str(item.get("candidateKind") or "unknown") for item in assemblies).items())),
            "minEngineValidatedSolutions": max(0, int(min_engine_validated_solutions)),
        },
        "componentTimingOraclePortfolio": global_component_portfolio,
        "chemistryTransplantSearch": chemistry_transplant_search,
        "orderedChemistrySearch": ordered_chemistry_search,
        "productCompletionSearch": product_completion_search,
        "repeatingProductSearch": repeating_product_search,
        "candidates": results,
    }
