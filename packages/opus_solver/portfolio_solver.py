from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable

from .autonomous import solve_puzzle_auto as solve_puzzle_auto_legacy
from .autonomous import solve_puzzle_from_knowledge
from .solver import GeneratedSolutionError, SolveResult, UnsupportedPuzzleError, solve_puzzle


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

    Historically `solve_puzzle_auto` returned immediately when a handcrafted
    direct generator succeeded.  That is correct for feasibility but wrong for
    optimization: a learned architecture or a newly composed mechanism may be
    better under the requested metric.  When reusable flow knowledge is
    available, this adapter places the direct result into the same bounded
    portfolio instead of giving it an implicit priority.
    """

    architecture_candidates = list(architecture_candidates)
    direct: SolveResult | None = None
    direct_error: Exception | None = None
    try:
        direct = solve_puzzle(puzzle)
    except (UnsupportedPuzzleError, GeneratedSolutionError) as error:
        direct_error = error

    # Without learned flow knowledge there is no second machine family to
    # compare. Preserve the existing direct/legacy behavior exactly.
    if flow_index is None:
        if direct is not None:
            return solve_puzzle_auto_legacy(
                puzzle,
                flow_index=None,
                fragment_index=fragment_index,
                composition_limit=composition_limit,
                objective=objective,
                oracle_validator=oracle_validator,
                oracle_name=oracle_name,
                architecture_candidates=architecture_candidates,
            )
        if direct_error is not None:
            raise direct_error
        raise UnsupportedPuzzleError("No direct solution or learned flow knowledge is available")

    seeds = list(architecture_candidates)
    if direct is not None:
        seeds.insert(0, _direct_seed(direct))

    result = solve_puzzle_from_knowledge(
        puzzle,
        flow_index,
        fragment_index,
        limit=composition_limit,
        objective=objective,
        oracle_validator=oracle_validator,
        oracle_name=oracle_name,
        architecture_candidates=seeds,
    )

    validation = result.validation
    validation["directGeneratorAvailable"] = direct is not None
    validation["directGeneratorStrategy"] = direct.strategy if direct is not None else None
    validation["portfolioArchitectureCandidateCount"] = len(seeds)
    validation["learnedArchitectureCandidateCount"] = len(architecture_candidates)

    if validation.get("selectedCandidateId") == "direct-generator-v1":
        validation["solverRoute"] = "direct-generator-v1"
        validation["selectedCandidateSource"] = "direct-generator"
        validation["selectedCandidateKind"] = "direct-complete-architecture"

    return result


# New canonical entry point.  Keep the explicit portfolio name as well so
# callers can opt into the semantics without relying on an alias.
solve_puzzle_auto = solve_puzzle_portfolio
