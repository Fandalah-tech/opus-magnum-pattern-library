from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

Hex = tuple[int, int]


@dataclass(slots=True)
class Atom:
    id: str
    element: str
    position: Hex
    held_by: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class Bond:
    a: str
    b: str
    kind: str = "normal"

    def __post_init__(self) -> None:
        if self.a == self.b:
            raise ValueError("A bond must connect two distinct atoms")

    @property
    def key(self) -> tuple[str, str, str]:
        first, second = sorted((self.a, self.b))
        return first, second, self.kind


@dataclass(slots=True)
class Molecule:
    id: str
    atom_ids: set[str]
    bond_keys: set[tuple[str, str, str]]


def connected_components(atom_ids: Iterable[str], bonds: Iterable[Bond]) -> list[set[str]]:
    atoms = set(atom_ids)
    adjacency = {atom_id: set() for atom_id in atoms}
    for bond in bonds:
        if bond.a in atoms and bond.b in atoms:
            adjacency[bond.a].add(bond.b)
            adjacency[bond.b].add(bond.a)

    components: list[set[str]] = []
    unseen = set(atoms)
    while unseen:
        start = unseen.pop()
        component = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components
