from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from typing import Any, Callable, Iterable

from packages.opus_engine import SimulationError

from .state import canonical_state_key

Action = dict[str, str]
GoalPredicate = Callable[[Any], bool]


@dataclass(slots=True)
class ExplorationResult:
    found: bool
    actions: list[Action]
    simulator: Any | None
    visited_states: int
    expanded_states: int
    depth: int | None
    stopped_reason: str


def enumerate_joint_actions(
    action_options: dict[str, Iterable[str | None]],
    *,
    include_idle: bool = False,
    max_active_arms: int | None = None,
) -> list[Action]:
    """Expand per-arm instruction choices into deterministic joint actions.

    ``None`` represents an idle arm. ``max_active_arms`` can cap simultaneous
    arm actions, which is useful for a first inexpensive search pass before
    allowing fully coordinated motions.
    """
    if max_active_arms is not None and max_active_arms < 0:
        raise ValueError("max_active_arms must be non-negative")

    arm_ids = sorted(str(arm_id) for arm_id in action_options)
    choices = [tuple(action_options[arm_id]) for arm_id in arm_ids]
    actions: list[Action] = []
    for combination in product(*choices):
        action = {
            arm_id: instruction
            for arm_id, instruction in zip(arm_ids, combination, strict=True)
            if instruction is not None
        }
        if max_active_arms is not None and len(action) > max_active_arms:
            continue
        if action or include_idle:
            actions.append(action)
    return actions


def explore_simulator_states(
    initial_simulator: Any,
    action_options: dict[str, Iterable[str | None]],
    goal: GoalPredicate,
    *,
    max_depth: int = 12,
    max_states: int = 100_000,
    include_idle: bool = False,
    max_active_arms: int | None = None,
) -> ExplorationResult:
    """Breadth-first search over legal simulator transitions.

    This is intentionally a local choreography explorer rather than a complete
    puzzle solver. Callers choose the active arms and instruction vocabulary,
    which makes it suitable for questions such as: "Can this tri-salt fragment
    be inserted from the current frame without exceeding the fixed layout?"
    """
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if max_states < 1:
        raise ValueError("max_states must be positive")

    root = deepcopy(initial_simulator)
    root_key = canonical_state_key(root)
    if goal(root):
        return ExplorationResult(True, [], root, 1, 0, 0, "goal")

    joint_actions = enumerate_joint_actions(
        action_options,
        include_idle=include_idle,
        max_active_arms=max_active_arms,
    )
    queue = deque([(root, [], 0)])
    visited = {root_key}
    expanded = 0

    while queue:
        simulator, path, depth = queue.popleft()
        if depth >= max_depth:
            continue
        expanded += 1

        for action in joint_actions:
            candidate = deepcopy(simulator)
            try:
                frame = candidate.step(action)
            except SimulationError:
                continue
            if frame.get("phase") == "error":
                continue

            key = canonical_state_key(candidate)
            if key in visited:
                continue
            visited.add(key)
            candidate_path = [*path, dict(action)]
            candidate_depth = depth + 1

            if goal(candidate):
                return ExplorationResult(
                    True,
                    candidate_path,
                    candidate,
                    len(visited),
                    expanded,
                    candidate_depth,
                    "goal",
                )
            if len(visited) >= max_states:
                return ExplorationResult(
                    False,
                    [],
                    None,
                    len(visited),
                    expanded,
                    None,
                    "state-limit",
                )
            queue.append((candidate, candidate_path, candidate_depth))

    return ExplorationResult(
        False,
        [],
        None,
        len(visited),
        expanded,
        None,
        "exhausted",
    )
