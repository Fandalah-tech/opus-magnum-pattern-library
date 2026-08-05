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
    molecule_groups: dict[str, set[str]] = field(default_factory=dict)
    atom_molecule: dict[str, str] = field(default_factory=dict)
    _molecule_generation: int = 0

    def _next_molecule_id(self, prefix: str = "molecule") -> str:
        result = f"{prefix}-{self._molecule_generation}"
        self._molecule_generation += 1
        return result

    def register_molecule(self, atom_ids: set[str] | list[str] | tuple[str, ...], molecule_id: str | None = None) -> str:
        members = {atom_id for atom_id in atom_ids if atom_id in self.atoms}
        if not members:
            raise ValueError("Cannot register an empty molecule")
        existing = {self.atom_molecule[atom_id] for atom_id in members if atom_id in self.atom_molecule}
        for group_id in existing:
            members.update(self.molecule_groups.pop(group_id, set()))
        result = molecule_id or self._next_molecule_id()
        if result in self.molecule_groups:
            members.update(self.molecule_groups.pop(result))
        self.molecule_groups[result] = members
        for atom_id in members:
            self.atom_molecule[atom_id] = result
        return result

    def molecule_atom_ids(self, atom_id: str) -> set[str]:
        group_id = self.atom_molecule.get(atom_id)
        if group_id is None:
            return {atom_id} if atom_id in self.atoms else set()
        return set(self.molecule_groups.get(group_id, {atom_id}))

    def merge_molecules(self, first_atom_id: str, second_atom_id: str) -> str:
        members = self.molecule_atom_ids(first_atom_id) | self.molecule_atom_ids(second_atom_id)
        return self.register_molecule(members)

    def recalculate_molecule(self, atom_id: str, *, excluded_bond_keys: set[tuple[str, str, str]] | None = None) -> None:
        members = self.molecule_atom_ids(atom_id)
        if not members:
            return
        old_group = self.atom_molecule.get(atom_id)
        if old_group is not None:
            self.molecule_groups.pop(old_group, None)
        for member in members:
            self.atom_molecule.pop(member, None)
        excluded = excluded_bond_keys or set()
        bonds = [
            bond for key, bond in self.bonds.items()
            if key not in excluded and bond.a in members and bond.b in members
        ]
        for component in connected_components(members, bonds):
            self.register_molecule(set(component))

    def add_atom(self, atom: Atom) -> None:
        if atom.id in self.atoms:
            raise ValueError(f"Duplicate atom id: {atom.id}")
        occupant = self.atom_at(atom.position)
        if occupant is not None:
            raise ValueError(f"Hex {atom.position} is already occupied by {occupant.id}")
        self.atoms[atom.id] = atom
        self.register_molecule({atom.id})

    def remove_atom(self, atom_id: str) -> None:
        if atom_id not in self.atoms:
            return
        group_id = self.atom_molecule.pop(atom_id, None)
        if group_id is not None:
            members = self.molecule_groups.get(group_id)
            if members is not None:
                members.discard(atom_id)
                if not members:
                    self.molecule_groups.pop(group_id, None)
        del self.atoms[atom_id]
        for key in [key for key, bond in self.bonds.items() if atom_id in (bond.a, bond.b)]:
            del self.bonds[key]

    def add_bond(self, bond: Bond, *, merge_molecules: bool = True) -> None:
        if bond.a not in self.atoms or bond.b not in self.atoms:
            raise ValueError("Both bonded atoms must exist in the world")
        self.bonds[bond.key] = bond
        if merge_molecules:
            self.merge_molecules(bond.a, bond.b)

    def remove_bond(self, a: str, b: str, kind: str | None = None, *, recalculate: bool = True) -> bool:
        first, second = sorted((a, b))
        removed = False
        affected = a if a in self.atoms else b
        for key in list(self.bonds):
            if key[0] == first and key[1] == second and (kind is None or key[2] == kind):
                del self.bonds[key]
                removed = True
        if removed and recalculate and affected in self.atoms:
            # Opus Magnum disjoint semantics: any successful debond causes the
            # entire logical molecule to be rebuilt from its bond network.
            self.recalculate_molecule(affected)
        return removed

    def atom_at(self, position: Hex) -> Atom | None:
        return next((atom for atom in self.atoms.values() if atom.position == position), None)

    def occupied(self) -> dict[Hex, str]:
        return {atom.position: atom.id for atom in self.atoms.values()}

    def molecules(self) -> list[Molecule]:
        result: list[Molecule] = []
        represented: set[str] = set()
        for group_id, members in sorted(self.molecule_groups.items()):
            live = {atom_id for atom_id in members if atom_id in self.atoms}
            if not live:
                continue
            represented.update(live)
            keys = {
                key for key, bond in self.bonds.items()
                if bond.a in live and bond.b in live
            }
            result.append(Molecule(id=group_id, atom_ids=live, bond_keys=keys))
        for atom_id in sorted(set(self.atoms) - represented):
            result.append(Molecule(id=self._next_molecule_id(), atom_ids={atom_id}, bond_keys=set()))
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
                    "moleculeId": self.atom_molecule.get(atom.id),
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
