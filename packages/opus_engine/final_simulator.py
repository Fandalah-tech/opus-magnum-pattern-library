from __future__ import annotations

from typing import Any

from .builder import DIRECTIONS
from .complete_simulator import Simulator as CompleteSimulator
from .simulator import Simulator as BaseSimulator
from .world import WorldEvent

VAN_BERLO_ELEMENTS = ("salt", "air", "water", "salt", "earth", "fire")


class Simulator(CompleteSimulator):
    """Campaign-complete simulator surface.

    Adds Van Berlo wheel chemistry and remembers repeating products that were
    valid at any point during the simulation, even if the finished polymer is
    later moved away from the output footprint.
    """

    def __post_init__(self) -> None:
        self.van_berlo_arms = []
        self.completed_repeating_outputs = set()
        super().__post_init__()

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        simulator.van_berlo_arms = [
            arm for arm in simulator.arms.values() if arm.part_type == "baron"
        ]
        return simulator

    def _process_van_berlo(self) -> None:
        for arm in self.van_berlo_arms:
            for direction_index, direction in enumerate(DIRECTIONS):
                position = (arm.origin[0] + direction[0], arm.origin[1] + direction[1])
                atom = self.world.atom_at(position)
                if atom is None or atom.element != "salt":
                    continue
                produced = VAN_BERLO_ELEMENTS[(arm.rotation - direction_index) % 6]
                if produced == "salt":
                    continue
                atom.element = produced
                self.world.events.append(WorldEvent("atom-van-berlo-transformed", self.world.cycle, {
                    "wheelPartId": arm.id,
                    "atomId": atom.id,
                    "toElement": produced,
                    "position": list(position),
                }))

    def repeating_product_complete(self, output_id: str, repetitions: int = 3) -> bool:
        if output_id in self.completed_repeating_outputs:
            return True
        return super().repeating_product_complete(output_id, repetitions)

    def _latch_repeating_outputs(self) -> None:
        for output_id, *_ in self.repeating_patterns:
            if output_id in self.completed_repeating_outputs:
                continue
            if super().repeating_product_complete(output_id, 3):
                self.completed_repeating_outputs.add(output_id)
                self.world.events.append(WorldEvent("repeating-product-completed", self.world.cycle, {
                    "consumerPartId": output_id,
                    "repetitions": 3,
                }))

    def _respawn_inputs(self) -> None:
        self._process_calcification()
        self._process_van_berlo()
        self._process_duplication()
        self._process_animismus()
        self._process_basic_glyphs()
        self._process_projection()
        self._process_purification()
        self._latch_repeating_outputs()
        self._process_consumers()
        BaseSimulator._respawn_inputs(self)
