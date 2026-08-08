from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Any

from packages.opus_engine.builder import rotate_hex

CLASSICAL_ELEMENTS = {"air", "earth", "fire", "water"}
STANDARD_PRODUCT_TARGET = 6


@dataclass(frozen=True, slots=True)
class FragmentEmbedding:
    reagent_index: int
    rotation: int
    translation: tuple[int, int]
    source_to_product: tuple[tuple[str, str], ...]
    mapped_positions: tuple[tuple[int, int], ...]
    conversions: tuple[tuple[str, str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FragmentAssemblyPlan:
    supported: bool
    reason: str | None
    strategy: str
    embeddings: tuple[FragmentEmbedding, ...]
    cross_bonds: tuple[tuple[tuple[int, int], tuple[int, int], str], ...]
    required_glyphs: tuple[str, ...]
    input_pulls_per_product: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def input_bound_n(self, *, target_products: int = STANDARD_PRODUCT_TARGET) -> int:
        if not self.supported or not self.input_pulls_per_product:
            return 0
        return max(self.input_pulls_per_product) * target_products

    def classical_cycle_bound(
        self,
        *,
        latency: int,
        target_products: int = STANDARD_PRODUCT_TARGET,
        final_output_cycle: int = 1,
    ) -> int:
        """Return the standard non-overlap lower bound 2N + L + final-output.

        ``latency`` is deliberately explicit: proving L is a separate geometry/
        scheduling problem, while this planner proves the input-use term N.
        """
        n = self.input_bound_n(target_products=target_products)
        return 2 * n + latency + final_output_cycle


def _pos(atom: dict[str, Any]) -> tuple[int, int]:
    raw = atom.get("position") or (0, 0)
    return int(raw[0]), int(raw[1])


def _add(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    return a[0] + b[0], a[1] + b[1]


def _sub(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    return a[0] - b[0], a[1] - b[1]


def _bond_key(a: tuple[int, int], b: tuple[int, int], kind: str) -> tuple[tuple[int, int], tuple[int, int], str]:
    first, second = sorted((a, b))
    return first, second, kind


def _bonds(molecule: dict[str, Any]) -> set[tuple[tuple[int, int], tuple[int, int], str]]:
    result: set[tuple[tuple[int, int], tuple[int, int], str]] = set()
    for bond in molecule.get("bonds") or []:
        kind = str(bond.get("type") or "normal")
        a = tuple(int(v) for v in bond.get("from") or (0, 0))
        b = tuple(int(v) for v in bond.get("to") or (0, 0))
        result.add(_bond_key(a, b, kind))
    return result


def _conversion(source: str, target: str, available_glyphs: set[str]) -> tuple[str, str, str] | None:
    if source == target:
        return (source, target, "direct")
    if source in CLASSICAL_ELEMENTS and target == "salt" and "calcification" in available_glyphs:
        return (source, target, "calcification")
    return None


def _embedding_candidates(
    reagent_index: int,
    reagent: dict[str, Any],
    product_molecule: dict[str, Any],
    available_glyphs: set[str],
) -> list[FragmentEmbedding]:
    reagent_atoms = list(reagent.get("atoms") or [])
    product_atoms = list(product_molecule.get("atoms") or [])
    if not reagent_atoms:
        return []

    product_by_pos = {_pos(atom): atom for atom in product_atoms}
    reagent_bonds = _bonds(reagent)
    product_bonds = _bonds(product_molecule)
    anchor_source = _pos(reagent_atoms[0])
    candidates: list[FragmentEmbedding] = []

    for rotation in range(6):
        rotated_source = rotate_hex(anchor_source, rotation)
        for anchor_target in product_by_pos:
            translation = _sub(anchor_target, rotated_source)
            mapped: dict[tuple[int, int], tuple[int, int]] = {}
            source_to_product: list[tuple[str, str]] = []
            conversions: list[tuple[str, str, str]] = []
            valid = True

            for source_atom in reagent_atoms:
                source_position = _pos(source_atom)
                target_position = _add(rotate_hex(source_position, rotation), translation)
                target_atom = product_by_pos.get(target_position)
                if target_atom is None or target_position in mapped.values():
                    valid = False
                    break
                converted = _conversion(
                    str(source_atom.get("element") or ""),
                    str(target_atom.get("element") or ""),
                    available_glyphs,
                )
                if converted is None:
                    valid = False
                    break
                mapped[source_position] = target_position
                source_to_product.append((
                    str(source_atom.get("id") or source_position),
                    str(target_atom.get("id") or target_position),
                ))
                if converted[2] != "direct":
                    conversions.append(converted)

            if not valid:
                continue

            transformed_internal = {
                _bond_key(mapped[a], mapped[b], kind)
                for a, b, kind in reagent_bonds
            }
            mapped_positions = set(mapped.values())
            product_internal = {
                bond
                for bond in product_bonds
                if bond[0] in mapped_positions and bond[1] in mapped_positions
            }
            if transformed_internal != product_internal:
                continue

            candidates.append(FragmentEmbedding(
                reagent_index=reagent_index,
                rotation=rotation,
                translation=translation,
                source_to_product=tuple(source_to_product),
                mapped_positions=tuple(sorted(mapped_positions)),
                conversions=tuple(conversions),
            ))

    candidates.sort(key=lambda item: (len(item.conversions), item.rotation, item.translation))
    return candidates


def analyze_two_fragment_assembly(puzzle: dict[str, Any]) -> FragmentAssemblyPlan:
    """Recognize the first multi-atom assembly family.

    The supported family intentionally stays narrow: exactly two reagent
    molecules are each consumed once per product, their existing internal bonds
    are preserved under rotation/translation, and together they cover one
    standard product. Product bonds between the two embedded fragments are
    treated as assembly bonds. Classical atoms may be calcified to salt.
    """
    strategy = "two-fragment-assembly-v1"
    reagents = list(puzzle.get("reagents") or [])
    products = list(puzzle.get("products") or [])
    available = set((puzzle.get("availableParts") or {}).get("glyphs") or [])

    def unsupported(reason: str) -> FragmentAssemblyPlan:
        return FragmentAssemblyPlan(
            supported=False,
            reason=reason,
            strategy=strategy,
            embeddings=(),
            cross_bonds=(),
            required_glyphs=(),
            input_pulls_per_product=(),
        )

    if len(reagents) != 2:
        return unsupported("two-fragment-assembly-v1 requires exactly two reagents")
    if len(products) != 1:
        return unsupported("two-fragment-assembly-v1 requires exactly one product")
    if any(not (reagent.get("atoms") or []) for reagent in reagents):
        return unsupported("reagents must contain atoms")

    target = products[0]
    if len(target.get("atoms") or []) != sum(len(item.get("atoms") or []) for item in reagents):
        return unsupported("product atom count must equal the sum of both reagent atom counts")

    candidates = [
        _embedding_candidates(index, reagent, target, available)
        for index, reagent in enumerate(reagents)
    ]
    if any(not items for items in candidates):
        return unsupported("at least one reagent cannot be embedded into the product")

    target_positions = {_pos(atom) for atom in target.get("atoms") or []}
    best: tuple[int, tuple[FragmentEmbedding, FragmentEmbedding]] | None = None
    for first, second in product(candidates[0], candidates[1]):
        first_positions = set(first.mapped_positions)
        second_positions = set(second.mapped_positions)
        if first_positions & second_positions:
            continue
        if first_positions | second_positions != target_positions:
            continue
        score = len(first.conversions) + len(second.conversions)
        pair = (first, second)
        if best is None or score < best[0]:
            best = (score, pair)

    if best is None:
        return unsupported("no disjoint reagent embeddings cover the complete product")

    embeddings = best[1]
    internal_positions = [set(item.mapped_positions) for item in embeddings]
    cross_bonds: list[tuple[tuple[int, int], tuple[int, int], str]] = []
    for bond in sorted(_bonds(target)):
        if any(bond[0] in positions and bond[1] in positions for positions in internal_positions):
            continue
        cross_bonds.append(bond)

    required: set[str] = set()
    if any(item.conversions for item in embeddings):
        if "calcification" not in available:
            return unsupported("calcification is required but unavailable")
        required.add("glyph-calcification")
    if cross_bonds:
        if "bonder" not in available:
            return unsupported("cross-fragment bonds require a bonder")
        required.add("bonder")

    return FragmentAssemblyPlan(
        supported=True,
        reason=None,
        strategy=strategy,
        embeddings=embeddings,
        cross_bonds=tuple(cross_bonds),
        required_glyphs=tuple(sorted(required)),
        input_pulls_per_product=(1, 1),
    )
