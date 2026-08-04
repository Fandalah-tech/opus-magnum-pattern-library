from __future__ import annotations

from typing import Any

from .simulator import RESET, Simulator as BaseSimulator


class Simulator(BaseSimulator):
    """Runtime simulator with Opus Magnum reset semantics.

    Reset always releases every held atom before returning the arm to its
    configured base state. The base simulator then performs the positional,
    rotational, piston, and track reset without carrying a molecule along.
    """

    def step(self, instructions: dict[str, str | None]) -> dict[str, Any]:
        for arm_id, instruction in instructions.items():
            if instruction not in RESET:
                continue
            arm = self.arms.get(arm_id)
            if arm is not None:
                self._drop(arm)
        return super().step(instructions)
