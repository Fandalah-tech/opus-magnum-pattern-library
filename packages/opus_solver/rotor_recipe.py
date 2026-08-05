from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceAtom:
    pull_id: str
    reagent_index: int
    atom_index: int
    source_element: str


@dataclass(frozen=True, slots=True)
class TargetAtom:
    atom_id: str
    position: tuple[int, int]
    target_element: str
    component_index: int


@dataclass(frozen=True, slots=True)
class AtomAssignment:
    source: SourceAtom
    target: TargetAtom
    transformation: str | None


@dataclass(frozen=True, slots=True)
class RotorRecipe:
    supported: bool
    reason: str | None
    reagent_pulls: tuple[int, ...]
    assignments: tuple[AtomAssignment, ...]
    transformation_count: int
    preserved_components: tuple[int, ...]
    mixed_components: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pos(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _product_components(product: dict[str, Any]) -> list[set[tuple[int, int]]]:
    positions = {_pos(atom.get("position")) for atom in product.get("atoms") or []}
    adjacency = {position: set() for position in positions}
    for bond in product.get("bonds") or []:
        first = _pos(bond.get("from"))
        second = _pos(bond.get("to"))
        adjacency[first].add(second)
        adjacency[second].add(first)
    result: list[set[tuple[int, int]]] = []
    remaining = set(positions)
    while remaining:
        root = min(remaining)
        stack = [root]
        component: set[tuple[int, int]] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            remaining.discard(current)
            stack.extend(adjacency[current] - component)
        result.append(component)
    return sorted(result, key=lambda item: (len(item), sorted(item)))


def _conversion(source: str, target: str) -> str | None | bool:
    if source == target:
        return None
    if source == "salt" and target in {"air", "earth", "fire", "water"}:
        return "van-berlo"
    return False


def build_rotor_recipe(
    puzzle: dict[str, Any],
    *,
    reagent_pulls: tuple[int, ...] = (2, 3),
    product_index: int = 0,
) -> RotorRecipe:
    """Assign concrete reagent atoms to the Rotor product.

    The search minimizes Van Berlo transformations first, then the number of
    bonded product components assembled from more than one reagent pull. This
    is a chemistry and provenance plan; it does not yet place machine parts.
    """
    products = list(puzzle.get("products") or [])
    reagents = list(puzzle.get("reagents") or [])
    if not 0 <= product_index < len(products):
        return RotorRecipe(False, "product index is out of range", reagent_pulls, (), 0, (), ())
    if len(reagent_pulls) != len(reagents):
        return RotorRecipe(False, "reagent pull vector does not match reagent count", reagent_pulls, (), 0, (), ())

    product_model = products[product_index]
    components = _product_components(product_model)
    component_by_position = {
        position: index
        for index, component in enumerate(components)
        for position in component
    }
    targets = [
        TargetAtom(
            str(atom.get("id") or f"a{index}"),
            _pos(atom.get("position")),
            str(atom.get("element") or ""),
            component_by_position[_pos(atom.get("position"))],
        )
        for index, atom in enumerate(product_model.get("atoms") or [])
    ]
    sources: list[SourceAtom] = []
    for reagent_index, pull_count in enumerate(reagent_pulls):
        reagent_atoms = list(reagents[reagent_index].get("atoms") or [])
        for pull in range(pull_count):
            pull_id = f"r{reagent_index}-p{pull}"
            for atom_index, atom in enumerate(reagent_atoms):
                sources.append(SourceAtom(
                    pull_id,
                    reagent_index,
                    atom_index,
                    str(atom.get("element") or ""),
                ))

    if len(sources) != len(targets):
        return RotorRecipe(
            False,
            f"source atom count {len(sources)} does not match product atom count {len(targets)}",
            reagent_pulls,
            (),
            0,
            (),
            (),
        )

    candidates = [
        [index for index, target in enumerate(targets) if _conversion(source.source_element, target.target_element) is not False]
        for source in sources
    ]
    order = sorted(range(len(sources)), key=lambda index: len(candidates[index]))
    best: tuple[tuple[int, int], list[AtomAssignment]] | None = None

    def visit(depth: int, used: set[int], assignments: list[AtomAssignment]) -> None:
        nonlocal best
        if depth == len(order):
            component_pulls: dict[int, set[str]] = {}
            transforms = 0
            for assignment in assignments:
                component_pulls.setdefault(assignment.target.component_index, set()).add(assignment.source.pull_id)
                transforms += assignment.transformation is not None
            mixed = sum(1 for pulls in component_pulls.values() if len(pulls) > 1)
            score = (transforms, mixed)
            if best is None or score < best[0]:
                best = score, list(assignments)
            return

        source_index = order[depth]
        source = sources[source_index]
        for target_index in candidates[source_index]:
            if target_index in used:
                continue
            target = targets[target_index]
            transformation = _conversion(source.source_element, target.target_element)
            assert transformation is not False
            partial_transforms = sum(item.transformation is not None for item in assignments) + (transformation is not None)
            if best is not None and partial_transforms > best[0][0]:
                continue
            used.add(target_index)
            assignments.append(AtomAssignment(source, target, transformation))
            visit(depth + 1, used, assignments)
            assignments.pop()
            used.remove(target_index)

    visit(0, set(), [])
    if best is None:
        return RotorRecipe(False, "no legal atom assignment exists", reagent_pulls, (), 0, (), ())

    _, assignments = best
    component_pulls: dict[int, set[str]] = {}
    for assignment in assignments:
        component_pulls.setdefault(assignment.target.component_index, set()).add(assignment.source.pull_id)
    preserved = tuple(sorted(index for index, pulls in component_pulls.items() if len(pulls) == 1))
    mixed = tuple(sorted(index for index, pulls in component_pulls.items() if len(pulls) > 1))
    ordered_assignments = tuple(sorted(assignments, key=lambda item: item.target.atom_id))
    return RotorRecipe(
        True,
        None,
        reagent_pulls,
        ordered_assignments,
        sum(item.transformation is not None for item in ordered_assignments),
        preserved,
        mixed,
    )
