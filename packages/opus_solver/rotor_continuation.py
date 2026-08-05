from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .explorer import ExplorationResult, explore_simulator_states


@dataclass(frozen=True, slots=True)
class RotorContinuationTarget:
    minimum_bonds: int = 1
    require_held_atom: bool = False

    def reached(self, simulator: Any) -> bool:
        if len(simulator.world.bonds) < self.minimum_bonds:
            return False
        if self.require_held_atom:
            return any(arm.held_atoms for arm in simulator.arms.values())
        return True


def search_compact_continuation(
    simulator: Any,
    *,
    target: RotorContinuationTarget | None = None,
    max_depth: int = 8,
    max_states: int = 200_000,
) -> ExplorationResult:
    """Search the two compact Rotor pistons for the next persistent bond.

    The fixed A42 layout and trusted human prefix remain untouched. Search is
    limited to the two pistons and the ordinary mechanical instruction set.
    """
    target = target or RotorContinuationTarget()
    active = {
        arm_id: (
            None,
            "grab",
            "drop",
            "rotate_cw",
            "rotate_ccw",
            "pivot_cw",
            "pivot_ccw",
            "extend",
            "retract",
            "track_plus",
            "track_minus",
        )
        for arm_id in sorted(simulator.arms)
        if simulator.arms[arm_id].part_type == "piston"
    }
    return explore_simulator_states(
        simulator,
        active,
        target.reached,
        max_depth=max_depth,
        max_states=max_states,
        include_idle=False,
    )
