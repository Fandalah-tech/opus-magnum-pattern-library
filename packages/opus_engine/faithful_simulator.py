from __future__ import annotations

from typing import Any

from .runtime_simulator import METAL_ORDER, Simulator as RuntimeSimulator
from .world import WorldEvent


class Simulator(RuntimeSimulator):
    """Runtime simulator with per-arm track ownership and safe atom consumption."""

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        tracks = [
            tuple(tuple(cell) for cell in (part.get("trackHexes") or []))
            for part in solution.get("parts", [])
            if part.get("type") == "track"
        ]
        for arm in simulator.arms.values():
            owned_track = next((track for track in tracks if arm.origin in track), ())
            arm.track_cells = owned_track
            if owned_track:
                arm.track_index = owned_track.index(arm.origin)
                arm.base_track_index = arm.track_index
            else:
                arm.track_index = 0
                arm.base_track_index = 0
        return simulator

    def _detach_consumed_atom(self, atom_id: str) -> None:
        atom = self.world.atoms.get(atom_id)
        if atom is not None:
            for arm_id in list(atom.held_by):
                arm = self.arms.get(arm_id)
                if arm is None:
                    continue
                arm.held_atoms = {
                    branch: held_atom_id
                    for branch, held_atom_id in arm.held_atoms.items()
                    if held_atom_id != atom_id
                }
                if not arm.held_atoms:
                    arm.grabbing = False
            atom.held_by.clear()

    def _process_projection(self) -> None:
        for first_pos, second_pos, part_id in self.projection_glyphs:
            first = self.world.atom_at(first_pos)
            second = self.world.atom_at(second_pos)
            if first is None or second is None:
                continue

            if first.element == "quicksilver":
                quicksilver, metal = first, second
            elif second.element == "quicksilver":
                quicksilver, metal = second, first
            else:
                continue

            try:
                index = METAL_ORDER.index(metal.element)
            except ValueError:
                continue
            if index >= len(METAL_ORDER) - 1:
                continue

            previous = metal.element
            produced = METAL_ORDER[index + 1]
            consumed_id = quicksilver.id
            self._detach_consumed_atom(consumed_id)
            self.world.remove_atom(consumed_id)
            self._replace_atom_element(metal.id, produced)
            self.world.events.append(WorldEvent("atom-projected", self.world.cycle, {
                "glyphPartId": part_id,
                "consumedAtomId": consumed_id,
                "transformedAtomId": metal.id,
                "fromElement": previous,
                "toElement": produced,
                "position": list(metal.position),
            }))
