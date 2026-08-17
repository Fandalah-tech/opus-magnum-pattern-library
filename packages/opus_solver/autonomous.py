from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Callable, Iterable

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator

from .assembly import rank_fragment_assemblies
from .candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from .chemistry_composition import manufacturing_requirements, rank_chains_for_manufacturing_plan
from .layout import materialize_candidate_layout
from .manufacturing_extensions import build_manufacturing_plan
from .objective_portfolio import OBJECTIVES, objective_key
from .scheduling import materialize_candidate_schedule, synchronize_layout_programs
from .solver import (
    GeneratedSolutionError,
    SolveResult,
    UnsupportedPuzzleError,
    solve_puzzle,
    validate_generated_solution,
)

KNOWLEDGE_OBJECTIVES = ("balanced", *OBJECTIVES)
LOCAL_OBJECTIVES = ("balanced", "cycles", "instructions")
STANDARD_PRODUCT_TARGET = 6


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


def _instruction_count(solution: dict[str, Any]) -> int:
    """Count physical instruction cells after OMSim-compatible tape decoding."""
    timeline = build_program_timeline(solution)
    return sum(
        int(arm.get("expandedInstructionCount") or 0)
        for arm in timeline.get("arms", [])
    )


def _local_completion_cycle(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    validation: dict[str, Any],
) -> tuple[int | None, dict[str, int]]:
    """Return the zero-based frame where every standard product reaches six."""

    required_products = {
        int(part.get("which") or 0)
        for part in solution.get("parts", [])
        if part.get("type") == "out-std"
    }
    if not required_products:
        return None, {}

    horizon = max(
        1,
        int(validation.get("requestedCycles") or validation.get("completedCycles") or 1),
    )
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    counts: Counter[int] = Counter()
    completed: dict[int, int] = {}
    for frame in replay.get("frames", []):
        cycle = int(frame.get("cycle") or 0)
        for event in frame.get("events", []):
            if event.get("kind") != "product-delivered":
                continue
            product_index = int(event.get("productIndex") or 0)
            if product_index not in required_products:
                continue
            counts[product_index] += 1
            if counts[product_index] >= STANDARD_PRODUCT_TARGET and product_index not in completed:
                completed[product_index] = cycle
        if required_products.issubset(completed):
            return max(completed.values()), {
                str(key): value for key, value in sorted(completed.items())
            }
    return None, {str(key): value for key, value in sorted(completed.items())}


def _local_candidate_metrics(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    completion_cycle, completion_by_product = _local_completion_cycle(
        puzzle,
        solution,
        validation,
    )
    fallback_cycle = int(
        validation.get("completedCycles")
        or validation.get("requestedCycles")
        or 10**9
    )
    metric_cycles = completion_cycle + 1 if completion_cycle is not None else fallback_cycle
    return {
        "cycles": metric_cycles,
        "completionCycle": completion_cycle,
        "completionByProduct": completion_by_product,
        "instructions": _instruction_count(solution),
        "parts": len(solution.get("parts", [])),
    }


def _oracle_metrics(validation: dict[str, Any]) -> dict[str, int]:
    result = {
        key: int(value)
        for key, value in (validation.get("metrics") or {}).items()
        if key in {"cost", "cycles", "area", "instructions"}
        and isinstance(value, int)
    }
    if isinstance(validation.get("rate"), int):
        result["rate"] = int(validation["rate"])
    return result


def _candidate_objective_key(
    record: dict[str, Any],
    objective: str,
    *,
    use_oracle: bool,
) -> tuple[Any, ...]:
    rank = int(record.get("rank") or 10**9)
    if use_oracle and objective in OBJECTIVES:
        return (*objective_key(objective, record["oracleMetrics"]), rank)

    metrics = record["localMetrics"]
    cycles = int(metrics["cycles"])
    instructions = int(metrics["instructions"])
    parts = int(metrics["parts"])
    assembly_score = float(record.get("assemblyScore") or 0.0)
    if objective == "cycles":
        return cycles, instructions, parts, -assembly_score, rank
    if objective == "instructions":
        return instructions, cycles, parts, -assembly_score, rank
    if objective == "balanced":
        source_bias = 0 if record.get("candidateSource") == "fragment-composition" else 1
        return source_bias, -assembly_score, cycles, instructions, parts, rank
    raise ValueError(
        f"Objective {objective!r} requires an authoritative oracle; local objectives are {LOCAL_OBJECTIVES}"
    )


def _validate_objective(
    objective: str,
    *,
    oracle_validator: Callable[[dict[str, Any]], dict[str, Any]] | None,
) -> None:
    if objective not in KNOWLEDGE_OBJECTIVES:
        raise ValueError(
            f"Unknown autonomous objective {objective!r}; expected one of {KNOWLEDGE_OBJECTIVES}"
        )
    if oracle_validator is None and objective not in LOCAL_OBJECTIVES:
        raise ValueError(
            f"Objective {objective!r} requires an authoritative oracle; without one use one of {LOCAL_OBJECTIVES}"
        )


def _score_complete_candidates_with_oracle(
    records: list[dict[str, Any]],
    oracle_validator: Callable[[dict[str, Any]], dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    valid: list[dict[str, Any]] = []
    scored = 0
    for record in records:
        try:
            oracle_validation = oracle_validator(record["solution"])
        except Exception as error:
            oracle_validation = {
                "valid": False,
                "metrics": {},
                "rate": None,
                "issues": [{
                    "code": "ORACLE_EXCEPTION",
                    "message": f"{type(error).__name__}: {error}",
                }],
            }
        scored += 1
        record["oracleValidation"] = deepcopy(oracle_validation)
        record["oracleMetrics"] = _oracle_metrics(oracle_validation)
        if oracle_validation.get("valid"):
            valid.append(record)
    return valid, scored


def _learned_architecture_records(
    puzzle: dict[str, Any],
    candidates: Iterable[dict[str, Any]],
    *,
    starting_rank: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    complete: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for offset, candidate in enumerate(candidates):
        rank = starting_rank + offset
        candidate_id = str(candidate.get("id") or f"learned-architecture-{offset + 1}")
        record: dict[str, Any] = {
            "rank": rank,
            "candidateId": candidate_id,
            "candidateSource": "learned-architecture-bank",
            "candidateKind": "learned-complete-architecture",
            "assemblyScore": None,
            "focusObjectives": list(candidate.get("focusObjectives") or ()),
            "referenceMetrics": deepcopy(candidate.get("referenceMetrics") or {}),
            "provenance": deepcopy(candidate.get("provenance") or {}),
        }
        try:
            solution = deepcopy(candidate["solution"])
            solution.setdefault("source", {})["generator"] = "opus_solver/learned-architecture-bank-v1"
            solution["name"] = f"Opus Solver - learned architecture {candidate_id}"
            roundtrip = serialize_candidate_roundtrip(solution)
            record["serialization"] = deepcopy(roundtrip["diagnostics"])
            validation = validate_generated_solution(puzzle, roundtrip["parsed"])
            record["validation"] = deepcopy(validation)
            if not validation.get("complete"):
                diagnostics.append(record)
                continue
            record["solution"] = roundtrip["parsed"]
            record["localMetrics"] = _local_candidate_metrics(
                puzzle,
                roundtrip["parsed"],
                validation,
            )
            complete.append(record)
        except Exception as error:
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            diagnostics.append(record)
    return complete, diagnostics


def solve_puzzle_from_knowledge(
    puzzle: dict[str, Any],
    flow_index: dict[str, Any],
    fragment_index: dict[str, Any] | None = None,
    *,
    limit: int = 10,
    objective: str = "balanced",
    oracle_validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    oracle_name: str = "oracle",
    architecture_candidates: Iterable[dict[str, Any]] = (),
) -> SolveResult:
    """Rank learned complete architectures and fresh fragment compositions together."""

    _validate_objective(objective, oracle_validator=oracle_validator)

    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        raise UnsupportedPuzzleError(plan.reason or "Puzzle is not supported by the manufacturing planner")

    fragments = fragment_index or flow_index
    architecture_candidates = list(architecture_candidates)
    architecture_complete, architecture_diagnostics = _learned_architecture_records(
        puzzle,
        architecture_candidates,
        starting_rank=1,
    )

    assemblies = _composition_assemblies(
        plan,
        flow_index,
        fragments,
        limit=limit,
    )
    diagnostics: list[dict[str, Any]] = [*architecture_diagnostics]
    complete: list[dict[str, Any]] = [*architecture_complete]
    first_assembly_rank = len(architecture_candidates) + 1

    for offset, assembly in enumerate(assemblies):
        rank = first_assembly_rank + offset
        record: dict[str, Any] = {
            "rank": rank,
            "candidateId": f"fragment-composition-{offset + 1}",
            "candidateSource": "fragment-composition",
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

            record["solution"] = roundtrip["parsed"]
            record["localMetrics"] = _local_candidate_metrics(
                puzzle,
                roundtrip["parsed"],
                validation,
            )
            complete.append(record)
        except Exception as error:
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            diagnostics.append(record)

    if not complete:
        raise GeneratedSolutionError(
            "Knowledge portfolio did not produce a complete solution: "
            f"tested={len(architecture_candidates) + len(assemblies)} diagnostics={diagnostics[:3]}"
        )

    oracle_scored_count = 0
    oracle_valid_count = 0
    selectable = complete
    use_oracle = oracle_validator is not None and objective in OBJECTIVES
    if use_oracle:
        selectable, oracle_scored_count = _score_complete_candidates_with_oracle(
            complete,
            oracle_validator,
        )
        oracle_valid_count = len(selectable)
        if not selectable:
            raise GeneratedSolutionError(
                f"{oracle_name} rejected all {oracle_scored_count} locally complete candidates"
            )

    selected = min(
        selectable,
        key=lambda record: _candidate_objective_key(
            record,
            objective,
            use_oracle=use_oracle,
        ),
    )
    validation = selected["validation"]
    selected_source = str(selected.get("candidateSource") or "fragment-composition")
    solver_route = (
        "knowledge-architecture-bank-v1"
        if selected_source == "learned-architecture-bank"
        else "knowledge-fragment-composition-v1"
    )
    resolved_validation = {
        **validation,
        "solverRoute": solver_route,
        "optimizationObjective": objective,
        "optimizationMetricSource": oracle_name if use_oracle else "opus-engine-local",
        "compositionCandidateRank": selected["rank"],
        "compositionAssemblyScore": selected.get("assemblyScore"),
        "compositionCandidateKind": selected.get("candidateKind"),
        "compositionCompleteCandidateCount": len(complete),
        "compositionTestedCandidateCount": len(architecture_candidates) + len(assemblies),
        "architectureSeedCandidateCount": len(architecture_candidates),
        "architectureSeedCompleteCount": len(architecture_complete),
        "fragmentAssemblyCandidateCount": len(assemblies),
        "selectedCandidateId": selected.get("candidateId"),
        "selectedCandidateSource": selected_source,
        "selectedFocusObjectives": list(selected.get("focusObjectives") or ()),
        "selectedReferenceMetrics": deepcopy(selected.get("referenceMetrics") or {}),
        "localCandidateMetrics": selected["localMetrics"],
        "oracleScoredCandidateCount": oracle_scored_count,
        "oracleValidCandidateCount": oracle_valid_count,
        "knowledgeTransitionCount": len(flow_index.get("transitions", [])),
        "knowledgeFragmentCount": len(fragments.get("fragments", [])),
        "knowledgeConvergenceCount": len(flow_index.get("convergenceMotifs", [])),
    }
    if use_oracle:
        resolved_validation["oracleMetrics"] = selected["oracleMetrics"]
        resolved_validation["oracleValidation"] = selected["oracleValidation"]
        resolved_validation["objectiveKey"] = list(
            objective_key(objective, selected["oracleMetrics"])
        )

    return SolveResult(
        puzzle_name=str(puzzle.get("name") or puzzle.get("id") or "generated-puzzle"),
        strategy=f"{plan.strategy}+knowledge-portfolio-v1",
        plan=plan,
        solution=selected["solution"],
        validation=resolved_validation,
    )


def solve_puzzle_auto(
    puzzle: dict[str, Any],
    *,
    flow_index: dict[str, Any] | None = None,
    fragment_index: dict[str, Any] | None = None,
    composition_limit: int = 10,
    objective: str = "balanced",
    oracle_validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    oracle_name: str = "oracle",
    architecture_candidates: Iterable[dict[str, Any]] = (),
) -> SolveResult:
    """Use the direct generator first, then the multi-level learned portfolio."""

    _validate_objective(objective, oracle_validator=oracle_validator)

    try:
        direct = solve_puzzle(puzzle)
    except (UnsupportedPuzzleError, GeneratedSolutionError):
        if flow_index is None:
            raise
    else:
        local_metrics = _local_candidate_metrics(
            puzzle,
            direct.solution,
            direct.validation,
        )
        validation = {
            **direct.validation,
            "solverRoute": "direct-generator-v1",
            "optimizationObjective": objective,
            "optimizationMetricSource": "opus-engine-local",
            "localCandidateMetrics": local_metrics,
        }
        if oracle_validator is not None and objective in OBJECTIVES:
            oracle_validation = oracle_validator(direct.solution)
            if not oracle_validation.get("valid"):
                raise GeneratedSolutionError(
                    f"{oracle_name} rejected the direct-generator solution"
                )
            metrics = _oracle_metrics(oracle_validation)
            validation.update({
                "optimizationMetricSource": oracle_name,
                "oracleScoredCandidateCount": 1,
                "oracleValidCandidateCount": 1,
                "oracleMetrics": metrics,
                "oracleValidation": deepcopy(oracle_validation),
                "objectiveKey": list(objective_key(objective, metrics)),
            })
        direct.validation = validation
        return direct

    return solve_puzzle_from_knowledge(
        puzzle,
        flow_index,
        fragment_index,
        limit=composition_limit,
        objective=objective,
        oracle_validator=oracle_validator,
        oracle_name=oracle_name,
        architecture_candidates=architecture_candidates,
    )
