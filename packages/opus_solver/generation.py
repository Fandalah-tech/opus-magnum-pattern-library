from __future__ import annotations

from typing import Any

from .assembly import rank_fragment_assemblies
from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .layout import materialize_assembly_layout
from .manufacturing import build_manufacturing_plan
from .scheduling import materialize_assembly_schedule, synchronize_layout_programs
from .solver import validate_generated_solution
from .variants import enumerate_empirical_assembly_variants


def generate_composed_candidates(
    puzzle: dict[str, Any],
    flow_index: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    limit: int = 25,
    assembly_limit: int = 10,
    variants_per_assembly: int = 6,
    validate_engine: bool = True,
    stop_on_complete: bool = False,
) -> dict[str, Any]:
    """Run the database-driven assembly generation and empirical variant search."""
    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        return {
            "schemaVersion": "0.2.0",
            "plan": plan.to_dict(),
            "summary": {
                "supported": False,
                "assemblyCandidateCount": 0,
                "expandedVariantCount": 0,
                "serializableCount": 0,
                "engineCompleteCount": 0,
            },
            "candidates": [],
        }

    assemblies = rank_fragment_assemblies(plan, flow_index, limit=max(1, int(assembly_limit)))
    results = []
    serializable_count = 0
    engine_complete_count = 0
    expanded_variant_count = 0

    should_stop = False
    for assembly_rank, assembly in enumerate(assemblies, start=1):
        variants = enumerate_empirical_assembly_variants(
            assembly,
            max_variants=max(1, int(variants_per_assembly)),
        )
        expanded_variant_count += len(variants)
        for variant_rank, variant in enumerate(variants, start=1):
            if len(results) >= max(1, int(limit)):
                should_stop = True
                break
            record: dict[str, Any] = {
                "rank": len(results) + 1,
                "assemblyRank": assembly_rank,
                "variantRank": variant_rank,
                "assemblyScore": assembly.get("score"),
                "variant": variant.get("variant", {}),
                "assembly": variant,
            }
            try:
                layout = materialize_assembly_layout(variant, fragment_index)
                record["layoutSummary"] = layout.get("summary", {})
                schedule = materialize_assembly_schedule(variant)
                record["scheduleSummary"] = schedule.get("summary", {})
                synchronized = synchronize_layout_programs(layout, schedule)
                record["synchronizedSummary"] = synchronized.get("summary", {})

                solution = build_candidate_solution(puzzle, plan, variant, synchronized)
                roundtrip = serialize_candidate_roundtrip(solution)
                record["serialization"] = roundtrip["diagnostics"]
                record["solution"] = solution
                serializable_count += int(bool(roundtrip["diagnostics"].get("roundTripClean")))

                if validate_engine:
                    try:
                        validation = validate_generated_solution(puzzle, roundtrip["parsed"])
                        record["engineValidation"] = validation
                        if validation.get("complete"):
                            engine_complete_count += 1
                            if stop_on_complete:
                                should_stop = True
                    except Exception as exc:
                        record["engineValidation"] = {
                            "complete": False,
                            "errorType": type(exc).__name__,
                            "message": str(exc),
                        }
            except Exception as exc:
                record["generationError"] = {"errorType": type(exc).__name__, "message": str(exc)}
            results.append(record)
            if should_stop:
                break
        if should_stop:
            break

    return {
        "schemaVersion": "0.2.0",
        "plan": plan.to_dict(),
        "summary": {
            "supported": True,
            "assemblyCandidateCount": len(assemblies),
            "expandedVariantCount": expanded_variant_count,
            "evaluatedCandidateCount": len(results),
            "serializableCount": serializable_count,
            "engineCompleteCount": engine_complete_count,
            "hasCompleteSolution": engine_complete_count > 0,
            "stoppedOnComplete": bool(stop_on_complete and engine_complete_count > 0),
        },
        "candidates": results,
    }
