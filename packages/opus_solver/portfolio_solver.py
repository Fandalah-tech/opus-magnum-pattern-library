from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable

from .autonomous import solve_puzzle_auto as solve_puzzle_auto_legacy
from .autonomous import solve_puzzle_from_knowledge
from .solver import GeneratedSolutionError, SolveResult, UnsupportedPuzzleError, solve_puzzle


_EMPTY_KNOWLEDGE_INDEX = {
    "schemaVersion": "0.0.0",
    "transitions": [],
    "fragments": [],
    "convergenceMotifs": [],
}


def _direct_seed(result: SolveResult) -> dict[str, Any]:
    """Represent a direct-generator solve as one complete portfolio architecture."""

    return {
        "id": "direct-generator-v1",
        "solution": deepcopy(result.solution),
        "focusObjectives": [],
        "referenceMetrics": deepcopy(result.solution.get("metrics") or {}),
        "provenance": {
            "kind": "direct-generator",
            "strategy": result.strategy,
        },
    }


def solve_puzzle_portfolio(
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
    """Optimize across direct, learned-complete and recomposed machine families.

    A successful direct generator is a feasibility proof, not an optimization
    winner. Whenever either learned complete architectures or fragment-flow
    knowledge exists, the direct solution is inserted into the same bounded
    portfolio and must win under the requested objective like every other
    machine family.
    """

    architecture_candidates = list(architecture_candidates)
    direct: SolveResult | None = None
    direct_error: Exception | None = None
    try:
        direct = solve_puzzle(puzzle)
    except (UnsupportedPuzzleError, GeneratedSolutionError) as error:
        direct_error = error

    has_learned_architectures = bool(architecture_candidates)
    has_fragment_knowledge = flow_index is not None

    # Preserve the historical direct-only path only when literally no learned
    # alternative exists. This also avoids introducing an empty portfolio layer
    # into the simplest supported puzzles.
    if not has_fragment_knowledge and not has_learned_architectures:
        if direct is not None:
            return solve_puzzle_auto_legacy(
                puzzle,
                flow_index=None,
                fragment_index=fragment_index,
                composition_limit=composition_limit,
                objective=objective,
                oracle_validator=oracle_validator,
                oracle_name=oracle_name,
                architecture_candidates=(),
            )
        if direct_error is not None:
            raise direct_error
        raise UnsupportedPuzzleError("No direct solution or learned knowledge is available")

    resolved_flow_index = flow_index or deepcopy(_EMPTY_KNOWLEDGE_INDEX)
    resolved_fragment_index = fragment_index or resolved_flow_index

    seeds = list(architecture_candidates)
    if direct is not None:
        seeds.insert(0, _direct_seed(direct))

    result = solve_puzzle_from_knowledge(
        puzzle,
        resolved_flow_index,
        resolved_fragment_index,
        limit=composition_limit,
        objective=objective,
        oracle_validator=oracle_validator,
        oracle_name=oracle_name,
        architecture_candidates=seeds,
    )

    validation = result.validation
    validation["directGeneratorAvailable"] = direct is not None
    validation["directGeneratorStrategy"] = direct.strategy if direct is not None else None
    validation["fragmentKnowledgeAvailable"] = has_fragment_knowledge
    validation["portfolioArchitectureCandidateCount"] = len(seeds)
    validation["learnedArchitectureCandidateCount"] = len(architecture_candidates)

    if validation.get("selectedCandidateId") == "direct-generator-v1":
        validation["solverRoute"] = "direct-generator-v1"
        validation["selectedCandidateSource"] = "direct-generator"
        validation["selectedCandidateKind"] = "direct-complete-architecture"
        if direct is not None:
            result.strategy = direct.strategy

    return result


# Canonical optimization entry point.
solve_puzzle_auto = solve_puzzle_portfolio
