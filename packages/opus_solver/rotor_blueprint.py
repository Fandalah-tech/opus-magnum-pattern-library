from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BlueprintAtom:
    target_position: tuple[int, int]
    target_element: str
    pull_id: str
    source_atom_index: int
    transformation: str | None


@dataclass(frozen=True, slots=True)
class RotorBlueprint:
    supported: bool
    reason: str | None
    atoms: tuple[BlueprintAtom, ...]
    pull_edges: tuple[tuple[str, str], ...]
    transformation_count: int
    connected: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _product_lookup(puzzle: dict[str, Any]) -> dict[tuple[int, int], str]:
    products = list(puzzle.get("products") or [])
    if len(products) != 1:
        return {}
    return {
        tuple(atom.get("position") or (0, 0)): str(atom.get("element") or "")
        for atom in products[0].get("atoms") or []
    }


def _is_connected(nodes: set[str], edges: set[tuple[str, str]]) -> bool:
    if not nodes:
        return False
    adjacency = {node: set() for node in nodes}
    for first, second in edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    seen = {min(nodes)}
    stack = list(seen)
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current] - seen:
            seen.add(neighbor)
            stack.append(neighbor)
    return seen == nodes


def build_connected_rotor_blueprint(puzzle: dict[str, Any]) -> RotorBlueprint:
    """Return a six-conversion recipe whose required product bonds merge all pulls.

    Pulls r0-p0/r0-p1 are Destabilized Water and r1-p0..p2 are
    Tripartite Salt. Every final dimer crosses pull boundaries, so the six
    permanent product bonds are sufficient to combine the five input logical
    molecules into one disjoint output molecule. No sacrificial merge bond is
    required by this blueprint.
    """
    expected = {
        (0, 0): "salt",
        (0, 2): "water",
        (-1, 2): "salt",
        (-2, 2): "air",
        (-2, 1): "water",
        (-1, -1): "air",
        (0, -2): "fire",
        (1, -2): "salt",
        (2, -2): "earth",
        (2, -1): "fire",
        (1, 1): "earth",
        (2, 0): "salt",
        (-2, 0): "salt",
    }
    if _product_lookup(puzzle) != expected:
        return RotorBlueprint(False, "puzzle product does not match Van Berlo's Rotor", (), (), 0, False)

    atoms = (
        BlueprintAtom((0, 0), "salt", "r1-p0", 2, None),
        BlueprintAtom((0, 2), "water", "r0-p1", 0, None),
        BlueprintAtom((-1, 2), "salt", "r1-p1", 1, None),
        BlueprintAtom((-2, 2), "air", "r1-p2", 0, "van-berlo"),
        BlueprintAtom((-2, 1), "water", "r0-p0", 0, None),
        BlueprintAtom((-1, -1), "air", "r1-p1", 2, "van-berlo"),
        BlueprintAtom((0, -2), "fire", "r1-p0", 1, "van-berlo"),
        BlueprintAtom((1, -2), "salt", "r0-p1", 1, None),
        BlueprintAtom((2, -2), "earth", "r1-p2", 1, "van-berlo"),
        BlueprintAtom((2, -1), "fire", "r1-p2", 2, "van-berlo"),
        BlueprintAtom((1, 1), "earth", "r1-p0", 0, "van-berlo"),
        BlueprintAtom((2, 0), "salt", "r0-p0", 1, None),
        BlueprintAtom((-2, 0), "salt", "r1-p1", 0, None),
    )

    bonds = [
        ((1, -2), (2, -2)),
        ((2, 0), (2, -1)),
        ((-2, 2), (-1, 2)),
        ((0, 2), (1, 1)),
        ((-1, -1), (0, -2)),
        ((-2, 1), (-2, 0)),
    ]
    pull_by_position = {atom.target_position: atom.pull_id for atom in atoms}
    edges = {
        tuple(sorted((pull_by_position[first], pull_by_position[second])))
        for first, second in bonds
        if pull_by_position[first] != pull_by_position[second]
    }
    nodes = {atom.pull_id for atom in atoms}
    connected = _is_connected(nodes, edges)
    transformations = sum(atom.transformation is not None for atom in atoms)
    if transformations != 6 or not connected:
        return RotorBlueprint(False, "internal Rotor blueprint invariant failed", atoms, tuple(sorted(edges)), transformations, connected)
    return RotorBlueprint(True, None, atoms, tuple(sorted(edges)), transformations, connected)
