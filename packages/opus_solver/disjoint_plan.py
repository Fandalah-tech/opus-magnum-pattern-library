from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from functools import lru_cache
from itertools import product
from typing import Any


Hex = tuple[int, int]
CLASSICAL = {"air", "earth", "fire", "water"}


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
    reagent_pulls: tuple[int, ...]
    waste_atoms: int
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


def _conversion_cost(source: str, target: str) -> int | None:
    if source == target:
        return 0
    if source in CLASSICAL | {"salt"} and target in CLASSICAL:
        return 1
    if source in CLASSICAL and target == "salt":
        return 1
    return None


def _minimum_assignment_cost(source_elements: tuple[str, ...], demand: Counter[str]) -> int | None:
    targets = tuple(sorted(demand))
    initial = tuple(demand[target] for target in targets)

    @lru_cache(maxsize=None)
    def visit(index: int, remaining: tuple[int, ...]) -> int | None:
        if index == len(source_elements):
            return 0 if not any(remaining) else None
        source = source_elements[index]
        best = visit(index + 1, remaining)  # discard this atom
        for target_index, target in enumerate(targets):
            if remaining[target_index] <= 0:
                continue
            conversion = _conversion_cost(source, target)
            if conversion is None:
                continue
            updated = list(remaining)
            updated[target_index] -= 1
            suffix = visit(index + 1, tuple(updated))
            if suffix is None:
                continue
            candidate = conversion + suffix
            if best is None or candidate < best:
                best = candidate
        return best

    return visit(0, initial)


def _best_reagent_plan(reagents: list[dict[str, Any]], demand: Counter[str]) -> tuple[tuple[int, ...], int, int] | None:
    target_atoms = sum(demand.values())
    templates = [
        tuple(str(atom.get("element") or "") for atom in reagent.get("atoms") or [])
        for reagent in reagents
    ]
    if any(not template for template in templates):
        return None
    limits = [target_atoms // len(template) + 2 for template in templates]
    best: tuple[tuple[int, int, int, tuple[int, ...]], tuple[int, ...], int, int] | None = None
    for pulls in product(*(range(limit + 1) for limit in limits)):
        supplied = tuple(
            element
            for reagent_index, count in enumerate(pulls)
            for _ in range(count)
            for element in templates[reagent_index]
        )
        if len(supplied) < target_atoms:
            continue
        cost = _minimum_assignment_cost(supplied, demand)
        if cost is None:
            continue
        waste = len(supplied) - target_atoms
        score = (waste, sum(pulls), cost, pulls)
        if best is None or score < best[0]:
            best = score, pulls, waste, cost
    if best is None:
        return None
    return best[1], best[2], best[3]


def build_disjoint_product_plan(puzzle: dict[str, Any], product_index: int = 0) -> DisjointProductPlan:
    products = list(puzzle.get("products") or [])
    reagents = list(puzzle.get("reagents") or [])

    def unsupported(reason: str) -> DisjointProductPlan:
        return DisjointProductPlan(False, reason, product_index, (), (), (), (), 0, 0, 0, 0)

    if not 0 <= product_index < len(products):
        return unsupported("product index is out of range")
    if not reagents:
        return unsupported("puzzle has no reagents")

    product_model = products[product_index]
    components = _components(product_model)
    demand = Counter(str(atom.get("element") or "") for atom in product_model.get("atoms") or [])
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
    reagent_plan = _best_reagent_plan(reagents, demand)
    if reagent_plan is None:
        return unsupported("available reagent atoms cannot be assigned to the product")
    pulls, waste_atoms, required_transmutations = reagent_plan

    return DisjointProductPlan(
        supported=True,
        reason=None,
        product_index=product_index,
        components=components,
        element_demand=tuple(sorted(demand.items())),
        reagent_element_supply=supply,
        reagent_pulls=pulls,
        waste_atoms=waste_atoms,
        required_transmutations=required_transmutations,
        required_bonds=len(product_model.get("bonds") or []),
        isolated_atoms=sum(1 for component in components if len(component.atom_ids) == 1),
    )
