from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .manufacturing import ManufacturingOperation, ManufacturingPlan


CARDINAL_ELEMENTS = ("air", "earth", "fire", "water")
METAL_ELEMENTS = ("lead", "tin", "iron", "copper", "silver", "gold")


@dataclass(frozen=True, slots=True)
class ElementRecipe:
    """Minimum-input chemistry recipe for producing one atom."""

    element: str
    kind: str
    cost: int
    depth: int
    reagent_index: int | None = None
    reagent_atom_index: int | None = None
    extraction_bond_count: int = 0
    inputs: tuple["ElementRecipe", ...] = ()
    glyph: str | None = None
    byproducts: tuple[str, ...] = ()


def _position(atom: dict[str, Any]) -> tuple[int, int]:
    raw = atom.get("position") or (0, 0)
    return int(raw[0]), int(raw[1])


def _connected_normal_bonds(
    molecule: dict[str, Any],
) -> list[tuple[tuple[int, int], tuple[int, int]]] | None:
    positions = {_position(atom) for atom in molecule.get("atoms") or ()}
    if not positions:
        return None
    raw: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for bond in molecule.get("bonds") or ():
        if str(bond.get("type") or "normal") != "normal":
            return None
        first = _position({"position": bond.get("from")})
        second = _position({"position": bond.get("to")})
        if first == second or first not in positions or second not in positions:
            return None
        raw.append((first, second))
    if len(positions) == 1:
        return [] if not raw else None
    if not raw:
        return None

    pending = list(raw)
    ordered = [pending.pop(0)]
    connected = set(ordered[0])
    while pending:
        attaching = next(
            (
                index
                for index, (first, second) in enumerate(pending)
                if (first in connected) ^ (second in connected)
            ),
            None,
        )
        if attaching is not None:
            first, second = pending.pop(attaching)
            ordered.append((first, second))
            connected.update((first, second))
            continue
        closing = next(
            (
                index
                for index, (first, second) in enumerate(pending)
                if first in connected and second in connected
            ),
            None,
        )
        if closing is None:
            return None
        ordered.append(pending.pop(closing))
    return ordered if connected == positions else None


def _normal_atom_degrees(molecule: dict[str, Any]) -> dict[tuple[int, int], int] | None:
    atoms = list(molecule.get("atoms") or ())
    positions = {_position(atom) for atom in atoms}
    if len(positions) != len(atoms):
        return None
    degrees = {position: 0 for position in positions}
    for bond in molecule.get("bonds") or ():
        if str(bond.get("type") or "normal") != "normal":
            return None
        first = _position({"position": bond.get("from")})
        second = _position({"position": bond.get("to")})
        if first == second or first not in positions or second not in positions:
            return None
        degrees[first] += 1
        degrees[second] += 1
    return degrees


def _route_key(route: ElementRecipe) -> tuple[int, int, int, str]:
    source_priority = 0 if route.kind == "source" else 1 if route.kind == "extract" else 2
    return route.cost, route.depth, source_priority, route.kind


def build_element_recipes(puzzle: dict[str, Any]) -> dict[str, ElementRecipe]:
    """Find cheap element recipes using renewable reagent molecules and OM chemistry.

    Reagent glyphs are renewable molecule feeds, not merely singleton atom
    feeds.  When an atom is embedded in a normal-bond reagent and an unbonder
    is available, the planner may isolate a fresh copy of that atom by removing
    each incident bond.  The physical composer still decides how to transport
    the residual fragment; this layer only proves chemical reachability and
    exposes the required bond-removal relations explicitly.
    """

    reagents = list(puzzle.get("reagents") or ())
    available_parts = puzzle.get("availableParts") or {}
    glyphs = set(available_parts.get("glyphs") or ())
    arms = set(available_parts.get("arms") or ())

    routes: dict[str, ElementRecipe] = {}
    for reagent_index, reagent in enumerate(reagents):
        atoms = list(reagent.get("atoms") or ())
        if not atoms:
            continue
        degrees = _normal_atom_degrees(reagent)
        if degrees is None:
            continue
        bonded = bool(reagent.get("bonds"))
        for atom_index, atom in enumerate(atoms):
            element = str(atom.get("element") or "")
            degree = int(degrees[_position(atom)])
            if len(atoms) == 1 and not bonded:
                candidate = ElementRecipe(
                    element,
                    "source",
                    1,
                    0,
                    reagent_index=reagent_index,
                    reagent_atom_index=atom_index,
                )
            else:
                if degree > 0 and "unbonder" not in glyphs:
                    continue
                candidate = ElementRecipe(
                    element,
                    "extract",
                    1 + degree,
                    degree,
                    reagent_index=reagent_index,
                    reagent_atom_index=atom_index,
                    extraction_bond_count=degree,
                    glyph="unbonder" if degree else None,
                )
            existing = routes.get(element)
            if existing is None or _route_key(candidate) < _route_key(existing):
                routes[element] = candidate

    def propose(
        element: str,
        kind: str,
        inputs: tuple[ElementRecipe, ...],
        glyph: str,
        *,
        byproducts: tuple[str, ...] = (),
    ) -> bool:
        candidate = ElementRecipe(
            element=element,
            kind=kind,
            cost=1 + sum(item.cost for item in inputs),
            depth=1 + max(item.depth for item in inputs),
            inputs=inputs,
            glyph=glyph,
            byproducts=byproducts,
        )
        existing = routes.get(element)
        if existing is None or _route_key(candidate) < _route_key(existing):
            routes[element] = candidate
            return True
        return False

    # Costs strictly increase through reactions, so fixed-point relaxation is
    # stable even for the reversible cardinal/salt/quintessence subnetwork.
    for _ in range(32):
        changed = False

        if "calcification" in glyphs:
            for cardinal in CARDINAL_ELEMENTS:
                if cardinal in routes:
                    changed |= propose("salt", "calcification", (routes[cardinal],), "glyph-calcification")

        if "animismus" in glyphs and "salt" in routes:
            salt = routes["salt"]
            changed |= propose("mors", "animismus", (salt, salt), "glyph-animismus", byproducts=("vitae",))
            changed |= propose("vitae", "animismus", (salt, salt), "glyph-animismus", byproducts=("mors",))

        if "dispersion" in glyphs and "quintessence" in routes:
            quintessence = routes["quintessence"]
            for cardinal in CARDINAL_ELEMENTS:
                changed |= propose(
                    cardinal,
                    "dispersion",
                    (quintessence,),
                    "glyph-dispersion",
                    byproducts=tuple(item for item in CARDINAL_ELEMENTS if item != cardinal),
                )

        if "unification" in glyphs and all(element in routes for element in CARDINAL_ELEMENTS):
            changed |= propose(
                "quintessence",
                "unification",
                tuple(routes[element] for element in CARDINAL_ELEMENTS),
                "glyph-unification",
            )

        if "purification" in glyphs:
            for index in range(len(METAL_ELEMENTS) - 1):
                source, target = METAL_ELEMENTS[index:index + 2]
                if source in routes:
                    changed |= propose(target, "purification", (routes[source], routes[source]), "glyph-purification")

        if "projection" in glyphs and "quicksilver" in routes:
            quicksilver = routes["quicksilver"]
            for index in range(len(METAL_ELEMENTS) - 1):
                source, target = METAL_ELEMENTS[index:index + 2]
                if source in routes:
                    changed |= propose(target, "projection", (routes[source], quicksilver), "glyph-projection")

        # Duplication alone is not arbitrary transmutation.  Only expose the
        # salt-to-cardinal route when Van Berlo's wheel is actually available.
        if "duplication" in glyphs and "van-berlo" in arms and "salt" in routes:
            for cardinal in CARDINAL_ELEMENTS:
                changed |= propose(cardinal, "van-berlo", (routes["salt"],), "glyph-duplication")

        if not changed:
            break
    return routes


def _materialize_recipe(
    route: ElementRecipe,
    operations: list[ManufacturingOperation],
    serial: list[int],
    *,
    product_index: int,
    atom_index: int,
) -> str:
    def next_id(prefix: str) -> str:
        value = serial[0]
        serial[0] += 1
        return f"{prefix}-{value}"

    if route.kind in {"source", "extract"}:
        output = next_id("feed")
        operations.append(ManufacturingOperation(
            id=next_id("source"),
            kind="source",
            inputs=(),
            outputs=(output,),
            metadata={
                "reagentIndex": route.reagent_index,
                "reagentAtomIndex": route.reagent_atom_index,
                "element": route.element,
                "reusableSource": True,
                "productIndex": product_index,
                "productAtomIndex": atom_index,
                "extractFromReagentMolecule": route.kind == "extract",
                "extractionBondCount": route.extraction_bond_count,
            },
        ))
        current = output
        for extraction_step in range(route.extraction_bond_count):
            extracted = next_id("extracted")
            operations.append(ManufacturingOperation(
                id=next_id("unbond"),
                kind="unbond",
                inputs=(current,),
                outputs=(extracted,),
                glyph="unbonder",
                metadata={
                    "reagentIndex": route.reagent_index,
                    "reagentAtomIndex": route.reagent_atom_index,
                    "element": route.element,
                    "extractionStep": extraction_step,
                    "extractionBondCount": route.extraction_bond_count,
                    "chemistryOnlyRecipe": True,
                },
            ))
            current = extracted
        return current

    input_ids = tuple(
        _materialize_recipe(
            item,
            operations,
            serial,
            product_index=product_index,
            atom_index=atom_index,
        )
        for item in route.inputs
    )
    output = next_id(route.element)
    waste_ids = tuple(next_id(f"waste-{element}") for element in route.byproducts)
    operations.append(ManufacturingOperation(
        id=next_id(route.kind),
        kind="transform",
        inputs=input_ids,
        outputs=(output, *waste_ids),
        glyph=route.glyph,
        metadata={
            "reaction": route.kind,
            "to": route.element,
            "byproducts": list(route.byproducts),
            "productIndex": product_index,
            "productAtomIndex": atom_index,
            "chemistryOnlyRecipe": True,
        },
    ))
    return output


def generic_singleton_chemistry_plan(puzzle: dict[str, Any]) -> ManufacturingPlan | None:
    """Plan normal-bond products from renewable singleton or bonded reagents."""

    reagents = list(puzzle.get("reagents") or ())
    products = list(puzzle.get("products") or ())
    glyphs = set((puzzle.get("availableParts") or {}).get("glyphs") or ())
    if not reagents or not products:
        return None

    product_bonds: list[list[tuple[tuple[int, int], tuple[int, int]]]] = []
    for product in products:
        ordered = _connected_normal_bonds(product)
        if ordered is None or (ordered and "bonder" not in glyphs):
            return None
        product_bonds.append(ordered)

    routes = build_element_recipes(puzzle)
    target_elements = {
        str(atom.get("element") or "")
        for product in products
        for atom in product.get("atoms") or ()
    }
    if not target_elements or not target_elements.issubset(routes):
        return None

    operations: list[ManufacturingOperation] = []
    required_glyphs: set[str] = set()
    serial = [0]
    for product_index, (product, ordered_bonds) in enumerate(zip(products, product_bonds)):
        atoms = list(product.get("atoms") or ())
        atom_resources: dict[tuple[int, int], str] = {}
        for atom_index, atom in enumerate(atoms):
            position = _position(atom)
            target = str(atom.get("element") or "")
            before = len(operations)
            current = _materialize_recipe(
                routes[target],
                operations,
                serial,
                product_index=product_index,
                atom_index=atom_index,
            )
            required_glyphs.update(
                operation.glyph for operation in operations[before:] if operation.glyph
            )
            placed = f"product-{product_index}-atom-{atom_index}"
            atom_resources[position] = placed
            operations.append(ManufacturingOperation(
                id=f"place-product-{product_index}-atom-{atom_index}",
                kind="place",
                inputs=(current,),
                outputs=(placed,),
                metadata={"position": list(position), "element": target, "productIndex": product_index},
            ))

        assembled: str | None = None
        assembled_positions: set[tuple[int, int]] = set()
        for bond_index, (first, second) in enumerate(ordered_bonds):
            if assembled is None:
                inputs = (atom_resources[first], atom_resources[second])
                assembled_positions.update((first, second))
            else:
                new_positions = [position for position in (first, second) if position not in assembled_positions]
                inputs = (assembled, *(atom_resources[position] for position in new_positions))
                assembled_positions.update((first, second))
            next_assembled = f"product-{product_index}-assembled-{bond_index}"
            operations.append(ManufacturingOperation(
                id=f"bond-product-{product_index}-{bond_index}",
                kind="bond",
                inputs=tuple(inputs),
                outputs=(next_assembled,),
                glyph="bonder",
                metadata={
                    "type": "normal",
                    "from": list(first),
                    "to": list(second),
                    "productIndex": product_index,
                    "bondIndex": bond_index,
                },
            ))
            required_glyphs.add("bonder")
            assembled = next_assembled

        if assembled is None:
            assembled = atom_resources[_position(atoms[0])]
        operations.append(ManufacturingOperation(
            id=f"deliver-product-{product_index}",
            kind="deliver",
            inputs=(assembled,),
            outputs=(f"output-{product_index}",),
            metadata={"productIndex": product_index},
        ))

    extracted = any(
        operation.kind == "source" and operation.metadata.get("extractFromReagentMolecule")
        for operation in operations
    )
    return ManufacturingPlan(
        strategy="generic-reagent-chemistry-v1" if extracted else "generic-singleton-chemistry-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=(),
        operations=tuple(operations),
        required_glyphs=tuple(sorted(required_glyphs)),
    )


__all__ = [
    "CARDINAL_ELEMENTS",
    "METAL_ELEMENTS",
    "ElementRecipe",
    "build_element_recipes",
    "generic_singleton_chemistry_plan",
]
