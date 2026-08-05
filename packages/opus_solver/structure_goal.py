from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from packages.opus_engine.builder import rotate_hex

Hex = tuple[int, int]
Edge = tuple[Hex, Hex]


def _canon_edge(a: Hex, b: Hex) -> Edge:
    return (a, b) if a <= b else (b, a)


def _normalize_positions(positions: Iterable[Hex]) -> tuple[Hex, ...]:
    points = tuple(positions)
    if not points:
        return ()
    anchor = min(points)
    return tuple(sorted((q - anchor[0], r - anchor[1]) for q, r in points))


def _normalize_edges(edges: Iterable[Edge]) -> tuple[Edge, ...]:
    materialized = tuple(edges)
    if not materialized:
        return ()
    points = [point for edge in materialized for point in edge]
    anchor = min(points)
    shifted = [
        _canon_edge(
            (a[0] - anchor[0], a[1] - anchor[1]),
            (b[0] - anchor[0], b[1] - anchor[1]),
        )
        for a, b in materialized
    ]
    return tuple(sorted(shifted))


def _rotations(points: Iterable[Hex]) -> tuple[tuple[Hex, ...], ...]:
    source = tuple(points)
    return tuple(_normalize_positions(rotate_hex(point, steps) for point in source) for steps in range(6))


def _edge_rotations(edges: Iterable[Edge]) -> tuple[tuple[Edge, ...], ...]:
    source = tuple(edges)
    return tuple(
        _normalize_edges((rotate_hex(a, steps), rotate_hex(b, steps)) for a, b in source)
        for steps in range(6)
    )


@dataclass(frozen=True, slots=True)
class StructureGoal:
    atom_count: int
    bond_count: int
    position_variants: tuple[tuple[Hex, ...], ...]
    edge_variants: tuple[tuple[Edge, ...], ...]

    @classmethod
    def from_product(cls, product: dict[str, Any]) -> "StructureGoal":
        atoms = product.get("atoms", [])
        positions = [tuple(atom["position"]) for atom in atoms]
        by_position = {tuple(atom["position"]): atom for atom in atoms}
        edges: list[Edge] = []
        for bond in product.get("bonds", []):
            a = tuple(bond.get("from") or ())
            b = tuple(bond.get("to") or ())
            if a in by_position and b in by_position:
                edges.append(_canon_edge(a, b))
        return cls(
            atom_count=len(positions),
            bond_count=len(edges),
            position_variants=_rotations(positions),
            edge_variants=_edge_rotations(edges),
        )

    def world_positions(self, simulator: Any) -> tuple[Hex, ...]:
        return _normalize_positions(tuple(atom.position) for atom in simulator.world.atoms.values())

    def world_edges(self, simulator: Any) -> tuple[Edge, ...]:
        edges = []
        for bond in simulator.world.bonds.values():
            a = simulator.world.atoms[bond.a].position
            b = simulator.world.atoms[bond.b].position
            edges.append(_canon_edge(a, b))
        return _normalize_edges(edges)

    def reached(self, simulator: Any) -> bool:
        if len(simulator.world.atoms) != self.atom_count:
            return False
        if len(simulator.world.bonds) != self.bond_count:
            return False
        return (
            self.world_positions(simulator) in self.position_variants
            and self.world_edges(simulator) in self.edge_variants
        )

    def score(self, simulator: Any) -> int:
        """Higher is better; elements and Van Berlo state are intentionally ignored."""
        atoms = tuple(simulator.world.atoms.values())
        bonds = tuple(simulator.world.bonds.values())
        count_score = -abs(self.atom_count - len(atoms)) * 40
        bond_count_score = -abs(self.bond_count - len(bonds)) * 60

        world_positions = set(self.world_positions(simulator))
        position_overlap = max(
            (len(world_positions.intersection(variant)) for variant in self.position_variants),
            default=0,
        )
        world_edges = set(self.world_edges(simulator))
        edge_overlap = max(
            (len(world_edges.intersection(variant)) for variant in self.edge_variants),
            default=0,
        )
        return count_score + bond_count_score + position_overlap * 8 + edge_overlap * 30
