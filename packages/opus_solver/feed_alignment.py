from __future__ import annotations

from collections import Counter
from typing import Any

from packages.opus_analysis.canonical import rotate_hex

from .capabilities import part_is_available
from .generic_chemistry import ElementRecipe, build_element_recipes


ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
TRACK_INSTRUCTIONS = {"track_plus", "track_minus"}


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


def _hex_distance(first: tuple[int, int], second: tuple[int, int]) -> int:
    dq = first[0] - second[0]
    dr = first[1] - second[1]
    return max(abs(dq), abs(dr), abs(dq + dr))


def _arm_initial_tip(part: dict[str, Any]) -> tuple[int, int]:
    base = tuple(int(value) for value in (part.get("position") or (0, 0)))
    reach = rotate_hex((int(part.get("length") or 1), 0), int(part.get("rotation") or 0) % 6)
    return base[0] + reach[0], base[1] + reach[1]


def _track_world_cells(track: dict[str, Any]) -> set[tuple[int, int]]:
    origin = tuple(int(value) for value in (track.get("position") or (0, 0)))
    cells = {origin}
    cells.update(
        (origin[0] + int(offset[0]), origin[1] + int(offset[1]))
        for offset in (track.get("trackHexes") or [])
    )
    return cells


def _grab_rotations(arm: dict[str, Any]) -> set[int]:
    """Return arm orientations observed at explicit grabs in one learned tape."""
    current = int(arm.get("rotation") or 0) % 6
    rotations: set[int] = set()
    ordered = sorted(arm.get("program") or [], key=lambda item: int(item.get("cycle") or 0))
    for item in ordered:
        instruction = str(item.get("instruction") or "")
        if instruction == "grab":
            rotations.add(current)
        elif instruction == "rotate_cw":
            current = (current - 1) % 6
        elif instruction == "rotate_ccw":
            current = (current + 1) % 6
        elif instruction == "reset":
            current = int(arm.get("rotation") or 0) % 6
    return rotations or {int(arm.get("rotation") or 0) % 6}


def _track_grab_candidates(
    arm: dict[str, Any],
    all_parts: list[dict[str, Any]],
) -> tuple[set[tuple[int, int]], list[str]]:
    """Approximate repeated grab cells for an arm that advances on a learned track.

    A tape such as ``grab -> track_plus -> drop`` grabs at a different base on
    later repetitions even though its first grab is at the reset pose.  Using
    every compatible track base with the orientations actually observed at grab
    instructions preserves distinct donor feed lanes instead of collapsing all
    remapped inputs onto the first reset-tip cell.
    """
    if not any(
        str(item.get("instruction") or "") in TRACK_INSTRUCTIONS
        for item in (arm.get("program") or [])
    ):
        return set(), []

    base = tuple(int(value) for value in (arm.get("position") or (0, 0)))
    arm_instances = _fragment_instance_ids(arm)
    rotations = _grab_rotations(arm)
    length = max(1, int(arm.get("length") or 1))
    candidates: set[tuple[int, int]] = set()
    track_ids: list[str] = []
    for track in all_parts:
        if str(track.get("type") or "") != "track":
            continue
        track_instances = _fragment_instance_ids(track)
        if arm_instances and track_instances and not (arm_instances & track_instances):
            continue
        cells = _track_world_cells(track)
        if base not in cells:
            continue
        track_ids.append(str(track.get("id") or ""))
        for mobile_base in cells:
            for rotation in rotations:
                reach = rotate_hex((length, 0), rotation)
                candidates.add((mobile_base[0] + reach[0], mobile_base[1] + reach[1]))
    return candidates, sorted(track_ids)


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
    """Translate a target reagent so a useful atom lands on a learned grab cell.

    For stationary mechanisms the target atom is aligned to the serving arm's
    first grab, preserving the previous singleton/bonded-feed behavior.  For a
    track-moving learned arm, the alignment instead chooses the reachable grab
    cell that requires the smallest translation from this input's inherited
    donor pose.  Multiple target inputs can therefore reuse one renewable
    reagent and one transport arm without being collapsed onto the same hexes.
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

    atom_position = tuple(int(value) for value in (atoms[anchor_index].get("position") or (0, 0)))
    atom_offset = rotate_hex(atom_position, int(input_part.get("rotation") or 0) % 6)
    original = tuple(int(value) for value in (input_part.get("position") or (0, 0)))

    track_grabs, track_ids = _track_grab_candidates(arm, all_parts)
    grab_candidates = track_grabs or {_arm_initial_tip(arm)}
    ranked: list[tuple[int, int, int, int, tuple[int, int], tuple[int, int]]] = []
    for grab in grab_candidates:
        aligned = (grab[0] - atom_offset[0], grab[1] - atom_offset[1])
        ranked.append((
            _hex_distance(aligned, original),
            _hex_distance(grab, original),
            aligned[0],
            aligned[1],
            grab,
            aligned,
        ))
    ranked.sort()
    _, _, _, _, grab, aligned = ranked[0]

    track_preserving = bool(track_grabs)
    return {
        "position": [aligned[0], aligned[1]],
        "originalPosition": [original[0], original[1]],
        "reagentIndex": int(reagent_index),
        "targetAtomIndex": int(anchor_index),
        "targetAtomElement": str(atoms[anchor_index].get("element") or ""),
        "targetAtomLocalPosition": list(atom_position),
        "targetReagentAtomCount": len(atoms),
        "bondedTargetReagent": bool(reagents[reagent_index].get("bonds")),
        "grabPosition": list(grab),
        "servingArmId": str(arm.get("id") or ""),
        "servingTrackIds": track_ids,
        "reachableGrabCandidateCount": len(grab_candidates),
        "translationDistance": _hex_distance(aligned, original),
        "sharedFragmentInstanceCount": int(overlap),
        "exactFragmentInstanceMatch": bool(exact),
        "firstGrabCycle": int(-negative_cycle),
        "alignmentEvidence": (
            "target-chemistry-source-atom-to-nearest-learned-track-grab"
            if track_preserving
            else "target-chemistry-source-atom-to-learned-first-grab"
        ),
    }


__all__ = ["generic_input_alignment", "preferred_reagent_anchor_atom"]
