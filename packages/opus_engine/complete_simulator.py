from __future__ import annotations

from .faithful_simulator import Simulator as FaithfulSimulator


class Simulator(FaithfulSimulator):
    """Most complete simulator surface used by audits and consumers.

    Opus Magnum outputs consume a matching product as soon as its full
    footprint is present, even when an arm still holds one of its atoms.
    The inherited molecule-removal path safely detaches those atoms from
    every arm after delivery.
    """

    def _process_consumers(self) -> None:
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
