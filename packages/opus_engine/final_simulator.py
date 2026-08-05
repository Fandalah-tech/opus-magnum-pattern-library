from __future__ import annotations

from typing import Any

from .complete_simulator import Simulator as CompleteSimulator
from .model import Atom
from .simulator import SimulationError, Simulator as BaseSimulator
from .world import WorldEvent

# Element order around the physical Van Berlo wheel in local branch order.
VAN_BERLO_ELEMENTS = ("salt", "water", "air", "salt", "fire", "earth")


class Simulator(CompleteSimulator):
    """Campaign-complete simulator surface.

    Models the Van Berlo wheel as six permanent atoms held by a six-branch
    rotating wheel and remembers repeating products that were valid at any
    point during the simulation.
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
        for arm in simulator.van_berlo_arms:
            arm.grabbing = True
            for branch, element in enumerate(VAN_BERLO_ELEMENTS):
                atom_id = f"{arm.id}-wheel-{branch}"
                atom = Atom(atom_id, element, arm.tip(branch))
                atom.held_by.add(arm.id)
                simulator.world.add_atom(atom)
                arm.held_atoms[branch] = atom_id
        if simulator.van_berlo_arms:
            simulator.frames[0] = simulator.snapshot("initial")
        return simulator

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

    def _validate_and_apply(self, proposals) -> None:
        try:
            super()._validate_and_apply(proposals)
        except SimulationError as error:
            output_cells = {
                position
                for _, _, expected_atoms, _ in self.output_patterns
                for position, _ in expected_atoms
            }
            candidates = []
            for molecule in self.world.molecules():
                if not any(
                    self.world.atoms[atom_id].position in output_cells
                    for atom_id in molecule.atom_ids
                ):
                    continue
                atoms, bonds = self._molecule_signature(set(molecule.atom_ids))
                candidates.append({
                    "atomIds": sorted(molecule.atom_ids),
                    "atoms": list(atoms),
                    "bonds": list(bonds),
                    "heldBy": {
                        atom_id: sorted(self.world.atoms[atom_id].held_by)
                        for atom_id in sorted(molecule.atom_ids)
                        if self.world.atoms[atom_id].held_by
                    },
                })
            raise SimulationError(f"{error}; outputCandidates={candidates}") from error

    def _process_consumers(self) -> None:
        # Standard outputs consume a matching product even when a grabber is
        # still attached to it. Preserve holder state only for atoms that remain.
        held_by = {
            atom_id: set(atom.held_by)
            for atom_id, atom in self.world.atoms.items()
            if atom.held_by
        }
        for atom_id in held_by:
            atom = self.world.atoms.get(atom_id)
            if atom is not None:
                atom.held_by.clear()

        super()._process_consumers()

        for atom_id, holders in held_by.items():
            atom = self.world.atoms.get(atom_id)
            if atom is not None:
                atom.held_by.update(holders)

    def _respawn_inputs(self) -> None:
        self._process_calcification()
        self._process_duplication()
        self._process_animismus()
        self._process_basic_glyphs()
        self._process_projection()
        self._process_purification()
        self._latch_repeating_outputs()
        self._process_consumers()
        BaseSimulator._respawn_inputs(self)
