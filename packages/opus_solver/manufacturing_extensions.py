from __future__ import annotations

from collections import Counter
from typing import Any

from .manufacturing import (
    CLASSICAL_ELEMENTS,
    ManufacturingOperation,
    ManufacturingPlan,
    build_manufacturing_plan as build_base_manufacturing_plan,
)


def _position(atom: dict[str, Any]) -> tuple[int, int]:
    raw = atom.get("position") or (0, 0)
    return int(raw[0]), int(raw[1])


def _normal_induced_topology(
    molecule: dict[str, Any],
    selected_positions: set[tuple[int, int]] | None = None,
) -> tuple[int, int, tuple[int, ...]] | None:
    atom_positions = {_position(atom) for atom in molecule.get("atoms") or ()}
    selected = atom_positions if selected_positions is None else set(selected_positions)
    if not selected or not selected.issubset(atom_positions):
        return None
    degrees = Counter({position: 0 for position in selected})
    bond_count = 0
    for bond in molecule.get("bonds") or ():
        if str(bond.get("type") or "normal") != "normal":
            return None
        first = _position({"position": bond.get("from")})
        second = _position({"position": bond.get("to")})
        if first in selected and second in selected:
            if first == second:
                return None
            degrees[first] += 1
            degrees[second] += 1
            bond_count += 1
    return len(selected), bond_count, tuple(sorted(degrees.values()))


def paired_bonded_clusters_plan(puzzle: dict[str, Any]) -> ManufacturingPlan | None:
    """Recognize two homologous bonded clusters, one preserved and one calcified.

    This is deliberately chemistry/topology driven rather than keyed to a
    puzzle name or file hash.  Two identical homogeneous classical-element
    reagents may form a product containing one unchanged copy and one
    bond-preserving salt copy, with one or more new normal bonds between the
    two clusters.
    """

    products = list(puzzle.get("products") or ())
    reagents = list(puzzle.get("reagents") or ())
    available_glyphs = set((puzzle.get("availableParts") or {}).get("glyphs") or ())
    if len(products) != 1 or len(reagents) != 2:
        return None
    if not {"bonder", "calcification"}.issubset(available_glyphs):
        return None

    profiles: list[tuple[str, tuple[int, int, tuple[int, ...]]]] = []
    for reagent in reagents:
        atoms = list(reagent.get("atoms") or ())
        if len(atoms) < 2:
            return None
        elements = {str(atom.get("element") or "") for atom in atoms}
        if len(elements) != 1:
            return None
        source_element = next(iter(elements))
        if source_element not in CLASSICAL_ELEMENTS:
            return None
        topology = _normal_induced_topology(reagent)
        if topology is None:
            return None
        profiles.append((source_element, topology))
    if profiles[0] != profiles[1]:
        return None

    source_element, reagent_topology = profiles[0]
    cluster_size = reagent_topology[0]
    product = products[0]
    product_atoms = list(product.get("atoms") or ())
    if len(product_atoms) != cluster_size * 2:
        return None

    by_element: dict[str, set[tuple[int, int]]] = {}
    for atom in product_atoms:
        by_element.setdefault(str(atom.get("element") or ""), set()).add(_position(atom))
    if set(by_element) != {source_element, "salt"}:
        return None
    if len(by_element[source_element]) != cluster_size or len(by_element["salt"]) != cluster_size:
        return None
    if _normal_induced_topology(product, by_element[source_element]) != reagent_topology:
        return None
    if _normal_induced_topology(product, by_element["salt"]) != reagent_topology:
        return None

    cross_bonds: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for bond in product.get("bonds") or ():
        if str(bond.get("type") or "normal") != "normal":
            return None
        first = _position({"position": bond.get("from")})
        second = _position({"position": bond.get("to")})
        first_side = source_element if first in by_element[source_element] else "salt" if first in by_element["salt"] else None
        second_side = source_element if second in by_element[source_element] else "salt" if second in by_element["salt"] else None
        if first_side is None or second_side is None:
            return None
        if first_side != second_side:
            cross_bonds.append((first, second))
    if not cross_bonds:
        return None

    operations: list[ManufacturingOperation] = [
        ManufacturingOperation(
            "source-direct-cluster",
            "source",
            (),
            ("direct-cluster",),
            metadata={"reagentIndex": 0, "element": source_element, "atomCount": cluster_size},
        ),
        ManufacturingOperation(
            "source-calcified-cluster",
            "source",
            (),
            ("calcification-stage-0",),
            metadata={"reagentIndex": 1, "element": source_element, "atomCount": cluster_size},
        ),
    ]
    current = "calcification-stage-0"
    for index in range(cluster_size):
        transformed = f"calcification-stage-{index + 1}"
        operations.append(ManufacturingOperation(
            f"calcify-cluster-atom-{index}",
            "transform",
            (current,),
            (transformed,),
            glyph="glyph-calcification",
            metadata={
                "from": source_element,
                "to": "salt",
                "atomIndex": index,
                "preserveExistingBonds": True,
            },
        ))
        current = transformed

    assembled = "assembled-product-0"
    operations.append(ManufacturingOperation(
        "join-clusters-0",
        "bond",
        ("direct-cluster", current),
        (assembled,),
        glyph="bonder",
        metadata={"type": "normal", "crossBondIndex": 0},
    ))
    for index in range(1, len(cross_bonds)):
        next_stage = f"assembled-product-{index}"
        operations.append(ManufacturingOperation(
            f"join-clusters-{index}",
            "bond",
            (assembled,),
            (next_stage,),
            glyph="bonder",
            metadata={"type": "normal", "crossBondIndex": index},
        ))
        assembled = next_stage
    operations.append(ManufacturingOperation(
        "deliver-product",
        "deliver",
        (assembled,),
        ("output-0",),
    ))

    return ManufacturingPlan(
        strategy="paired-bonded-clusters-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=tuple(operations),
        required_glyphs=("bonder", "glyph-calcification"),
    )


def build_manufacturing_plan(puzzle: dict[str, Any]) -> ManufacturingPlan:
    """Route new bonded-cluster chemistry before the established planner."""

    cluster_plan = paired_bonded_clusters_plan(puzzle)
    if cluster_plan is not None:
        return cluster_plan
    return build_base_manufacturing_plan(puzzle)
