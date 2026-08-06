from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.opus_engine.builder import rotate_hex

Hex = tuple[int, int]
Edge = tuple[Hex, Hex]


def _canon_edge(a: Hex, b: Hex) -> Edge:
    return (a, b) if a <= b else (b, a)


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
    include_baron_held: bool = False

    @classmethod
    def from_product(
        cls,
        product: dict[str, Any],
        *,
        include_baron_held: bool = False,
    ) -> "StructureGoal":
        positions = [tuple(atom["position"]) for atom in product.get("atoms", [])]
        known = set(positions)
        edges = [
            _canon_edge(tuple(bond.get("from") or ()), tuple(bond.get("to") or ()))
            for bond in product.get("bonds", [])
            if tuple(bond.get("from") or ()) in known and tuple(bond.get("to") or ()) in known
        ]
        position_variants: list[tuple[Hex, ...]] = []
        edge_variants: list[tuple[Edge, ...]] = []
        for steps in range(6):
            rotated_positions = [rotate_hex(point, steps) for point in positions]
            anchor = min(rotated_positions, default=(0, 0))

            def shift(point: Hex) -> Hex:
                return point[0] - anchor[0], point[1] - anchor[1]

            position_variants.append(tuple(sorted(shift(point) for point in rotated_positions)))
            edge_variants.append(tuple(sorted(
                _canon_edge(shift(rotate_hex(a, steps)), shift(rotate_hex(b, steps)))
                for a, b in edges
            )))
        return cls(
            len(positions),
            len(edges),
            tuple(position_variants),
            tuple(edge_variants),
            include_baron_held,
        )

    def _eligible_atom_ids(self, simulator: Any) -> set[str]:
        if self.include_baron_held:
            return set(simulator.world.atoms)
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
        occupied = {simulator.world.atoms[atom_id].position for atom_id in eligible}
        world_edges = {
            _canon_edge(simulator.world.atoms[bond.a].position, simulator.world.atoms[bond.b].position)
            for bond in simulator.world.bonds.values()
            if bond.a in eligible and bond.b in eligible
        }
        if not occupied:
            return StructureMatch(0, 0, (0, 0), 0)

        best = StructureMatch(0, 0, (0, 0), 0)
        for rotation, (positions, edges) in enumerate(zip(self.position_variants, self.edge_variants, strict=True)):
            translations: set[Hex] = set()
            for world_a, world_b in world_edges:
                for target_a, target_b in edges:
                    translations.add((world_a[0] - target_a[0], world_a[1] - target_a[1]))
                    translations.add((world_a[0] - target_b[0], world_a[1] - target_b[1]))
            probes = (positions[0], positions[len(positions) // 2], positions[-1])
            for world in occupied:
                for target in probes:
                    translations.add((world[0] - target[0], world[1] - target[1]))

            for translation in translations:
                tq, tr = translation
                shifted_positions = {(q + tq, r + tr) for q, r in positions}
                occupied_count = len(shifted_positions.intersection(occupied))
                shifted_edges = {
                    _canon_edge((a[0] + tq, a[1] + tr), (b[0] + tq, b[1] + tr))
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
        match = self.best_match(simulator)
        eligible = self._eligible_atom_ids(simulator)
        live_bonds = sum(
            1 for bond in simulator.world.bonds.values()
            if bond.a in eligible and bond.b in eligible
        )
        excess_atoms = max(0, len(eligible) - self.atom_count)
        return (
            match.occupied_positions * 24
            + match.matched_edges * 140
            + min(live_bonds, self.bond_count) * 4
            - excess_atoms * 10
        )
