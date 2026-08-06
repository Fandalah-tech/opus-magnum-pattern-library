from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Iterable

from packages.opus_engine import SimulationError

from .explorer import Action, enumerate_joint_actions
from .state import canonical_state_key

ScoreFunction = Callable[[Any], int]
GoalPredicate = Callable[[Any], bool]
StateFilter = Callable[[Any], bool]
ProgressCallback = Callable[[dict[str, Any]], None]

_INVERSE_INSTRUCTION = {
    "rotate_cw": "rotate_ccw",
    "rotate_ccw": "rotate_cw",
    "pivot_cw": "pivot_ccw",
    "pivot_ccw": "pivot_cw",
    "extend": "retract",
    "retract": "extend",
    "track_plus": "track_minus",
    "track_minus": "track_plus",
}


@dataclass(slots=True)
class BeamExplorationResult:
    found: bool
    actions: list[Action]
    simulator: Any | None
    visited_states: int
    expanded_states: int
    depth: int | None
    stopped_reason: str
    best_score: int


def _strip_history(simulator: Any) -> Any:
    if hasattr(simulator, "frames"):
        simulator.frames = simulator.frames[-1:]
    return simulator


def _immediately_reverses(previous: Action, current: Action) -> bool:
    """Return true only when every active arm exactly undoes its prior motion."""
    if not previous or previous.keys() != current.keys():
        return False
    return all(_INVERSE_INSTRUCTION.get(previous[arm_id]) == instruction for arm_id, instruction in current.items())


def explore_simulator_beam(
    initial_simulator: Any,
    action_options: dict[str, Iterable[str | None]],
    goal: GoalPredicate,
    score: ScoreFunction,
    *,
    max_depth: int = 30,
    beam_width: int = 2_000,
    max_states: int = 300_000,
    max_active_arms: int | None = 2,
    include_idle: bool = False,
    time_limit_seconds: float | None = None,
    prune_immediate_reversals: bool = True,
    state_filter: StateFilter | None = None,
    progress_callback: ProgressCallback | None = None,
    progress_interval_seconds: float = 10.0,
) -> BeamExplorationResult:
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if beam_width < 1:
        raise ValueError("beam_width must be positive")
    if max_states < 1:
        raise ValueError("max_states must be positive")
    if time_limit_seconds is not None and time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be positive")
    if progress_interval_seconds <= 0:
        raise ValueError("progress_interval_seconds must be positive")

    started = monotonic()
    last_progress = started
    root = _strip_history(deepcopy(initial_simulator))
    if state_filter is not None and not state_filter(root):
        raise ValueError("initial_simulator does not satisfy state_filter")
    root_score = score(root)
    if goal(root):
        return BeamExplorationResult(True, [], root, 1, 0, 0, "goal", root_score)

    actions = enumerate_joint_actions(
        action_options,
        include_idle=include_idle,
        max_active_arms=max_active_arms,
    )
    frontier: list[tuple[int, int, Any, list[Action]]] = [(root_score, 0, root, [])]
    visited = {canonical_state_key(root)}
    expanded = 0
    best_score = root_score
    best_simulator = root
    best_path: list[Action] = []

    def timed_out() -> bool:
        return time_limit_seconds is not None and monotonic() - started >= time_limit_seconds

    def emit_progress(depth: int, *, force: bool = False) -> None:
        nonlocal last_progress
        if progress_callback is None:
            return
        now = monotonic()
        if not force and now - last_progress < progress_interval_seconds:
            return
        last_progress = now
        progress_callback({
            "depth": depth,
            "elapsedSeconds": round(now - started, 3),
            "visitedStates": len(visited),
            "expandedStates": expanded,
            "frontierSize": len(frontier),
            "bestScore": best_score,
            "bestPathLength": len(best_path),
        })

    emit_progress(0, force=True)
    for depth in range(1, max_depth + 1):
        candidates: list[tuple[int, int, Any, list[Action]]] = []
        serial = 0
        for _, _, simulator, path in frontier:
            emit_progress(depth)
            if timed_out():
                emit_progress(depth, force=True)
                return BeamExplorationResult(False, best_path, best_simulator, len(visited), expanded, depth, "time-limit", best_score)
            expanded += 1
            previous_action = path[-1] if path else None
            for action in actions:
                if prune_immediate_reversals and previous_action is not None and _immediately_reverses(previous_action, action):
                    continue
                emit_progress(depth)
                if timed_out():
                    emit_progress(depth, force=True)
                    return BeamExplorationResult(False, best_path, best_simulator, len(visited), expanded, depth, "time-limit", best_score)
                candidate = _strip_history(deepcopy(simulator))
                try:
                    frame = candidate.step(action)
                except SimulationError:
                    continue
                if frame.get("phase") == "error":
                    continue

                candidate = _strip_history(candidate)
                if state_filter is not None and not state_filter(candidate):
                    continue
                key = canonical_state_key(candidate)
                if key in visited:
                    continue
                visited.add(key)
                candidate_path = [*path, dict(action)]
                candidate_score = score(candidate)
                serial += 1

                if candidate_score > best_score:
                    best_score = candidate_score
                    best_simulator = candidate
                    best_path = candidate_path
                    emit_progress(depth, force=True)
                if goal(candidate):
                    emit_progress(depth, force=True)
                    return BeamExplorationResult(True, candidate_path, candidate, len(visited), expanded, depth, "goal", candidate_score)
                candidates.append((candidate_score, serial, candidate, candidate_path))
                if len(visited) >= max_states:
                    emit_progress(depth, force=True)
                    return BeamExplorationResult(False, best_path, best_simulator, len(visited), expanded, depth, "state-limit", best_score)

        if not candidates:
            emit_progress(depth, force=True)
            return BeamExplorationResult(False, best_path, best_simulator, len(visited), expanded, depth, "exhausted", best_score)
        candidates.sort(key=lambda item: (item[0], -len(item[3])), reverse=True)
        frontier = candidates[:beam_width]
        emit_progress(depth, force=True)

    emit_progress(max_depth, force=True)
    return BeamExplorationResult(False, best_path, best_simulator, len(visited), expanded, max_depth, "depth-limit", best_score)
