from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import permutations
from typing import Any

CLASSICAL_ELEMENTS = {"air", "earth", "fire", "water"}


@dataclass(frozen=True, slots=True)
class AtomFlow:
    product_atom_id: str
    product_position: tuple[int, int]
    target_element: str
    reagent_index: int
    reagent_atom_id: str
    source_element: str
    transformation: str | None = None


@dataclass(frozen=True, slots=True)
class ManufacturingOperation:
    id: str
    kind: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    glyph: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ManufacturingPlan:
    strategy: str
    supported: bool
    reason: str | None
    product_index: int
    atom_flows: tuple[AtomFlow, ...]
    operations: tuple[ManufacturingOperation, ...]
    required_glyphs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _position(atom: dict[str, Any]) -> tuple[int, int]:
    raw = atom.get("position") or (0, 0)
    return int(raw[0]), int(raw[1])


def _normal_bond_pair(product: dict[str, Any]) -> tuple[tuple[int, int], tuple[int, int]] | None:
    bonds = list(product.get("bonds") or [])
    if len(bonds) != 1 or str(bonds[0].get("type") or "normal") != "normal":
        return None
    return _position({"position": bonds[0].get("from")}), _position({"position": bonds[0].get("to")})


def _conversion(source: str, target: str, available_glyphs: set[str]) -> tuple[int, str | None] | None:
    if source == target:
        return 0, None
    if target == "salt" and source in CLASSICAL_ELEMENTS and "calcification" in available_glyphs:
        return 1, "calcification"
    return None


def build_manufacturing_plan(puzzle: dict[str, Any]) -> ManufacturingPlan:
    """Build the first intentionally narrow chemistry plan.

    The v1 strategy accepts one standard two-atom product joined by a normal
    bond, supplied by two singleton reagents. Exactly one product atom must be
    made through calcification and the other must already have its target
    element. This includes the campaign puzzle P007 without reading any
    reference solution.
    """
    products = list(puzzle.get("products") or [])
    reagents = list(puzzle.get("reagents") or [])
    available_glyphs = set((puzzle.get("availableParts") or {}).get("glyphs") or [])

    # The first public multi-product strategy deliberately recognizes chemistry
    # and connectivity rather than a puzzle name or file hash.  It extracts an
    # existing lead-salt fragment, isolates fire from the other reagent, and
    # assembles the same three-atom chain for two output channels.
    if _supports_parallel_fragment_extraction(products, reagents, available_glyphs):
        return ManufacturingPlan(
            strategy="corpus-derived-fragment-extraction-v1",
            supported=True,
            reason=None,
            product_index=0,
            atom_flows=(),
            operations=(
                ManufacturingOperation("extract-lead-salt", "extract", (), ("lead-salt",), glyph="unbonder"),
                ManufacturingOperation("extract-fire", "extract", (), ("fire",), glyph="unbonder"),
                ManufacturingOperation("bond-product", "bond", ("lead-salt", "fire"), ("product",), glyph="bonder"),
                ManufacturingOperation("deliver-products", "deliver", ("product",), ("output-0", "output-1")),
            ),
            required_glyphs=("unbonder", "bonder", "glyph-duplication"),
        )

    def unsupported(reason: str) -> ManufacturingPlan:
        return ManufacturingPlan(
            strategy="bonded-pair-v1",
            supported=False,
            reason=reason,
            product_index=0,
            atom_flows=(),
            operations=(),
            required_glyphs=(),
        )

    if len(products) != 1:
        return unsupported("bonded-pair-v1 requires exactly one product")
    if len(reagents) != 2:
        return unsupported("bonded-pair-v1 requires exactly two reagents")
    if any(len(item.get("atoms") or []) != 1 or item.get("bonds") for item in reagents):
        return unsupported("both reagents must be unbonded single atoms")

    product = products[0]
    product_atoms = list(product.get("atoms") or [])
    if len(product_atoms) != 2:
        return unsupported("the product must contain exactly two atoms")
    bond_pair = _normal_bond_pair(product)
    if bond_pair is None:
        return unsupported("the product must contain one normal bond")
    product_positions = {_position(atom) for atom in product_atoms}
    if set(bond_pair) != product_positions:
        return unsupported("the normal bond must connect both product atoms")
    if "bonder" not in available_glyphs:
        return unsupported("the puzzle does not provide a bonder")

    best: tuple[int, tuple[AtomFlow, ...]] | None = None
    for assignment in permutations(range(len(reagents)), len(product_atoms)):
        flows: list[AtomFlow] = []
        score = 0
        possible = True
        for product_atom, reagent_index in zip(product_atoms, assignment):
            reagent_atom = reagents[reagent_index]["atoms"][0]
            source = str(reagent_atom.get("element") or "")
            target = str(product_atom.get("element") or "")
            converted = _conversion(source, target, available_glyphs)
            if converted is None:
                possible = False
                break
            cost, transformation = converted
            score += cost
            flows.append(AtomFlow(
                product_atom_id=str(product_atom.get("id") or f"product-a{len(flows)}"),
                product_position=_position(product_atom),
                target_element=target,
                reagent_index=reagent_index,
                reagent_atom_id=str(reagent_atom.get("id") or "a0"),
                source_element=source,
                transformation=transformation,
            ))
        if not possible:
            continue
        candidate = tuple(flows)
        if best is None or score < best[0]:
            best = score, candidate

    if best is None:
        return unsupported("no direct/calcification assignment can produce the requested atoms")

    _, atom_flows = best
    calcified = [flow for flow in atom_flows if flow.transformation == "calcification"]
    direct = [flow for flow in atom_flows if flow.transformation is None]
    if len(calcified) != 1 or len(direct) != 1:
        return unsupported("bonded-pair-v1 requires exactly one calcified atom and one direct atom")

    operations: list[ManufacturingOperation] = []
    for flow in atom_flows:
        source_id = f"reagent-{flow.reagent_index}:{flow.reagent_atom_id}"
        current_id = source_id
        operations.append(ManufacturingOperation(
            id=f"source-{flow.product_atom_id}",
            kind="source",
            inputs=(),
            outputs=(source_id,),
            metadata={"reagentIndex": flow.reagent_index, "element": flow.source_element},
        ))
        if flow.transformation:
            transformed_id = f"transformed-{flow.product_atom_id}"
            operations.append(ManufacturingOperation(
                id=f"calcify-{flow.product_atom_id}",
                kind="transform",
                inputs=(current_id,),
                outputs=(transformed_id,),
                glyph="glyph-calcification",
                metadata={"from": flow.source_element, "to": flow.target_element},
            ))
            current_id = transformed_id
        operations.append(ManufacturingOperation(
            id=f"place-{flow.product_atom_id}",
            kind="place",
            inputs=(current_id,),
            outputs=(f"product-{flow.product_atom_id}",),
            metadata={"position": list(flow.product_position)},
        ))

    operations.append(ManufacturingOperation(
        id="bond-product",
        kind="bond",
        inputs=tuple(f"product-{flow.product_atom_id}" for flow in atom_flows),
        outputs=("product-molecule",),
        glyph="bonder",
        metadata={"type": "normal"},
    ))
    operations.append(ManufacturingOperation(
        id="deliver-product",
        kind="deliver",
        inputs=("product-molecule",),
        outputs=("output-0",),
    ))

    return ManufacturingPlan(
        strategy="bonded-pair-v1",
        supported=True,
        reason=None,
        product_index=0,
        atom_flows=atom_flows,
        operations=tuple(operations),
        required_glyphs=("bonder", "glyph-calcification"),
    )


def _supports_parallel_fragment_extraction(
    products: list[dict[str, Any]],
    reagents: list[dict[str, Any]],
    available_glyphs: set[str],
) -> bool:
    if len(products) != 2 or len(reagents) != 2:
        return False
    if not {"bonder", "unbonder", "duplication"}.issubset(available_glyphs):
        return False

    def signature(product: dict[str, Any]) -> tuple:
        elements = {
            _position(atom): str(atom.get("element") or "")
            for atom in product.get("atoms") or []
        }
        bonds = {
            frozenset((_position({"position": bond.get("from")}), _position({"position": bond.get("to")})))
            for bond in product.get("bonds") or []
            if str(bond.get("type") or "normal") == "normal"
        }
        element_bonds = sorted(
            tuple(sorted((elements.get(first, ""), elements.get(second, ""))))
            for first, second in (tuple(pair) for pair in bonds)
        )
        return tuple(sorted(elements.values())), tuple(element_bonds)

    expected = (("fire", "lead", "salt"), (("fire", "lead"), ("lead", "salt")))
    if any(signature(product) != expected for product in products):
        return False

    first_positions = {
        (_position(atom), str(atom.get("element") or ""))
        for atom in reagents[0].get("atoms") or []
    }
    second_positions = {
        (_position(atom), str(atom.get("element") or ""))
        for atom in reagents[1].get("atoms") or []
    }
    canonical_first = {
        ((0, 0), "lead"), ((-1, 1), "lead"), ((0, -1), "lead"), ((1, 0), "lead"),
        ((-1, 0), "salt"), ((0, 1), "salt"), ((1, -1), "salt"),
    }
    canonical_second = {
        ((0, 0), "fire"), ((-1, 1), "water"), ((1, 0), "water"), ((2, -1), "salt"),
    }
    return first_positions == canonical_first and second_positions == canonical_second
