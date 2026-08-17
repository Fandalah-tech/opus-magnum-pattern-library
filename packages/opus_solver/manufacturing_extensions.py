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


def _singleton_conversion(
    source: str,
    target: str,
    available_glyphs: set[str],
) -> tuple[int, str | None] | None:
    if source == target:
        return 0, None
    if target == "salt" and source in CLASSICAL_ELEMENTS and "calcification" in available_glyphs:
        return 1, "calcification"
    return None


def _ordered_connected_bonds(
    product: dict[str, Any],
) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
    """Order normal product bonds so one connected molecule can be assembled.

    The manufacturing planner only needs a dependency DAG, not a mechanical
    placement recipe.  Starting from one edge, prefer edges that attach one new
    atom to the already assembled component; cycle-closing edges are appended
    once all their endpoints are present.  Disconnected output graphs are left
    for a future multi-molecule strategy.
    """

    positions = {_position(atom) for atom in product.get("atoms") or ()}
    raw: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for bond in product.get("bonds") or ():
        if str(bond.get("type") or "normal") != "normal":
            return None
        first = _position({"position": bond.get("from")})
        second = _position({"position": bond.get("to")})
        if first == second or first not in positions or second not in positions:
            return None
        raw.append((first, second))
    if not raw:
        return None

    pending = list(raw)
    ordered = [pending.pop(0)]
    connected = set(ordered[0])
    while pending:
        attaching_index = next(
            (
                index
                for index, (first, second) in enumerate(pending)
                if (first in connected) ^ (second in connected)
            ),
            None,
        )
        if attaching_index is not None:
            first, second = pending.pop(attaching_index)
            ordered.append((first, second))
            connected.update((first, second))
            continue

        closing_index = next(
            (
                index
                for index, (first, second) in enumerate(pending)
                if first in connected and second in connected
            ),
            None,
        )
        if closing_index is not None:
            ordered.append(pending.pop(closing_index))
            continue
        return None

    return ordered if connected == positions else None


def repeated_singleton_assembly_plan(puzzle: dict[str, Any]) -> ManufacturingPlan | None:
    """Assemble a connected normal-bond product from reusable singleton inputs.

    Opus Magnum reagent glyphs are renewable sources: one reagent definition is
    not consumed after one spawn.  This strategy therefore assigns every target
    atom independently to the cheapest compatible singleton reagent and permits
    the same reagent index to feed any number of product atoms.  It is a generic
    chemistry rule, not a puzzle-specific shortcut.
    """

    products = list(puzzle.get("products") or ())
    reagents = list(puzzle.get("reagents") or ())
    available_glyphs = set((puzzle.get("availableParts") or {}).get("glyphs") or ())
    if len(products) != 1 or not reagents or "bonder" not in available_glyphs:
        return None
    if any(len(reagent.get("atoms") or ()) != 1 or reagent.get("bonds") for reagent in reagents):
        return None

    product = products[0]
    product_atoms = list(product.get("atoms") or ())
    if len(product_atoms) < 2:
        return None
    ordered_bonds = _ordered_connected_bonds(product)
    if ordered_bonds is None:
        return None

    singleton_sources = [
        (
            index,
            str(reagent["atoms"][0].get("id") or "a0"),
            str(reagent["atoms"][0].get("element") or ""),
        )
        for index, reagent in enumerate(reagents)
    ]

    assignments: dict[tuple[int, int], tuple[int, str, str, str | None]] = {}
    for product_atom in product_atoms:
        target = str(product_atom.get("element") or "")
        options: list[tuple[int, int, str, str, str | None]] = []
        for reagent_index, reagent_atom_id, source in singleton_sources:
            converted = _singleton_conversion(source, target, available_glyphs)
            if converted is None:
                continue
            cost, transformation = converted
            options.append((cost, reagent_index, reagent_atom_id, source, transformation))
        if not options:
            return None
        _, reagent_index, reagent_atom_id, source, transformation = min(
            options,
            key=lambda item: (item[0], item[1]),
        )
        assignments[_position(product_atom)] = (
            reagent_index,
            reagent_atom_id,
            source,
            transformation,
        )

    operations: list[ManufacturingOperation] = []
    product_ids: dict[tuple[int, int], str] = {}
    uses_calcification = False
    for index, product_atom in enumerate(product_atoms):
        position = _position(product_atom)
        target = str(product_atom.get("element") or "")
        reagent_index, reagent_atom_id, source, transformation = assignments[position]
        spawn_id = f"spawn-{index}"
        operations.append(ManufacturingOperation(
            id=f"source-product-atom-{index}",
            kind="source",
            inputs=(),
            outputs=(spawn_id,),
            metadata={
                "reagentIndex": reagent_index,
                "reagentAtomId": reagent_atom_id,
                "element": source,
                "reusableSource": True,
                "targetPosition": list(position),
            },
        ))
        current = spawn_id
        if transformation == "calcification":
            uses_calcification = True
            transformed = f"transformed-{index}"
            operations.append(ManufacturingOperation(
                id=f"calcify-product-atom-{index}",
                kind="transform",
                inputs=(current,),
                outputs=(transformed,),
                glyph="glyph-calcification",
                metadata={"from": source, "to": target, "targetPosition": list(position)},
            ))
            current = transformed
        placed = f"product-atom-{index}"
        product_ids[position] = placed
        operations.append(ManufacturingOperation(
            id=f"place-product-atom-{index}",
            kind="place",
            inputs=(current,),
            outputs=(placed,),
            metadata={"position": list(position), "element": target},
        ))

    assembled_positions: set[tuple[int, int]] = set()
    assembled_id: str | None = None
    for bond_index, (first, second) in enumerate(ordered_bonds):
        if assembled_id is None:
            inputs = (product_ids[first], product_ids[second])
            assembled_positions.update((first, second))
        else:
            new_positions = [position for position in (first, second) if position not in assembled_positions]
            inputs = (assembled_id, *(product_ids[position] for position in new_positions))
            assembled_positions.update((first, second))
        next_assembled = f"assembled-product-{bond_index}"
        operations.append(ManufacturingOperation(
            id=f"bond-product-{bond_index}",
            kind="bond",
            inputs=tuple(inputs),
            outputs=(next_assembled,),
            glyph="bonder",
            metadata={
                "type": "normal",
                "from": list(first),
                "to": list(second),
                "bondIndex": bond_index,
            },
        ))
        assembled_id = next_assembled

    operations.append(ManufacturingOperation(
        id="deliver-product",
        kind="deliver",
        inputs=(str(assembled_id),),
        outputs=("output-0",),
    ))

    required_glyphs = ["bonder"]
    if uses_calcification:
        required_glyphs.append("glyph-calcification")
    return ManufacturingPlan(
        strategy="repeated-singleton-assembly-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=tuple(operations),
        required_glyphs=tuple(required_glyphs),
    )


def paired_bonded_clusters_plan(puzzle: dict[str, Any]) -> ManufacturingPlan | None:
    """Recognize two homologous bonded clusters, one preserved and one calcified.

    This is deliberately chemistry/topology driven rather than keyed to a
    puzzle name or file hash. Two identical homogeneous classical-element
    reagents may form a product containing one unchanged copy and one
    bond-preserving salt copy, with one or more new normal bonds between the
    two clusters. Because the reagent molecules are homologous, their source
    indices are explicitly marked as interchangeable for later assembly reuse.
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

    interchangeable_group = "homologous-bonded-clusters"
    operations: list[ManufacturingOperation] = [
        ManufacturingOperation(
            "source-direct-cluster",
            "source",
            (),
            ("direct-cluster",),
            metadata={
                "reagentIndex": 0,
                "element": source_element,
                "atomCount": cluster_size,
                "branchRole": "direct",
                "interchangeableSourceGroup": interchangeable_group,
            },
        ),
        ManufacturingOperation(
            "source-calcified-cluster",
            "source",
            (),
            ("calcification-stage-0",),
            metadata={
                "reagentIndex": 1,
                "element": source_element,
                "atomCount": cluster_size,
                "branchRole": "calcifying",
                "interchangeableSourceGroup": interchangeable_group,
            },
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
    """Route generic chemistry extensions before the established planner."""

    cluster_plan = paired_bonded_clusters_plan(puzzle)
    if cluster_plan is not None:
        return cluster_plan
    singleton_plan = repeated_singleton_assembly_plan(puzzle)
    if singleton_plan is not None:
        return singleton_plan
    return build_base_manufacturing_plan(puzzle)
