from __future__ import annotations

from copy import deepcopy
from typing import Any

from .assembly import rank_fragment_assemblies
from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .chemistry_composition import manufacturing_requirements, rank_chains_for_manufacturing_plan
from .layout import materialize_candidate_layout
from .manufacturing_extensions import build_manufacturing_plan
from .scheduling import materialize_candidate_schedule, synchronize_layout_programs
from .solver import (
    GeneratedSolutionError,
    SolveResult,
    UnsupportedPuzzleError,
    solve_puzzle,
    validate_generated_solution,
)


def _composition_assemblies(
    plan,
    flow_index: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    requirements = manufacturing_requirements(plan)
    if requirements["requiresConvergence"]:
        return [
            {**item, "candidateKind": "convergent-assembly"}
            for item in rank_fragment_assemblies(
                plan,
                flow_index,
                limit=max(1, int(limit)),
            )
        ]
    return [
        {**item, "candidateKind": "linear-chain"}
        for item in rank_chains_for_manufacturing_plan(
            plan,
            flow_index,
            fragment_index=fragment_index,
            limit=max(1, int(limit)),
            min_engine_validated_solutions=1,
        )
    ]


def solve_puzzle_from_knowledge(
    puzzle: dict[str, Any],
    flow_index: dict[str, Any],
    fragment_index: dict[str, Any] | None = None,
    *,
    limit: int = 10,
) -> SolveResult:
    """Compose and validate a puzzle solution from learned fragment evidence.

    This intentionally uses only the target puzzle plus a reusable fragment-flow
    knowledge index. Source solution bytes are not read by this stage.
    """

    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        raise UnsupportedPuzzleError(plan.reason or "Puzzle is not supported by the manufacturing planner")

    fragments = fragment_index or flow_index
    assemblies = _composition_assemblies(
        plan,
        flow_index,
        fragments,
        limit=limit,
    )
    diagnostics: list[dict[str, Any]] = []

    for rank, assembly in enumerate(assemblies, start=1):
        record: dict[str, Any] = {
            "rank": rank,
            "candidateKind": assembly.get("candidateKind"),
            "assemblyScore": assembly.get("score"),
        }
        try:
            layout = materialize_candidate_layout(assembly, fragments)
            record["layoutSummary"] = deepcopy(layout.get("summary", {}))
            schedule = materialize_candidate_schedule(assembly)
            record["scheduleSummary"] = deepcopy(schedule.get("summary", {}))
            synchronized = synchronize_layout_programs(layout, schedule)
            record["synchronizedSummary"] = deepcopy(synchronized.get("summary", {}))
            solution = build_candidate_solution(
                puzzle,
                plan,
                assembly,
                synchronized,
                name=f"Opus Solver - autonomous knowledge candidate {rank}",
            )
            solution.setdefault("source", {})["generator"] = "opus_solver/autonomous-knowledge-composition-v1"
            roundtrip = serialize_candidate_roundtrip(solution)
            record["serialization"] = deepcopy(roundtrip["diagnostics"])
            validation = validate_generated_solution(puzzle, roundtrip["parsed"])
            record["validation"] = deepcopy(validation)
            if not validation.get("complete"):
                diagnostics.append(record)
                continue

            resolved_validation = {
                **validation,
                "solverRoute": "knowledge-fragment-composition-v1",
                "compositionCandidateRank": rank,
                "compositionAssemblyScore": assembly.get("score"),
                "compositionCandidateKind": assembly.get("candidateKind"),
                "knowledgeTransitionCount": len(flow_index.get("transitions", [])),
                "knowledgeFragmentCount": len(fragments.get("fragments", [])),
                "knowledgeConvergenceCount": len(flow_index.get("convergenceMotifs", [])),
            }
            return SolveResult(
                puzzle_name=str(puzzle.get("name") or puzzle.get("id") or "generated-puzzle"),
                strategy=f"{plan.strategy}+knowledge-composition-v1",
                plan=plan,
                solution=roundtrip["parsed"],
                validation=resolved_validation,
            )
        except Exception as error:
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            diagnostics.append(record)

    raise GeneratedSolutionError(
        "Knowledge composition did not produce a complete solution: "
        f"tested={len(assemblies)} diagnostics={diagnostics[:3]}"
    )


def solve_puzzle_auto(
    puzzle: dict[str, Any],
    *,
    flow_index: dict[str, Any] | None = None,
    fragment_index: dict[str, Any] | None = None,
    composition_limit: int = 10,
) -> SolveResult:
    """Use the direct generator first, then learned composition when available."""

    try:
        direct = solve_puzzle(puzzle)
    except (UnsupportedPuzzleError, GeneratedSolutionError):
        if flow_index is None:
            raise
    else:
        direct.validation = {
            **direct.validation,
            "solverRoute": "direct-generator-v1",
        }
        return direct

    return solve_puzzle_from_knowledge(
        puzzle,
        flow_index,
        fragment_index,
        limit=composition_limit,
    )
