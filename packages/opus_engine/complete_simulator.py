from __future__ import annotations

from typing import Any

from .builder import rotate_hex
from .faithful_simulator import Simulator as FaithfulSimulator
from .model import Atom
from .simulator import GRAB, Simulator as BaseSimulator
from .world import WorldEvent


def _transform(
    position: tuple[int, int],
    origin: tuple[int, int],
    rotation: int,
) -> tuple[int, int]:
    rotated = rotate_hex(position, rotation)
    return origin[0] + rotated[0], origin[1] + rotated[1]


class Simulator(FaithfulSimulator):
    """Most complete simulator surface used by audits and consumers."""

    def __post_init__(self) -> None:
        self.animismus_glyphs = []
        self.duplication_glyphs = []
        self.faithful_purification_glyphs = []
        super().__post_init__()

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        simulator.purification_glyphs = []
        for part in solution.get("parts", []):
            part_type = str(part.get("type") or "")
            origin = tuple(part.get("position") or (0, 0))
            rotation = int(part.get("rotation") or 0)
            part_id = str(part.get("id") or part_type)
            if part_type == "glyph-life-and-death":
                simulator.animismus_glyphs.append((
                    _transform((0, 0), origin, rotation),
                    _transform((1, 0), origin, rotation),
                    _transform((0, 1), origin, rotation),
                    _transform((1, -1), origin, rotation),
                    part_id,
                ))
            elif part_type == "glyph-duplication":
                simulator.duplication_glyphs.append((
                    _transform((0, 0), origin, rotation),
                    _transform((1, 0), origin, rotation),
                    part_id,
                ))
            elif part_type == "glyph-purification":
                simulator.faithful_purification_glyphs.append((
                    _transform((0, 0), origin, rotation),
                    _transform((1, 0), origin, rotation),
                    _transform((0, 1), origin, rotation),
                    part_id,
                ))
        return simulator

    def _is_conversion_input(self, atom) -> bool:
        if atom is None or atom.held_by:
            return False
        return not any(
            bond.a == atom.id or bond.b == atom.id
            for bond in self.world.bonds.values()
        )

    def _process_duplication(self) -> None:
        classical = {"air", "earth", "fire", "water"}
        for source_pos, salt_pos, part_id in self.duplication_glyphs:
            source = self.world.atom_at(source_pos)
            salt = self.world.atom_at(salt_pos)
            if source is None or salt is None:
                continue
            if source.element not in classical or salt.element != "salt":
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
            }))

    def _process_animismus(self) -> None:
        for first_pos, second_pos, vitae_pos, mors_pos, part_id in self.animismus_glyphs:
            first = self.world.atom_at(first_pos)
            second = self.world.atom_at(second_pos)
            if (
                not self._is_conversion_input(first)
                or not self._is_conversion_input(second)
                or first.element != "salt"
                or second.element != "salt"
                or self.world.atom_at(vitae_pos) is not None
                or self.world.atom_at(mors_pos) is not None
            ):
                continue
            consumed = sorted((first.id, second.id))
            self._remove_molecule(set(consumed))
            vitae_id = f"{part_id}-vitae-{self._glyph_generation}"
            mors_id = f"{part_id}-mors-{self._glyph_generation}"
            self._glyph_generation += 1
            self.world.add_atom(Atom(vitae_id, "vitae", vitae_pos))
            self.world.add_atom(Atom(mors_id, "mors", mors_pos))
            self.world.events.append(WorldEvent("atoms-animated", self.world.cycle, {
                "glyphPartId": part_id,
                "consumedAtomIds": consumed,
                "producedAtomIds": [vitae_id, mors_id],
            }))

    def _process_purification(self) -> None:
        metal_order = ("lead", "tin", "iron", "copper", "silver", "gold")
        for first_pos, second_pos, output_pos, part_id in self.faithful_purification_glyphs:
            first = self.world.atom_at(first_pos)
            second = self.world.atom_at(second_pos)
            if (
                not self._is_conversion_input(first)
                or not self._is_conversion_input(second)
                or first.element != second.element
                or self.world.atom_at(output_pos) is not None
            ):
                continue
            try:
                index = metal_order.index(first.element)
            except ValueError:
                continue
            if index >= len(metal_order) - 1:
                continue
            consumed = sorted((first.id, second.id))
            self._remove_molecule(set(consumed))
            atom_id = f"{part_id}-purified-{self._glyph_generation}"
            self._glyph_generation += 1
            produced = metal_order[index + 1]
            self.world.add_atom(Atom(atom_id, produced, output_pos))
            self.world.events.append(WorldEvent("atom-purified", self.world.cycle, {
                "glyphPartId": part_id,
                "consumedAtomIds": consumed,
                "producedAtomId": atom_id,
                "element": produced,
                "position": list(output_pos),
            }))

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

    def _respawn_inputs(self) -> None:
        self._process_calcification()
        self._process_duplication()
        self._process_animismus()
        self._process_basic_glyphs()
        self._process_projection()
        self._process_purification()
        self._process_consumers()
        BaseSimulator._respawn_inputs(self)
