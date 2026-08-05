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
    return tuple(sorted(
        _canon_edge(
            (a[0] - anchor[0], a[1] - anchor[1]),
            (b[0] - anchor[0], b[1] - anchor[1]),
        )
        for a, b in materialized
    ))


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
class StructureMatch:
    occupied_positions: int
    matched_edges: int
    translation: Hex
    rotation: int


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

    def _eligible_atom_ids(self, simulator: Any) -> set[str]:
        baron_ids = {
            arm_id for arm_id, arm in getattr(simulator, "arms", {}).items()
            if getattr(arm, "part_type", "") == "baron"
        }
        return {
            atom_id for atom_id, atom in simulator.world.atoms.items()
            if not atom.held_by.intersection(baron_ids)
        }

    def best_match(self, simulator: Any) -> StructureMatch:
        eligible = self._eligible_atom_ids(simulator)
        occupied = {
            simulator.world.atoms[atom_id].position: atom_id
            for atom_id in eligible
        }
        world_edges = {
            _canon_edge(
                simulator.world.atoms[bond.a].position,
                simulator.world.atoms[bond.b].position,
            )
            for bond in simulator.world.bonds.values()
            if bond.a in eligible and bond.b in eligible
        }
        if not occupied:
            return StructureMatch(0, 0, (0, 0), 0)

        best = StructureMatch(0, 0, (0, 0), 0)
        world_positions = tuple(occupied)
        for rotation, (positions, edges) in enumerate(zip(self.position_variants, self.edge_variants, strict=True)):
            translations = {
                (world[0] - target[0], world[1] - target[1])
                for world in world_positions
                for target in positions
            }
            for translation in translations:
                shifted_positions = {
                    (point[0] + translation[0], point[1] + translation[1])
                    for point in positions
                }
                occupied_count = len(shifted_positions.intersection(occupied))
                shifted_edges = {
                    _canon_edge(
                        (a[0] + translation[0], a[1] + translation[1]),
                        (b[0] + translation[0], b[1] + translation[1]),
                    )
                    for a, b in edges
                }
                edge_count = len(shifted_edges.intersection(world_edges))
                candidate = StructureMatch(occupied_count, edge_count, translation, rotation)
                if (candidate.matched_edges, candidate.occupied_positions) > (best.matched_edges, best.occupied_positions):
                    best = candidate
        return best

    def reached(self, simulator: Any) -> bool:
        match = self.best_match(simulator)
        return match.occupied_positions == self.atom_count and match.matched_edges == self.bond_count

    def score(self, simulator: Any) -> int:
        """Higher is better; elements, spare reagents and Van Berlo wheel atoms are ignored."""
        match = self.best_match(simulator)
        return match.occupied_positions * 12 + match.matched_edges * 80
