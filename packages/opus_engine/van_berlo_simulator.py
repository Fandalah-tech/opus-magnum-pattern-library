from __future__ import annotations

from .final_simulator import Simulator as FinalSimulator
from .world import WorldEvent


class Simulator(FinalSimulator):
    """Final simulator with Van Berlo-aware duplication semantics.

    Van Berlo wheel atoms live on a deliberate overlap layer.  A duplication
    glyph whose source cell is covered by the wheel must read the wheel atom,
    not whichever ordinary atom happens to be returned first by World.atom_at.
    The transformed salt remains an ordinary, non-wheel atom.
    """

    def _process_duplication(self) -> None:
        classical = {"air", "earth", "fire", "water"}
        for source_pos, salt_pos, part_id in self.duplication_glyphs:
            source_candidates = self._atoms_at(source_pos)
            source = next(
                (
                    atom
                    for atom in source_candidates
                    if self._is_wheel_atom_id(atom.id) and atom.element in classical
                ),
                None,
            )
            if source is None:
                source = next(
                    (atom for atom in source_candidates if atom.element in classical),
                    None,
                )

            salt = next(
                (
                    atom
                    for atom in self._atoms_at(salt_pos)
                    if not self._is_wheel_atom_id(atom.id) and atom.element == "salt"
                ),
                None,
            )
            if source is None or salt is None:
                continue

            previous = salt.element
            salt.element = source.element
            self.world.events.append(WorldEvent("atom-duplicated", self.world.cycle, {
                "glyphPartId": part_id,
                "sourceAtomId": source.id,
                "transformedAtomId": salt.id,
                "fromElement": previous,
                "toElement": salt.element,
                "position": list(salt.position),
                "sourceLayer": "van-berlo" if self._is_wheel_atom_id(source.id) else "ordinary",
            }))
