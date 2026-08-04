from __future__ import annotations

from dataclasses import dataclass, field

from .model import Atom, Bond, Hex, Molecule, connected_components


@dataclass(slots=True)
class WorldEvent:
    kind: str
    cycle: int
    data: dict = field(default_factory=dict)


@dataclass(slots=True)
class World:
    cycle: int = 0
    atoms: dict[str, Atom] = field(default_factory=dict)
    bonds: dict[tuple[str, str, str], Bond] = field(default_factory=dict)
    events: list[WorldEvent] = field(default_factory=list)

    def add_atom(self, atom: Atom) -> None:
        if atom.id in self.atoms:
            raise ValueError(f"Duplicate atom id: {atom.id}")
        occupant = self.atom_at(atom.position)
        if occupant is not None:
            raise ValueError(f"Hex {atom.position} is already occupied by {occupant.id}")
        self.atoms[atom.id] = atom

    def remove_atom(self, atom_id: str) -> None:
        if atom_id not in self.atoms:
            return
        del self.atoms[atom_id]
        for key in [key for key, bond in self.bonds.items() if atom_id in (bond.a, bond.b)]:
            del self.bonds[key]

    def add_bond(self, bond: Bond) -> None:
        if bond.a not in self.atoms or bond.b not in self.atoms:
            raise ValueError("Both bonded atoms must exist in the world")
        self.bonds[bond.key] = bond

    def remove_bond(self, a: str, b: str, kind: str | None = None) -> None:
        first, second = sorted((a, b))
        for key in list(self.bonds):
            if key[0] == first and key[1] == second and (kind is None or key[2] == kind):
                del self.bonds[key]

    def atom_at(self, position: Hex) -> Atom | None:
        return next((atom for atom in self.atoms.values() if atom.position == position), None)

    def occupied(self) -> dict[Hex, str]:
        return {atom.position: atom.id for atom in self.atoms.values()}

    def molecules(self) -> list[Molecule]:
        result: list[Molecule] = []
        for index, component in enumerate(connected_components(self.atoms, self.bonds.values())):
            keys = {
                key for key, bond in self.bonds.items()
                if bond.a in component and bond.b in component
            }
            result.append(Molecule(id=f"molecule-{index}", atom_ids=component, bond_keys=keys))
        return result

    def snapshot(self) -> dict:
        molecules = self.molecules()
        return {
            "cycle": self.cycle,
            "atoms": [
                {
                    "id": atom.id,
                    "element": atom.element,
                    "position": list(atom.position),
                    "heldBy": sorted(atom.held_by),
                }
                for atom in sorted(self.atoms.values(), key=lambda item: item.id)
            ],
            "bonds": [
                {"fromAtomId": bond.a, "toAtomId": bond.b, "type": bond.kind}
                for bond in sorted(self.bonds.values(), key=lambda item: item.key)
            ],
            "molecules": [
                {
                    "id": molecule.id,
                    "atomIds": sorted(molecule.atom_ids),
                    "bondKeys": [list(key) for key in sorted(molecule.bond_keys)],
                }
                for molecule in molecules
            ],
        }
