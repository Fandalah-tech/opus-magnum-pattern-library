from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


Hex = tuple[int, int]


@dataclass(frozen=True, slots=True)
class ProductComponent:
    atom_ids: tuple[str, ...]
    positions: tuple[Hex, ...]
    elements: tuple[str, ...]
    bond_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DisjointProductPlan:
    supported: bool
    reason: str | None
    product_index: int
    components: tuple[ProductComponent, ...]
    element_demand: tuple[tuple[str, int], ...]
    reagent_element_supply: tuple[tuple[int, tuple[tuple[str, int], ...]], ...]
    required_transmutations: int
    required_bonds: int
    isolated_atoms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _position(value: Any) -> Hex:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _components(product: dict[str, Any]) -> tuple[ProductComponent, ...]:
    atoms = list(product.get("atoms") or [])
    by_position = {_position(atom.get("position")): atom for atom in atoms}
    adjacency: dict[Hex, set[Hex]] = {position: set() for position in by_position}
    bonds = list(product.get("bonds") or [])
    for bond in bonds:
        first = _position(bond.get("from"))
        second = _position(bond.get("to"))
        if first not in adjacency or second not in adjacency:
            raise ValueError("Product bond references an unknown atom position")
        adjacency[first].add(second)
        adjacency[second].add(first)

    remaining = set(adjacency)
    result: list[ProductComponent] = []
    while remaining:
        start = min(remaining)
        stack = [start]
        positions: set[Hex] = set()
        while stack:
            current = stack.pop()
            if current in positions:
                continue
            positions.add(current)
            remaining.discard(current)
            stack.extend(adjacency[current] - positions)
        ordered = tuple(sorted(positions))
        atom_ids = tuple(str(by_position[position].get("id") or "") for position in ordered)
        elements = tuple(str(by_position[position].get("element") or "") for position in ordered)
        component_bonds = sum(
            1
            for bond in bonds
            if _position(bond.get("from")) in positions
            and _position(bond.get("to")) in positions
        )
        result.append(ProductComponent(atom_ids, ordered, elements, component_bonds))
    return tuple(sorted(result, key=lambda item: (len(item.atom_ids), item.positions)))


def build_disjoint_product_plan(puzzle: dict[str, Any], product_index: int = 0) -> DisjointProductPlan:
    products = list(puzzle.get("products") or [])
    reagents = list(puzzle.get("reagents") or [])
    if not 0 <= product_index < len(products):
        return DisjointProductPlan(False, "product index is out of range", product_index, (), (), (), 0, 0, 0)
    if not reagents:
        return DisjointProductPlan(False, "puzzle has no reagents", product_index, (), (), (), 0, 0, 0)

    product = products[product_index]
    components = _components(product)
    demand = Counter(str(atom.get("element") or "") for atom in product.get("atoms") or [])
    supply = tuple(
        (
            index,
            tuple(sorted(Counter(
                str(atom.get("element") or "")
                for atom in reagent.get("atoms") or []
            ).items())),
        )
        for index, reagent in enumerate(reagents)
    )

    direct_classical = sum(
        count
        for element, count in Counter(
            str(atom.get("element") or "")
            for reagent in reagents
            for atom in reagent.get("atoms") or []
        ).items()
        if element in {"air", "earth", "fire", "water"}
    )
    classical_demand = sum(demand[element] for element in ("air", "earth", "fire", "water"))
    # This is a chemistry lower bound, not a scheduling claim: every demanded
    # classical atom not already present in one complete reagent set must be
    # created by Van Berlo or another conversion glyph.
    required_transmutations = max(0, classical_demand - direct_classical)

    return DisjointProductPlan(
        supported=True,
        reason=None,
        product_index=product_index,
        components=components,
        element_demand=tuple(sorted(demand.items())),
        reagent_element_supply=supply,
        required_transmutations=required_transmutations,
        required_bonds=len(product.get("bonds") or []),
        isolated_atoms=sum(1 for component in components if len(component.atom_ids) == 1),
    )
