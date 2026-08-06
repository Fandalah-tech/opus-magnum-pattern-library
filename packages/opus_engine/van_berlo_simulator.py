from __future__ import annotations

from .final_simulator import Simulator as FinalSimulator
from .world import WorldEvent


class Simulator(FinalSimulator):
    """Final simulator with Van Berlo-specific overlap and wheel semantics."""

    def _drop(self, arm) -> None:
        if arm.part_type != "baron":
            return super()._drop(arm)

        # Van Berlo's six native wheel atoms are permanent parts of the wheel.
        # DROP releases any ordinary payload overlapping its grabbers, but must
        # never detach the wheel atoms themselves or disable future rotations.
        wheel_atoms = {
            branch: atom_id
            for branch, atom_id in arm.held_atoms.items()
            if self._is_wheel_atom_id(atom_id)
        }
        arm.held_atoms = wheel_atoms
        arm.grabbing = True
        self.world.events.append(WorldEvent("van-berlo-payload-dropped", self.world.cycle, {
            "armId": arm.id,
            "retainedWheelAtomIds": sorted(wheel_atoms.values()),
        }))

    def _grab(self, arm) -> None:
        if arm.part_type == "baron":
            # Payload capture is positional and evaluated by
            # _baron_attached_atom_ids; native wheel atoms stay retained.
            arm.grabbing = True
            return
        return super()._grab(arm)

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
