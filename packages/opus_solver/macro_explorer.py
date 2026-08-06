from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Iterable

from .mechanical_macros import MechanicalMacro, enumerate_macro_successors
from .state import canonical_state_key

ScoreFunction = Callable[[Any], int]
GoalPredicate = Callable[[Any], bool]
StatePredicate = Callable[[Any], bool]


@dataclass(slots=True)
class MacroExplorationResult:
    found: bool
    macros: list[str]
    actions: list[dict[str, str]]
    simulator: Any | None
    visited_states: int
    expanded_states: int
    depth: int | None
    stopped_reason: str
    best_score: int


def explore_simulator_macro_beam(
    initial_simulator: Any,
    macros: Iterable[MechanicalMacro],
    goal: GoalPredicate,
    score: ScoreFunction,
    *,
    max_depth: int = 12,
    beam_width: int = 500,
    max_states: int = 100_000,
    time_limit_seconds: float | None = None,
    state_filter: StatePredicate | None = None,
) -> MacroExplorationResult:
    """Search complete mechanical transformations instead of individual cycles.

    Each edge is an atomically validated macro. This lets the structural search
    cross long score plateaus such as a confined rotation or temporary nucleus
    storage without requiring every intermediate cycle to survive beam pruning.

    ``state_filter`` can reject mechanically valid but strategically inadmissible
    terminal states, for example states that spawned more atoms than the target
    structure can contain. The filter is applied before canonical-state
    deduplication so rejected clutter never consumes the visited-state budget.
    """
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if beam_width < 1 or max_states < 1:
        raise ValueError("beam_width and max_states must be positive")
    if time_limit_seconds is not None and time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be positive")
    if state_filter is not None and not state_filter(initial_simulator):
        raise ValueError("initial_simulator does not satisfy state_filter")

    macro_set = tuple(macros)
    started = monotonic()
    root_score = score(initial_simulator)
    if goal(initial_simulator):
        return MacroExplorationResult(True, [], [], initial_simulator, 1, 0, 0, "goal", root_score)

    frontier: list[tuple[int, int, Any, list[str], list[dict[str, str]]]] = [
        (root_score, 0, initial_simulator, [], [])
    ]
    visited = {canonical_state_key(initial_simulator)}
    expanded = 0
    best_score = root_score
    best_simulator = initial_simulator
    best_macros: list[str] = []
    best_actions: list[dict[str, str]] = []

    def timed_out() -> bool:
        return time_limit_seconds is not None and monotonic() - started >= time_limit_seconds

    for depth in range(1, max_depth + 1):
        candidates: list[tuple[int, int, Any, list[str], list[dict[str, str]]]] = []
        serial = 0
        for _, _, simulator, macro_path, action_path in frontier:
            if timed_out():
                return MacroExplorationResult(False, best_macros, best_actions, best_simulator, len(visited), expanded, depth, "time-limit", best_score)
            expanded += 1
            for successor in enumerate_macro_successors(simulator, macro_set):
                if state_filter is not None and not state_filter(successor.simulator):
                    continue
                key = canonical_state_key(successor.simulator)
                if key in visited:
                    continue
                visited.add(key)
                next_macros = [*macro_path, successor.macro.name]
                next_actions = [*action_path, *successor.actions]
                candidate_score = score(successor.simulator)
                serial += 1
                if candidate_score > best_score:
                    best_score = candidate_score
                    best_simulator = successor.simulator
                    best_macros = next_macros
                    best_actions = next_actions
                if goal(successor.simulator):
                    return MacroExplorationResult(True, next_macros, next_actions, successor.simulator, len(visited), expanded, depth, "goal", candidate_score)
                candidates.append((candidate_score, serial, successor.simulator, next_macros, next_actions))
                if len(visited) >= max_states:
                    return MacroExplorationResult(False, best_macros, best_actions, best_simulator, len(visited), expanded, depth, "state-limit", best_score)
        if not candidates:
            return MacroExplorationResult(False, best_macros, best_actions, best_simulator, len(visited), expanded, depth, "exhausted", best_score)
        candidates.sort(key=lambda item: item[0], reverse=True)
        frontier = candidates[:beam_width]

    return MacroExplorationResult(False, best_macros, best_actions, best_simulator, len(visited), expanded, max_depth, "depth-limit", best_score)
