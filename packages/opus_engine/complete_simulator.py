from __future__ import annotations

from .faithful_simulator import Simulator as FaithfulSimulator
from .simulator import GRAB


class Simulator(FaithfulSimulator):
    """Most complete simulator surface used by audits and consumers.

    A product already being carried through an output is consumed after a
    motion instruction, but an atom newly grabbed on the output during the
    current cycle is not delivered until a later cycle.
    """

    def _process_consumers(self) -> None:
        protected_arms = {
            arm_id
            for arm_id, instruction in self._active_instructions.items()
            if instruction in GRAB
        }
        held_by = {
            atom_id: set(atom.held_by)
            for atom_id, atom in self.world.atoms.items()
            if atom.held_by and not (set(atom.held_by) & protected_arms)
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
