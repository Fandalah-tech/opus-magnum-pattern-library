from __future__ import annotations

from collections import Counter
from typing import Any

from packages.opus_analysis.canonical import rotate_hex

from .capabilities import part_is_available
from .generic_chemistry import ElementRecipe, build_element_recipes


ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}


def _fragment_instance_ids(part: dict[str, Any]) -> set[str]:
    values = {
        str(value)
        for value in (part.get("sourceFragmentInstances") or [])
        if value
    }
    for field in ("sourceFragmentInstance", "originalSourceFragmentInstance"):
        if part.get(field):
            values.add(str(part[field]))
    return values


def _first_program_instruction(part: dict[str, Any]) -> tuple[int, str] | None:
    program = sorted(
        (
            (int(item.get("cycle") or 0), str(item.get("instruction") or ""))
            for item in (part.get("program") or [])
            if item.get("instruction")
        ),
        key=lambda item: item[0],
    )
    return program[0] if program else None


def _arm_initial_tip(part: dict[str, Any]) -> tuple[int, int]:
    base = tuple(int(value) for value in (part.get("position") or (0, 0)))
    reach = rotate_hex((int(part.get("length") or 1), 0), int(part.get("rotation") or 0) % 6)
    return base[0] + reach[0], base[1] + reach[1]


def _collect_route_source_atoms(
    route: ElementRecipe,
    reagent_index: int,
    counts: Counter[int],
) -> None:
    if route.kind in {"source", "extract"}:
        if route.reagent_index == reagent_index and route.reagent_atom_index is not None:
            counts[int(route.reagent_atom_index)] += 1
        return
    for child in route.inputs:
        _collect_route_source_atoms(child, reagent_index, counts)


def preferred_reagent_anchor_atom(puzzle: dict[str, Any], reagent_index: int) -> int | None:
    """Choose the target reagent atom most used by the planner's cheapest recipes."""

    reagents = list(puzzle.get("reagents") or [])
    if not 0 <= reagent_index < len(reagents):
        return None
    atoms = list(reagents[reagent_index].get("atoms") or [])
    if not atoms:
        return None
    if len(atoms) == 1:
        return 0

    routes = build_element_recipes(puzzle)
    counts: Counter[int] = Counter()
    for product in puzzle.get("products") or []:
        for atom in product.get("atoms") or []:
            route = routes.get(str(atom.get("element") or ""))
            if route is not None:
                _collect_route_source_atoms(route, reagent_index, counts)
    if counts:
        return min(counts, key=lambda index: (-counts[index], index))
    return 0


def generic_input_alignment(
    input_part: dict[str, Any],
    reagent_index: int,
    puzzle: dict[str, Any],
    all_parts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Translate a target reagent so its useful atom appears under a learned grab.

    The original transfer path aligned only singleton reagents.  For bonded
    feeds we keep the inherited input rotation and whole molecule intact, choose
    the atom most often required by the target chemistry recipes, and translate
    the input glyph so that atom occupies the first grab cell of a provenance-
    compatible learned arm.  This is a mechanical adaptation derived from the
    target puzzle and learned fragment geometry only; no target solution is used.
    """

    reagents = list(puzzle.get("reagents") or [])
    if not 0 <= reagent_index < len(reagents):
        return None
    atoms = list(reagents[reagent_index].get("atoms") or [])
    if not atoms:
        return None

    input_instances = _fragment_instance_ids(input_part)
    if not input_instances:
        return None

    choices: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for arm in all_parts:
        arm_type = str(arm.get("type") or "")
        if arm_type not in ARM_TYPES or not part_is_available(puzzle, arm_type):
            continue
        first = _first_program_instruction(arm)
        if first is None or first[1] != "grab":
            continue
        arm_instances = _fragment_instance_ids(arm)
        overlap = len(input_instances & arm_instances)
        if overlap <= 0:
            continue
        exact = int(arm_instances == input_instances)
        choices.append((overlap, exact, -first[0], str(arm.get("id") or ""), arm))
    if not choices:
        return None

    choices.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    overlap, exact, negative_cycle, _, arm = choices[0]
    anchor_index = preferred_reagent_anchor_atom(puzzle, reagent_index)
    if anchor_index is None or not 0 <= anchor_index < len(atoms):
        return None

    grab = _arm_initial_tip(arm)
    atom_position = tuple(int(value) for value in (atoms[anchor_index].get("position") or (0, 0)))
    atom_offset = rotate_hex(atom_position, int(input_part.get("rotation") or 0) % 6)
    aligned = [grab[0] - atom_offset[0], grab[1] - atom_offset[1]]
    original = [int(value) for value in (input_part.get("position") or (0, 0))]
    return {
        "position": aligned,
        "originalPosition": original,
        "reagentIndex": int(reagent_index),
        "targetAtomIndex": int(anchor_index),
        "targetAtomElement": str(atoms[anchor_index].get("element") or ""),
        "targetAtomLocalPosition": list(atom_position),
        "targetReagentAtomCount": len(atoms),
        "bondedTargetReagent": bool(reagents[reagent_index].get("bonds")),
        "grabPosition": list(grab),
        "servingArmId": str(arm.get("id") or ""),
        "sharedFragmentInstanceCount": int(overlap),
        "exactFragmentInstanceMatch": bool(exact),
        "firstGrabCycle": int(-negative_cycle),
        "alignmentEvidence": "target-chemistry-source-atom-to-learned-first-grab",
    }


__all__ = ["generic_input_alignment", "preferred_reagent_anchor_atom"]
