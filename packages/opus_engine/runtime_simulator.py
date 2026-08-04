from __future__ import annotations

from typing import Any

from .builder import rotate_hex
from .simulator import RESET, SimulationError, Simulator as BaseSimulator
from .world import WorldEvent


def _transform(position: list[int] | tuple[int, int], origin: tuple[int, int], rotation: int) -> tuple[int, int]:
    rotated = rotate_hex((int(position[0]), int(position[1])), rotation)
    return origin[0] + rotated[0], origin[1] + rotated[1]


def _bond_signature(kind: str, start: tuple[int, int], end: tuple[int, int]) -> tuple:
    first, second = sorted((start, end))
    return kind, first, second


class Simulator(BaseSimulator):
    """Runtime simulator with reset and board-consumer semantics."""

    def __post_init__(self) -> None:
        self.output_patterns = []
        self.disposal_cells = set()
        self.delivered_products = {}
        self._active_instructions = {}
        super().__post_init__()

    @classmethod
    def from_models(cls, puzzle: dict[str, Any], solution: dict[str, Any]) -> "Simulator":
        simulator = super().from_models(puzzle, solution)
        products = puzzle.get("products", [])

        for part in solution.get("parts", []):
            part_type = str(part.get("type") or "")
            if part_type == "glyph-disposal":
                simulator.disposal_cells.add(tuple(part.get("position") or (0, 0)))
                continue
            if not part_type.startswith("out-"):
                continue
            product_index = int(part.get("which") or 0)
            if not 0 <= product_index < len(products):
                continue
            origin = tuple(part.get("position") or (0, 0))
            rotation = int(part.get("rotation") or 0)
            product = products[product_index]
            atoms = tuple(sorted(
                (_transform(atom.get("position") or (0, 0), origin, rotation), str(atom.get("element")))
                for atom in product.get("atoms", [])
            ))
            bonds = tuple(sorted(
                _bond_signature(
                    str(bond.get("type") or "normal"),
                    _transform(bond.get("from") or (0, 0), origin, rotation),
                    _transform(bond.get("to") or (0, 0), origin, rotation),
                )
                for bond in product.get("bonds", [])
            ))
            simulator.output_patterns.append((str(part.get("id")), product_index, atoms, bonds))
        return simulator

    def step(self, instructions: dict[str, str | None]) -> dict[str, Any]:
        self._active_instructions = dict(instructions)
        for arm_id, instruction in instructions.items():
            if instruction not in RESET:
                continue
            arm = self.arms.get(arm_id)
            if arm is not None:
                self._drop(arm)
        return super().step(instructions)

    def _validate_and_apply(self, proposals) -> None:
        try:
            super()._validate_and_apply(proposals)
        except SimulationError as error:
            held = {
                arm_id: {
                    "instruction": self._active_instructions.get(arm_id),
                    "heldAtoms": sorted(self._held_atom_ids(arm)),
                }
                for arm_id, arm in sorted(self.arms.items())
                if arm.held_atoms
            }
            raise SimulationError(f"{error}; activeArms={held}") from error

    def _molecule_signature(self, atom_ids: set[str]) -> tuple[tuple, tuple]:
        atoms = tuple(sorted(
            (self.world.atoms[atom_id].position, self.world.atoms[atom_id].element)
            for atom_id in atom_ids
        ))
        bonds = tuple(sorted(
            _bond_signature(
                bond.kind,
                self.world.atoms[bond.a].position,
                self.world.atoms[bond.b].position,
            )
            for bond in self.world.bonds.values()
            if bond.a in atom_ids and bond.b in atom_ids
        ))
        return atoms, bonds

    def _remove_molecule(self, atom_ids: set[str]) -> None:
        for atom_id in list(atom_ids):
            for arm in self.arms.values():
                for branch, held_atom_id in list(arm.held_atoms.items()):
                    if held_atom_id == atom_id:
                        del arm.held_atoms[branch]
                if not arm.held_atoms:
                    arm.grabbing = False
            self.world.remove_atom(atom_id)

    def _process_consumers(self) -> None:
        consumed: set[str] = set()

        if self.disposal_cells:
            for molecule in self.world.molecules():
                if any(self.world.atoms[atom_id].position in self.disposal_cells for atom_id in molecule.atom_ids):
                    consumed.update(molecule.atom_ids)
                    self.world.events.append(WorldEvent("molecule-consumed", self.world.cycle, {
                        "consumerType": "glyph-disposal",
                        "atomIds": sorted(molecule.atom_ids),
                    }))

        for output_id, product_index, expected_atoms, expected_bonds in self.output_patterns:
            for molecule in self.world.molecules():
                if molecule.atom_ids & consumed:
                    continue
                if any(self.world.atoms[atom_id].held_by for atom_id in molecule.atom_ids):
                    continue
                atoms, bonds = self._molecule_signature(molecule.atom_ids)
                if atoms != expected_atoms or bonds != expected_bonds:
                    continue
                consumed.update(molecule.atom_ids)
                self.delivered_products[output_id] = self.delivered_products.get(output_id, 0) + 1
                self.world.events.append(WorldEvent("product-delivered", self.world.cycle, {
                    "consumerType": "output",
                    "consumerPartId": output_id,
                    "productIndex": product_index,
                    "atomIds": sorted(molecule.atom_ids),
                }))
                break

        if consumed:
            self._remove_molecule(consumed)

    def _respawn_inputs(self) -> None:
        self._process_consumers()
        super()._respawn_inputs()
