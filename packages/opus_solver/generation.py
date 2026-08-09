from __future__ import annotations

from typing import Any

from .assembly import rank_fragment_assemblies
from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .layout import materialize_assembly_layout
from .manufacturing import build_manufacturing_plan
from .scheduling import materialize_assembly_schedule, synchronize_layout_programs
from .solver import validate_generated_solution


def generate_composed_candidates(
    puzzle: dict[str, Any],
    flow_index: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    limit: int = 10,
    validate_engine: bool = True,
) -> dict[str, Any]:
    """Run the first complete database-driven assembly generation pipeline.

    Candidate failures are retained as diagnostics so geometry/timing variants
    can later be searched instead of aborting the whole generation pass.
    """
    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        return {
            "schemaVersion": "0.1.0",
            "plan": plan.to_dict(),
            "summary": {"supported": False, "assemblyCandidateCount": 0, "serializableCount": 0, "engineCompleteCount": 0},
            "candidates": [],
        }

    assemblies = rank_fragment_assemblies(plan, flow_index, limit=max(1, int(limit)))
    results = []
    serializable_count = 0
    engine_complete_count = 0

    for index, assembly in enumerate(assemblies):
        record: dict[str, Any] = {
            "rank": index + 1,
            "assemblyScore": assembly.get("score"),
            "assembly": assembly,
        }
        try:
            layout = materialize_assembly_layout(assembly, fragment_index)
            record["layoutSummary"] = layout.get("summary", {})
            schedule = materialize_assembly_schedule(assembly)
            record["scheduleSummary"] = schedule.get("summary", {})
            synchronized = synchronize_layout_programs(layout, schedule)
            record["synchronizedSummary"] = synchronized.get("summary", {})

            solution = build_candidate_solution(puzzle, plan, assembly, synchronized)
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
                except Exception as exc:  # validation diagnostics must not abort candidate search
                    record["engineValidation"] = {
                        "complete": False,
                        "errorType": type(exc).__name__,
                        "message": str(exc),
                    }
        except Exception as exc:
            record["generationError"] = {"errorType": type(exc).__name__, "message": str(exc)}
        results.append(record)

    return {
        "schemaVersion": "0.1.0",
        "plan": plan.to_dict(),
        "summary": {
            "supported": True,
            "assemblyCandidateCount": len(assemblies),
            "serializableCount": serializable_count,
            "engineCompleteCount": engine_complete_count,
            "hasCompleteSolution": engine_complete_count > 0,
        },
        "candidates": results,
    }
