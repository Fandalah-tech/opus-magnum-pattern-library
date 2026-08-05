from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from packages.opus_engine import SimulationError

from .state import canonical_state_key

Action = Mapping[str, str]
MacroGuard = Callable[[Any], bool]


@dataclass(frozen=True, slots=True)
class MechanicalMacro:
    """A validated multi-cycle mechanical transformation.

    Macros deliberately describe arm motion only. They are independent from
    atom types and chemistry, so confined rotations, temporary nucleus storage,
    pair insertion and recovery can be learned and searched before Van Berlo or
    calcification constraints are reintroduced.
    """

    name: str
    actions: tuple[dict[str, str], ...]
    tags: frozenset[str] = frozenset()
    guard: MacroGuard | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("macro name must not be empty")
        if not self.actions:
            raise ValueError("macro must contain at least one action frame")

    @classmethod
    def from_actions(
        cls,
        name: str,
        actions: Sequence[Action],
        *,
        tags: Iterable[str] = (),
        guard: MacroGuard | None = None,
    ) -> "MechanicalMacro":
        return cls(
            name=name,
            actions=tuple(dict(action) for action in actions),
            tags=frozenset(tags),
            guard=guard,
        )

    def applicable(self, simulator: Any) -> bool:
        return self.guard is None or self.guard(simulator)


@dataclass(slots=True)
class MacroApplication:
    macro: MechanicalMacro
    simulator: Any
    actions: list[dict[str, str]]


def apply_mechanical_macro(simulator: Any, macro: MechanicalMacro) -> MacroApplication | None:
    """Apply a macro atomically, rejecting the whole macro on any collision.

    The input simulator is never mutated. Returning ``None`` makes invalid
    mechanical transformations cheap to prune during macro-level search.
    """
    if not macro.applicable(simulator):
        return None

    candidate = deepcopy(simulator)
    executed: list[dict[str, str]] = []
    try:
        for action in macro.actions:
            frame = candidate.step(action)
            if frame.get("phase") == "error":
                return None
            executed.append(dict(action))
    except SimulationError:
        return None
    return MacroApplication(macro, candidate, executed)


def enumerate_macro_successors(
    simulator: Any,
    macros: Iterable[MechanicalMacro],
) -> list[MacroApplication]:
    """Return distinct valid successors produced by complete macros."""
    successors: list[MacroApplication] = []
    seen: set[tuple[Any, ...]] = set()
    for macro in macros:
        applied = apply_mechanical_macro(simulator, macro)
        if applied is None:
            continue
        key = canonical_state_key(applied.simulator)
        if key in seen:
            continue
        seen.add(key)
        successors.append(applied)
    return successors


def select_macros(
    macros: Iterable[MechanicalMacro],
    *,
    required_tags: Iterable[str] = (),
) -> tuple[MechanicalMacro, ...]:
    required = frozenset(required_tags)
    return tuple(macro for macro in macros if required <= macro.tags)
