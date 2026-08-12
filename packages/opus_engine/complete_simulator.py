from __future__ import annotations

from typing import Any

from .builder import rotate_hex
from .faithful_simulator import Simulator as FaithfulSimulator
from .model import Atom, Bond
from .runtime_simulator import METAL_ORDER
from .simulator import GRAB, SimulationError, Simulator as BaseSimulator
from .world import WorldEvent


def _transform(
    position: tuple[int, int] | list[int],
    origin: tuple[int, int],
    rotation: int,
) -> tuple[int, int]:
    rotated = rotate_hex((int(position[0]), int(position[1])), rotation)
    return origin[0] + rotated[0], origin[1] + rotated[1]


class Simulator(FaithfulSimulator):
    """Most complete simulator surface used by audits and consumers."""

    def __post_init__(self) -> None:
        self.animismus_glyphs = []
        self.duplication_glyphs = []
        self.faithful_purification_glyphs = []
        self.repeating_patterns = []
        self.rejection_glyphs = []
        self.division_glyphs = []
        self.unification_glyphs = []
        self.proliferation_glyphs = []
        self.conduit_pairs = []
        self._pending_conduit_payloads = []
        super().__post_init__()

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        simulator.purification_glyphs = []
        products = puzzle.get("products", [])
        pipe_parts = []
        for part in solution.get("parts", []):
            part_type = str(part.get("type") or "")
            origin = tuple(part.get("position") or (0, 0))
            rotation = int(part.get("rotation") or 0)
            part_id = str(part.get("id") or part_type)
            if part_type == "pipe":
                pipe_parts.append(part)
                continue
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
            elif part_type == "glyph-rejection":
                simulator.rejection_glyphs.append((
                    _transform((0, 0), origin, rotation),
                    _transform((1, 0), origin, rotation),
                    part_id,
                ))
            elif part_type == "glyph-division":
                simulator.division_glyphs.append((
                    _transform((0, 0), origin, rotation),
                    _transform((1, 0), origin, rotation),
                    _transform((-1, 0), origin, rotation),
                    part_id,
                ))
            elif part_type == "glyph-unification":
                simulator.unification_glyphs.append((
                    tuple(_transform(cell, origin, rotation) for cell in ((0, 1), (-1, 1), (0, -1), (1, -1))),
                    _transform((0, 0), origin, rotation),
                    part_id,
                ))
            elif part_type == "glyph-proliferation":
                simulator.proliferation_glyphs.append((
                    _transform((-1, 1), origin, rotation),
                    _transform((1, 1), origin, rotation),
                    _transform((1, -1), origin, rotation),
                    part_id,
                ))
            elif part_type == "out-rep":
                product_index = int(part.get("which") or 0)
                if not 0 <= product_index < len(products):
                    continue
                product = products[product_index]
                real_atoms = [atom for atom in product.get("atoms", []) if atom.get("element") != "repeat"]
                repeat_atoms = [atom for atom in product.get("atoms", []) if atom.get("element") == "repeat"]
                if not real_atoms or not repeat_atoms:
                    continue
                anchor_local = tuple(real_atoms[0].get("position") or (0, 0))
                repeat_local = tuple(repeat_atoms[0].get("position") or (0, 0))
                anchor = _transform(anchor_local, origin, rotation)
                repeat_position = _transform(repeat_local, origin, rotation)
                shift = (repeat_position[0] - anchor[0], repeat_position[1] - anchor[1])
                atoms = tuple(
                    (tuple(atom.get("position") or (0, 0)), str(atom.get("element")))
                    for atom in real_atoms
                )
                bonds = tuple(
                    (
                        str(bond.get("type") or "normal"),
                        tuple(bond.get("from") or (0, 0)),
                        tuple(bond.get("to") or (0, 0)),
                    )
                    for bond in product.get("bonds", [])
                )
                simulator.repeating_patterns.append((
                    part_id, origin, rotation, anchor_local, repeat_local, shift, atoms, bonds,
                ))
        pipes_by_id = {}
        for part in pipe_parts:
            pipes_by_id.setdefault(int(part.get("pipeId") or 0), []).append(part)
        for pipe_id, sides in pipes_by_id.items():
            if len(sides) != 2:
                continue
            parsed_sides = []
            for part in sides:
                origin = tuple(part.get("position") or (0, 0))
                rotation = int(part.get("rotation") or 0)
                cells = tuple(tuple(cell) for cell in (part.get("pipeHexes") or [(0, 0)]))
                parsed_sides.append({
                    "id": str(part.get("id") or f"pipe-{pipe_id}"),
                    "origin": origin,
                    "rotation": rotation,
                    "localCells": cells,
                    "worldCells": frozenset(_transform(cell, origin, rotation) for cell in cells),
                })
            simulator.conduit_pairs.append((parsed_sides[0], parsed_sides[1]))
        return simulator

    @staticmethod
    def _conduit_local(position, side):
        relative = (position[0] - side["origin"][0], position[1] - side["origin"][1])
        return rotate_hex(relative, -side["rotation"])

    def _capture_conduit_direction(self, source, target) -> None:
        for molecule in list(self.world.molecules()):
            atom_ids = set(molecule.atom_ids)
            positions = {self.world.atoms[atom_id].position for atom_id in atom_ids}
            if not positions or not positions.issubset(source["worldCells"]):
                continue
            local_by_id = {
                atom_id: self._conduit_local(self.world.atoms[atom_id].position, source)
                for atom_id in atom_ids
            }
            payload = {
                "sourcePartId": source["id"],
                "targetPartId": target["id"],
                "atoms": [(atom_id, self.world.atoms[atom_id].element, local_by_id[atom_id]) for atom_id in sorted(atom_ids)],
                "bonds": [
                    (bond.a, bond.b, bond.kind)
                    for bond in self.world.bonds.values()
                    if bond.a in atom_ids and bond.b in atom_ids
                ],
                "target": target,
            }
            self._pending_conduit_payloads.append(payload)
            self._remove_molecule(atom_ids)
            self.world.events.append(WorldEvent("molecule-entered-conduit", self.world.cycle, {
                "conduitPartId": source["id"], "targetPartId": target["id"],
                "atomIds": sorted(atom_ids),
            }))

    def _capture_conduits(self) -> None:
        if self._pending_conduit_payloads:
            return
        for first, second in self.conduit_pairs:
            self._capture_conduit_direction(first, second)
            self._capture_conduit_direction(second, first)

    def _emit_conduits(self) -> None:
        pending = self._pending_conduit_payloads
        self._pending_conduit_payloads = []
        for payload in pending:
            target = payload["target"]
            id_map = {}
            destinations = {
                old_id: _transform(local, target["origin"], target["rotation"])
                for old_id, _, local in payload["atoms"]
            }
            blocked = next((position for position in destinations.values() if self.world.atom_at(position) is not None), None)
            if blocked is not None:
                raise SimulationError(f"Conduit output collision at {blocked}")
            for old_id, element, _ in payload["atoms"]:
                atom_id = f"{target['id']}-conduit-{self._glyph_generation}"
                self._glyph_generation += 1
                id_map[old_id] = atom_id
                self.world.add_atom(Atom(atom_id, element, destinations[old_id]))
            for first, second, kind in payload["bonds"]:
                self.world.add_bond(Bond(id_map[first], id_map[second], kind))
            self.world.events.append(WorldEvent("molecule-exited-conduit", self.world.cycle, {
                "conduitPartId": target["id"],
                "sourcePartId": payload["sourcePartId"],
                "atomIds": sorted(id_map.values()),
            }))

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

    def _produce_atom(self, part_id: str, suffix: str, element: str, position) -> str:
        atom_id = f"{part_id}-{suffix}-{self._glyph_generation}"
        self._glyph_generation += 1
        self.world.add_atom(Atom(atom_id, element, position))
        return atom_id

    def _process_rejection(self) -> None:
        for metal_pos, output_pos, part_id in self.rejection_glyphs:
            metal = self.world.atom_at(metal_pos)
            if metal is None or self.world.atom_at(output_pos) is not None:
                continue
            try:
                index = METAL_ORDER.index(metal.element)
            except ValueError:
                continue
            if index == 0:
                continue
            previous = metal.element
            metal.element = METAL_ORDER[index - 1]
            produced_id = self._produce_atom(part_id, "quicksilver", "quicksilver", output_pos)
            self.world.events.append(WorldEvent("atom-rejected", self.world.cycle, {
                "glyphPartId": part_id, "transformedAtomId": metal.id,
                "producedAtomId": produced_id, "fromElement": previous,
                "toElement": metal.element,
            }))

    def _process_division(self) -> None:
        for input_pos, first_pos, second_pos, part_id in self.division_glyphs:
            source = self.world.atom_at(input_pos)
            if (not self._is_conversion_input(source)
                    or self.world.atom_at(first_pos) is not None
                    or self.world.atom_at(second_pos) is not None):
                continue
            try:
                index = METAL_ORDER.index(source.element)
            except ValueError:
                continue
            if index == 0:
                continue
            source_id = source.id
            self._remove_molecule({source_id})
            first_element = METAL_ORDER[index // 2]
            second_element = METAL_ORDER[(index - 1) // 2]
            first_id = self._produce_atom(part_id, "division-a", first_element, first_pos)
            second_id = self._produce_atom(part_id, "division-b", second_element, second_pos)
            self.world.events.append(WorldEvent("atom-divided", self.world.cycle, {
                "glyphPartId": part_id, "consumedAtomId": source_id,
                "producedAtomIds": [first_id, second_id],
            }))

    def _process_unification(self) -> None:
        required = {"air", "earth", "fire", "water"}
        for input_positions, output_pos, part_id in self.unification_glyphs:
            atoms = [self.world.atom_at(position) for position in input_positions]
            if (any(not self._is_conversion_input(atom) for atom in atoms)
                    or {atom.element for atom in atoms if atom is not None} != required
                    or self.world.atom_at(output_pos) is not None):
                continue
            consumed = {atom.id for atom in atoms if atom is not None}
            self._remove_molecule(consumed)
            produced_id = self._produce_atom(part_id, "quintessence", "quintessence", output_pos)
            self.world.events.append(WorldEvent("atoms-unified", self.world.cycle, {
                "glyphPartId": part_id, "consumedAtomIds": sorted(consumed),
                "producedAtomId": produced_id,
            }))

    def _process_proliferation(self) -> None:
        for source_pos, quicksilver_pos, output_pos, part_id in self.proliferation_glyphs:
            source = self.world.atom_at(source_pos)
            quicksilver = self.world.atom_at(quicksilver_pos)
            if (source is None or source.element not in METAL_ORDER
                    or not self._is_conversion_input(quicksilver)
                    or quicksilver.element != "quicksilver"
                    or self.world.atom_at(output_pos) is not None):
                continue
            consumed_id = quicksilver.id
            self._remove_molecule({consumed_id})
            produced_id = self._produce_atom(part_id, "proliferated", source.element, output_pos)
            self.world.events.append(WorldEvent("atom-proliferated", self.world.cycle, {
                "glyphPartId": part_id, "sourceAtomId": source.id,
                "consumedAtomId": consumed_id, "producedAtomId": produced_id,
            }))

    def repeating_product_complete(self, output_id: str, repetitions: int = 3) -> bool:
        pattern = next((item for item in self.repeating_patterns if item[0] == output_id), None)
        if pattern is None:
            return False
        _, origin, rotation, anchor_local, repeat_local, shift, atoms, bonds = pattern
        repeat_set = {repeat_local}

        def position_for(local: tuple[int, int], repetition: int) -> tuple[int, int]:
            base = _transform(local, origin, rotation)
            return base[0] + repetition * shift[0], base[1] + repetition * shift[1]

        atom_ids: dict[tuple[int, tuple[int, int]], str] = {}
        for repetition in range(repetitions):
            for local, element in atoms:
                position = position_for(local, repetition)
                atom = self.world.atom_at(position)
                if atom is None or atom.element != element:
                    return False
                atom_ids[(repetition, local)] = atom.id

        for repetition in range(repetitions):
            for kind, start, end in bonds:
                start_rep = repetition
                end_rep = repetition
                start_local = start
                end_local = end
                if start in repeat_set:
                    start_rep += 1
                    start_local = anchor_local
                if end in repeat_set:
                    end_rep += 1
                    end_local = anchor_local
                if start_rep >= repetitions or end_rep >= repetitions:
                    continue
                first_id = atom_ids.get((start_rep, start_local))
                second_id = atom_ids.get((end_rep, end_local))
                if first_id is None or second_id is None:
                    return False
                if Bond(first_id, second_id, kind).key not in self.world.bonds:
                    return False
        return True

    def _process_disposal_exact(self) -> None:
        """Apply the disposal glyph without weakening grab/bond guards.

        The game removes only the single atom on the glyph, and only while that
        atom is unbonded and not grabbed. It never consumes an entire molecule.
        """
        for position in tuple(self.disposal_cells):
            atom = self.world.atom_at(position)
            if atom is None or atom.held_by:
                continue
            if any(atom.id in (bond.a, bond.b) for bond in self.world.bonds.values()):
                continue
            atom_id = atom.id
            self._remove_molecule({atom_id})
            self.world.events.append(WorldEvent("molecule-consumed", self.world.cycle, {
                "consumerType": "glyph-disposal",
                "atomIds": [atom_id],
            }))

    def _process_consumers(self) -> None:
        # Disposal observes the real GRABBED state. Outputs retain the existing
        # half-cycle compatibility behavior, where atoms already in motion may
        # be consumed but an atom grabbed in this instruction may not.
        self._process_disposal_exact()
        disposal_cells = self.disposal_cells
        self.disposal_cells = set()

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

        try:
            super()._process_consumers()
        finally:
            self.disposal_cells = disposal_cells
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
        self._process_rejection()
        self._process_division()
        self._process_unification()
        self._process_proliferation()
        self._process_consumers()
        BaseSimulator._respawn_inputs(self)
