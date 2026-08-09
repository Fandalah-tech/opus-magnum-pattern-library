from __future__ import annotations

from collections import Counter
from typing import Any

from .assembly import rank_fragment_assemblies
from .candidate_search import search_temporal_candidates
from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .geometry_search import search_geometric_candidates
from .layout import materialize_assembly_layout
from .manufacturing import build_manufacturing_plan
from .repair_policy import recommend_repair_order
from .scheduling import materialize_assembly_schedule, synchronize_layout_programs
from .solver import validate_generated_solution


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
            },
            "candidates": [],
        }

    assemblies = rank_fragment_assemblies(plan, flow_index, limit=max(1, int(limit)))
    results = []
    serializable_count = 0
    engine_complete_count = 0
    temporal_variant_count = 0
    temporal_complete_count = 0
    geometric_variant_count = 0
    geometric_complete_count = 0
    failure_modes: Counter[str] = Counter()
    repair_routes: Counter[str] = Counter()

    for index, assembly in enumerate(assemblies):
        record: dict[str, Any] = {
            "rank": index + 1,
            "assemblyScore": assembly.get("score"),
            "assembly": assembly,
        }
        try:
            layout = materialize_assembly_layout(assembly, fragment_index)
            layout_summary = layout.get("summary", {})
            record["layoutSummary"] = layout_summary
            schedule = materialize_assembly_schedule(assembly)
            record["scheduleSummary"] = schedule.get("summary", {})
            synchronized = synchronize_layout_programs(layout, schedule)
            record["synchronizedSummary"] = synchronized.get("summary", {})

            solution = build_candidate_solution(puzzle, plan, assembly, synchronized)
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
                    )
                    record["geometricSearch"] = search
                    geometric_variant_count += int(search.get("summary", {}).get("searchedVariantCount") or 0)
                    geometric_complete_count += int(search.get("summary", {}).get("completeVariantCount") or 0)
                    repaired = bool(search.get("summary", {}).get("hasCompleteSolution"))
                if repaired:
                    record["repairSucceededWith"] = repair
                    break
        except Exception as exc:
            record["generationError"] = {"errorType": type(exc).__name__, "message": str(exc)}
            failure_modes["generation-error"] += 1
        results.append(record)

    return {
        "schemaVersion": "0.4.0",
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
            "hasCompleteSolution": engine_complete_count > 0 or temporal_complete_count > 0 or geometric_complete_count > 0,
            "failureModes": dict(sorted(failure_modes.items())),
            "repairRoutes": dict(sorted(repair_routes.items())),
            "temporalSearchRadius": max(0, int(temporal_search_radius)),
            "transformSearchLimit": max(0, int(transform_search_limit)),
        },
        "candidates": results,
    }
