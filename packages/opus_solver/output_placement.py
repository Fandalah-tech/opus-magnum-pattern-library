from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from packages.opus_engine.builder import rotate_hex
from packages.opus_parser import expanded_bond_types


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _bond_signature(kind: str, first: tuple[int, int], second: tuple[int, int]) -> tuple[Any, ...]:
    a, b = sorted((first, second))
    return str(kind), a, b


def _product_pattern(product: dict[str, Any], rotation: int, origin: tuple[int, int]) -> tuple[Counter, Counter]:
    atoms = Counter()
    for atom in product.get("atoms", []) or []:
        local = _position(atom.get("position"))
        rotated = rotate_hex(local, rotation)
        world = (origin[0] + rotated[0], origin[1] + rotated[1])
        atoms[(world, str(atom.get("element") or ""))] += 1

    bonds = Counter()
    for bond in product.get("bonds", []) or []:
        first_local = rotate_hex(_position(bond.get("from")), rotation)
        second_local = rotate_hex(_position(bond.get("to")), rotation)
        first = (origin[0] + first_local[0], origin[1] + first_local[1])
        second = (origin[0] + second_local[0], origin[1] + second_local[1])
        for kind in expanded_bond_types(bond):
            bonds[_bond_signature(kind, first, second)] += 1
    return atoms, bonds


def _molecule_pattern(world: dict[str, Any], atom_ids: list[str]) -> tuple[Counter, Counter, bool]:
    by_id = {
        str(atom.get("id") or ""): atom
        for atom in world.get("atoms", []) or []
    }
    selected = [by_id[atom_id] for atom_id in atom_ids if atom_id in by_id]
    atoms = Counter(
        (_position(atom.get("position")), str(atom.get("element") or ""))
        for atom in selected
    )
    atom_set = set(atom_ids)
    bonds = Counter()
    for bond in world.get("bonds", []) or []:
        first_id = str(bond.get("fromAtomId") or "")
        second_id = str(bond.get("toAtomId") or "")
        if first_id not in atom_set or second_id not in atom_set:
            continue
        first = by_id.get(first_id)
        second = by_id.get(second_id)
        if first is None or second is None:
            continue
        bonds[_bond_signature(
            str(bond.get("type") or "normal"),
            _position(first.get("position")),
            _position(second.get("position")),
        )] += 1
    held = any(atom.get("heldBy") for atom in selected)
    return atoms, bonds, held


def _origins_for_match(
    product: dict[str, Any],
    molecule_atoms: Counter,
    rotation: int,
) -> list[tuple[int, int]]:
    product_atoms = list(product.get("atoms", []) or [])
    if not product_atoms or not molecule_atoms:
        return []
    candidates: set[tuple[int, int]] = set()
    for atom in product_atoms:
        element = str(atom.get("element") or "")
        local = rotate_hex(_position(atom.get("position")), rotation)
        for (world_position, world_element), count in molecule_atoms.items():
            if count <= 0 or world_element != element:
                continue
            candidates.add((world_position[0] - local[0], world_position[1] - local[1]))
    return sorted(candidates)


def product_output_opportunities(
    puzzle: dict[str, Any],
    replay: dict[str, Any],
    *,
    product_indices: set[int] | None = None,
    require_unheld: bool = True,
) -> list[dict[str, Any]]:
    """Find rigid output-glyph poses from molecules observed in generated replay.

    The puzzle product geometry is matched against complete replay molecules
    under all six rotations and translations.  No target solution geometry is
    consulted.  By default only unheld molecules are considered because a
    standard output cannot consume an atom currently held by an arm.
    """

    products = list(puzzle.get("products", []) or [])
    wanted = set(range(len(products))) if product_indices is None else set(product_indices)
    observations: dict[tuple[int, tuple[int, int], int], dict[str, Any]] = {}

    for frame in replay.get("frames", []) or []:
        cycle = int(frame.get("cycle") or 0)
        world = frame.get("world") or {}
        for molecule in world.get("molecules", []) or []:
            atom_ids = [str(value) for value in molecule.get("atomIds", []) or []]
            molecule_atoms, molecule_bonds, held = _molecule_pattern(world, atom_ids)
            if require_unheld and held:
                continue
            for product_index in sorted(wanted):
                if not 0 <= product_index < len(products):
                    continue
                product = products[product_index]
                if len(product.get("atoms", []) or []) != sum(molecule_atoms.values()):
                    continue
                for rotation in range(6):
                    for origin in _origins_for_match(product, molecule_atoms, rotation):
                        expected_atoms, expected_bonds = _product_pattern(product, rotation, origin)
                        if expected_atoms != molecule_atoms or expected_bonds != molecule_bonds:
                            continue
                        key = (product_index, origin, rotation)
                        item = observations.get(key)
                        if item is None:
                            item = {
                                "productIndex": product_index,
                                "origin": [origin[0], origin[1]],
                                "rotation": rotation,
                                "firstCycle": cycle,
                                "lastCycle": cycle,
                                "observationCount": 0,
                                "atomIds": atom_ids,
                                "held": held,
                                "evidence": "generated-replay-rigid-product-match",
                            }
                            observations[key] = item
                        item["observationCount"] = int(item["observationCount"]) + 1
                        item["firstCycle"] = min(int(item["firstCycle"]), cycle)
                        item["lastCycle"] = max(int(item["lastCycle"]), cycle)

    return sorted(
        observations.values(),
        key=lambda item: (
            int(item.get("productIndex") or 0),
            int(item.get("firstCycle") or 0),
            -int(item.get("observationCount") or 0),
            tuple(item.get("origin") or (0, 0)),
            int(item.get("rotation") or 0),
        ),
    )


def add_standard_output(
    solution: dict[str, Any],
    opportunity: dict[str, Any],
    *,
    part_id: str | None = None,
) -> dict[str, Any]:
    """Append one standard output at a replay-derived rigid product pose."""

    result = deepcopy(solution)
    existing_ids = {str(part.get("id") or "") for part in result.get("parts", []) or []}
    product_index = int(opportunity.get("productIndex") or 0)
    if part_id is None:
        serial = 0
        while f"generated-output-{product_index}-{serial}" in existing_ids:
            serial += 1
        part_id = f"generated-output-{product_index}-{serial}"
    result.setdefault("parts", []).append({
        "id": str(part_id),
        "type": "out-std",
        "enabled": True,
        "position": [int(value) for value in (opportunity.get("origin") or (0, 0))],
        "length": 1,
        "rotation": int(opportunity.get("rotation") or 0) % 6,
        "which": product_index,
        "armNumber": 0,
        "program": [],
    })
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/trace-guided-output-placement-v1"
    source.setdefault("outputPlacementRepairs", []).append({
        "productIndex": product_index,
        "partId": str(part_id),
        "opportunity": deepcopy(opportunity),
        "targetSolutionBytesUsed": 0,
    })
    return result


__all__ = [
    "add_standard_output",
    "product_output_opportunities",
]
