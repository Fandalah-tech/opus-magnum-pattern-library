from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from typing import Any

from packages.opus_analysis.canonical import rotate_hex
from packages.opus_parser import parse_solution_bytes, write_solution_bytes

from .capabilities import part_capability_requirement, part_is_available
from .manufacturing import AtomFlow, ManufacturingPlan

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}


def _puzzle_file_id(puzzle: dict[str, Any]) -> str:
    source_name = str((puzzle.get("source") or {}).get("name") or "")
    if source_name:
        return re.sub(r" \(\d+\)$", "", Path(source_name).stem)
    return str(puzzle.get("id") or puzzle.get("name") or "generated-puzzle")


def _branch_relations(candidate: dict[str, Any], branch_index: int) -> set[str]:
    relations = {
        str(edge.get("relation") or "")
        for edge in (candidate.get("branches", [])[branch_index] if branch_index < len(candidate.get("branches", [])) else [])
        if edge.get("relation")
    }
    convergence = candidate.get("convergence") or {}
    inputs = list(convergence.get("inputs", []))
    if branch_index < len(inputs):
        relations.update(str(value) for value in inputs[branch_index].get("relations", []) if value)
    return relations


def assign_branch_atom_flows(candidate: dict[str, Any], plan: ManufacturingPlan) -> dict[int, AtomFlow]:
    """Assign target-puzzle atom flows to assembly branches by chemistry."""
    branch_count = len(candidate.get("branches", []))
    flows = list(plan.atom_flows)
    if branch_count != len(flows):
        raise ValueError(f"Assembly has {branch_count} branches but manufacturing plan has {len(flows)} atom flows")

    calcified = [flow for flow in flows if flow.transformation == "calcification"]
    direct = [flow for flow in flows if flow.transformation is None]
    calcifying_branches = [index for index in range(branch_count) if "calcify" in _branch_relations(candidate, index)]

    if len(calcified) == 1 and len(direct) == 1 and branch_count == 2:
        if len(calcifying_branches) != 1:
            raise ValueError("Expected exactly one calcifying branch for bonded-pair assembly")
        calc_index = calcifying_branches[0]
        direct_index = 1 - calc_index
        return {calc_index: calcified[0], direct_index: direct[0]}

    raise ValueError(f"No branch assignment strategy for manufacturing plan {plan.strategy}")


def _interchangeable_reagent_groups(plan: ManufacturingPlan) -> list[set[int]]:
    groups: dict[str, set[int]] = {}
    for operation in plan.operations:
        if operation.kind != "source" or operation.metadata.get("reagentIndex") is None:
            continue
        group = str(operation.metadata.get("interchangeableSourceGroup") or "")
        if not group:
            continue
        groups.setdefault(group, set()).add(int(operation.metadata["reagentIndex"]))
    return [indices for indices in groups.values() if indices]


def _reagents_are_interchangeable(reagent_indices: set[int], plan: ManufacturingPlan) -> bool:
    if len(reagent_indices) <= 1:
        return True
    return any(reagent_indices.issubset(group) for group in _interchangeable_reagent_groups(plan))


def assign_branch_reagent_indices(candidate: dict[str, Any], plan: ManufacturingPlan) -> dict[int, int]:
    """Resolve each source branch to a target reagent without puzzle-specific IDs."""
    branch_count = len(candidate.get("branches", []))
    if branch_count <= 0:
        return {}

    if plan.atom_flows:
        return {
            branch_index: int(flow.reagent_index)
            for branch_index, flow in assign_branch_atom_flows(candidate, plan).items()
        }

    source_operations = [
        operation
        for operation in plan.operations
        if operation.kind == "source" and operation.metadata.get("reagentIndex") is not None
    ]
    if not source_operations:
        return {}

    source_indices = sorted({int(operation.metadata["reagentIndex"]) for operation in source_operations})
    if len(source_indices) == 1:
        return {branch_index: source_indices[0] for branch_index in range(branch_count)}

    interchangeable_groups = {
        str(operation.metadata.get("interchangeableSourceGroup") or "")
        for operation in source_operations
    } - {""}
    if (
        len(interchangeable_groups) == 1
        and all(operation.metadata.get("interchangeableSourceGroup") for operation in source_operations)
        and len(source_indices) == branch_count
    ):
        return {
            branch_index: reagent_index
            for branch_index, reagent_index in zip(range(branch_count), source_indices)
        }

    role_to_reagent = {
        str(operation.metadata.get("branchRole") or ""): int(operation.metadata["reagentIndex"])
        for operation in source_operations
        if operation.metadata.get("branchRole")
    }
    if set(role_to_reagent) == {"direct", "calcifying"} and branch_count == 2:
        calcifying_branches = [
            branch_index
            for branch_index in range(branch_count)
            if "calcify" in _branch_relations(candidate, branch_index)
        ]
        if len(calcifying_branches) != 1:
            raise ValueError(
                f"Expected exactly one calcifying source branch for {plan.strategy}; found {calcifying_branches}"
            )
        calcifying_index = calcifying_branches[0]
        direct_index = 1 - calcifying_index
        return {
            calcifying_index: role_to_reagent["calcifying"],
            direct_index: role_to_reagent["direct"],
        }

    raise ValueError(f"No source-branch reagent assignment strategy for manufacturing plan {plan.strategy}")


def _branch_indexes_for_part(part: dict[str, Any]) -> set[int]:
    instances = list(part.get("sourceFragmentInstances", []))
    if part.get("sourceFragmentInstance"):
        instances.append(part.get("sourceFragmentInstance"))
    indexes: set[int] = set()
    for instance in instances:
        value = str(instance or "")
        if not value.startswith("branch-"):
            continue
        prefix = value.split(":", 1)[0]
        try:
            indexes.add(int(prefix.split("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return indexes


def resolve_input_reagent_index(
    part: dict[str, Any],
    branch_reagent_indices: dict[int, int],
    source_reagent_indices: list[int],
    plan: ManufacturingPlan,
) -> int:
    """Resolve an input glyph, including safe sharing across equivalent branches."""
    branch_indexes = _branch_indexes_for_part(part)
    if branch_indexes:
        missing = sorted(branch_indexes - set(branch_reagent_indices))
        if missing:
            raise ValueError(f"Input part references unmapped source branches: {missing}")
        mapped = {int(branch_reagent_indices[index]) for index in branch_indexes}
        if len(mapped) == 1:
            return next(iter(mapped))
        if _reagents_are_interchangeable(mapped, plan):
            return min(mapped)
        raise ValueError(
            f"Input part is shared across non-interchangeable source branches: {sorted(branch_indexes)}"
        )

    if len(source_reagent_indices) == 1:
        return int(source_reagent_indices[0])
    source_set = {int(index) for index in source_reagent_indices}
    if source_set and _reagents_are_interchangeable(source_set, plan):
        return min(source_set)
    raise ValueError(f"Could not resolve target reagent for input part {part.get('id')}")


def _fragment_instance_ids(part: dict[str, Any]) -> set[str]:
    values = {
        str(value)
        for value in (part.get("sourceFragmentInstances") or [])
        if value
    }
    for field in (
        "sourceFragmentInstance",
        "originalSourceFragmentInstance",
    ):
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


def singleton_input_alignment(
    input_part: dict[str, Any],
    reagent_index: int,
    puzzle: dict[str, Any],
    all_parts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Recenter a singleton target reagent onto an inherited first grab site.

    Learned feed fragments may come from multi-atom reagents where the arm's
    first grab cell is offset from the input glyph origin.  If the target
    reagent contains exactly one atom, preserve the learned arm geometry and
    translate only the target input glyph so that atom appears under the first
    stationary grab.  Candidate arms must share fragment provenance with the
    input, which prevents unrelated nearby arms from attracting the glyph.
    """

    reagents = list(puzzle.get("reagents") or [])
    if reagent_index < 0 or reagent_index >= len(reagents):
        return None
    atoms = list(reagents[reagent_index].get("atoms") or [])
    if len(atoms) != 1:
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
    grab = _arm_initial_tip(arm)
    atom_position = tuple(int(value) for value in (atoms[0].get("position") or (0, 0)))
    atom_offset = rotate_hex(atom_position, int(input_part.get("rotation") or 0) % 6)
    aligned = [grab[0] - atom_offset[0], grab[1] - atom_offset[1]]
    original = [int(value) for value in (input_part.get("position") or (0, 0))]
    return {
        "position": aligned,
        "originalPosition": original,
        "reagentIndex": int(reagent_index),
        "targetAtomLocalPosition": list(atom_position),
        "grabPosition": list(grab),
        "servingArmId": str(arm.get("id") or ""),
        "sharedFragmentInstanceCount": int(overlap),
        "exactFragmentInstanceMatch": bool(exact),
        "firstGrabCycle": int(-negative_cycle),
    }


def _normal_bond_pairs(molecule: dict[str, Any]) -> set[frozenset[tuple[int, int]]] | None:
    pairs: set[frozenset[tuple[int, int]]] = set()
    for bond in molecule.get("bonds") or []:
        if str(bond.get("type") or "normal") != "normal":
            return None
        first = tuple(int(value) for value in (bond.get("from") or (0, 0)))
        second = tuple(int(value) for value in (bond.get("to") or (0, 0)))
        if first == second:
            return None
        pairs.add(frozenset((first, second)))
    return pairs


def _arc_output_transform(
    product: dict[str, Any],
    arc_cells: list[tuple[int, int]],
) -> tuple[tuple[int, int], int] | None:
    atoms = list(product.get("atoms") or [])
    local_cells = [tuple(int(value) for value in (atom.get("position") or (0, 0))) for atom in atoms]
    if len(local_cells) != len(arc_cells) or len(set(local_cells)) != len(local_cells):
        return None
    bonds = _normal_bond_pairs(product)
    if bonds is None or len(bonds) != len(local_cells) - 1:
        return None
    expected_world_bonds = {
        frozenset((arc_cells[index], arc_cells[index + 1]))
        for index in range(len(arc_cells) - 1)
    }
    target_cells = set(arc_cells)
    for rotation in range(6):
        rotated = [rotate_hex(cell, rotation) for cell in local_cells]
        for world_anchor in arc_cells:
            for local_anchor in rotated:
                origin = (
                    world_anchor[0] - local_anchor[0],
                    world_anchor[1] - local_anchor[1],
                )
                transformed = {
                    (origin[0] + cell[0], origin[1] + cell[1])
                    for cell in rotated
                }
                if transformed != target_cells:
                    continue
                world_bonds = {
                    frozenset((
                        (
                            origin[0] + rotate_hex(tuple(first), rotation)[0],
                            origin[1] + rotate_hex(tuple(first), rotation)[1],
                        ),
                        (
                            origin[0] + rotate_hex(tuple(second), rotation)[0],
                            origin[1] + rotate_hex(tuple(second), rotation)[1],
                        ),
                    ))
                    for pair in bonds
                    for first, second in [tuple(pair)]
                }
                if world_bonds == expected_world_bonds:
                    return origin, rotation
    return None


def _direction_rotation(delta: tuple[int, int]) -> int | None:
    for rotation in range(6):
        if rotate_hex((1, 0), rotation) == delta:
            return rotation
    return None


def _preferred_rotation_steps(arm: dict[str, Any]) -> list[int]:
    ordered = sorted(arm.get("program") or [], key=lambda item: int(item.get("cycle") or 0))
    preferred = None
    for item in ordered:
        instruction = str(item.get("instruction") or "")
        if instruction == "rotate_cw":
            preferred = -1
            break
        if instruction == "rotate_ccw":
            preferred = 1
            break
    return [preferred, -preferred] if preferred in {-1, 1} else [-1, 1]


def rotary_singleton_accumulator_adaptation(
    parts: list[dict[str, Any]],
    puzzle: dict[str, Any],
    plan: ManufacturingPlan,
    input_alignments: list[dict[str, Any]],
    source_part_map: dict[str, str],
) -> dict[str, Any] | None:
    """Adapt one learned feed arm into a repeating rotary chain accumulator.

    This specialization is intentionally structural.  It applies only to the
    renewable-singleton manufacturing plan, a fixed one-hex arm learned from
    the selected fragment, and a target product whose exact atom/bond geometry
    is congruent to successive arm-tip positions around that pivot.  No target
    solution data participates in the transformation.
    """
    if plan.strategy != "repeated-singleton-assembly-v1":
        return None
    products = list(puzzle.get("products") or [])
    reagents = list(puzzle.get("reagents") or [])
    if len(products) != 1 or not input_alignments:
        return None
    product = products[0]
    product_atoms = list(product.get("atoms") or [])
    if not 2 <= len(product_atoms) <= 6:
        return None

    by_id = {str(part.get("id") or ""): part for part in parts}
    bonder = next((part for part in parts if part.get("type") == "bonder"), None)
    output = next((part for part in parts if str(part.get("type") or "").startswith("out-")), None)
    if bonder is None or output is None:
        return None

    for alignment in input_alignments:
        input_part = by_id.get(str(alignment.get("partId") or ""))
        serving_clean_id = source_part_map.get(str(alignment.get("servingArmId") or ""))
        arm = by_id.get(str(serving_clean_id or ""))
        if input_part is None or arm is None:
            continue
        if arm.get("type") != "arm1" or int(arm.get("length") or 1) != 1:
            continue
        reagent_index = int(input_part.get("which") or 0)
        if not 0 <= reagent_index < len(reagents):
            continue
        reagent_atoms = list(reagents[reagent_index].get("atoms") or [])
        if len(reagent_atoms) != 1:
            continue
        source_element = str(reagent_atoms[0].get("element") or "")
        if {str(atom.get("element") or "") for atom in product_atoms} != {source_element}:
            continue

        pivot = tuple(int(value) for value in (arm.get("position") or (0, 0)))
        initial_rotation = int(arm.get("rotation") or 0) % 6
        for step in _preferred_rotation_steps(arm):
            arc_cells = []
            for index in range(len(product_atoms)):
                offset = rotate_hex((1, 0), initial_rotation + step * index)
                arc_cells.append((pivot[0] + offset[0], pivot[1] + offset[1]))
            transform = _arc_output_transform(product, arc_cells)
            if transform is None:
                continue
            output_origin, output_rotation = transform
            delta = (
                arc_cells[1][0] - arc_cells[0][0],
                arc_cells[1][1] - arc_cells[0][1],
            )
            bonder_rotation = _direction_rotation(delta)
            if bonder_rotation is None:
                continue

            selected_input = deepcopy(input_part)
            selected_arm = deepcopy(arm)
            selected_bonder = deepcopy(bonder)
            selected_output = deepcopy(output)

            selected_arm["program"] = [
                {"cycle": 0, "instruction": "grab"},
                {"cycle": 1, "instruction": "rotate_cw" if step == -1 else "rotate_ccw"},
                {"cycle": 2, "instruction": "drop"},
                {"cycle": 3, "instruction": "rotate_ccw" if step == -1 else "rotate_cw"},
            ]
            selected_arm["armNumber"] = 1
            selected_bonder["position"] = list(arc_cells[0])
            selected_bonder["rotation"] = int(bonder_rotation)
            selected_bonder["program"] = []
            selected_output["position"] = list(output_origin)
            selected_output["rotation"] = int(output_rotation)
            selected_output["which"] = int(plan.product_index)
            selected_output["program"] = []
            selected_input["program"] = []

            return {
                "parts": [selected_bonder, selected_input, selected_arm, selected_output],
                "metadata": {
                    "kind": "rotary-singleton-accumulator-v1",
                    "sourcePlan": plan.strategy,
                    "servingArmId": str(alignment.get("servingArmId") or ""),
                    "servingCandidateArmId": str(selected_arm.get("id") or ""),
                    "rotationStep": int(step),
                    "period": 4,
                    "targetAtomCount": len(product_atoms),
                    "arcCells": [list(cell) for cell in arc_cells],
                    "bonderPosition": list(selected_bonder["position"]),
                    "bonderRotation": int(selected_bonder["rotation"]),
                    "outputPosition": list(selected_output["position"]),
                    "outputRotation": int(selected_output["rotation"]),
                    "prunedPartCount": max(0, len(parts) - 4),
                    "geometryEvidence": "target-product-rigid-transform-to-learned-arm-tip-arc",
                    "targetSolutionBytesUsed": 0,
                },
            }
    return None


def _clean_part(part: dict[str, Any], *, part_id: str) -> dict[str, Any]:
    cleaned = {
        "id": part_id,
        "type": str(part.get("type") or ""),
        "enabled": bool(part.get("enabled", True)),
        "position": [int(value) for value in (part.get("position") or [0, 0])],
        "length": int(part.get("length") or 1),
        "rotation": int(part.get("rotation") or 0) % 6,
        "which": int(part.get("which") or 0),
        "armNumber": 0,
        "program": [
            {"cycle": int(item.get("cycle") or 0), "instruction": str(item.get("instruction") or "")}
            for item in part.get("program", [])
        ],
    }
    if cleaned["type"] == "track":
        cleaned["trackHexes"] = [[int(value) for value in cell] for cell in part.get("trackHexes", [])]
    if cleaned["type"] == "pipe":
        cleaned["pipeId"] = int(part.get("pipeId") or 0)
        cleaned["pipeHexes"] = [[int(value) for value in cell] for cell in part.get("pipeHexes", [])]
    return cleaned


def build_candidate_solution(
    puzzle: dict[str, Any],
    plan: ManufacturingPlan,
    candidate: dict[str, Any],
    synchronized_layout: dict[str, Any],
    *,
    name: str = "Opus Solver - composed candidate",
) -> dict[str, Any]:
    if not plan.supported:
        raise ValueError(plan.reason or "Manufacturing plan is unsupported")
    summary = synchronized_layout.get("summary", {})
    if not summary.get("layoutComplete"):
        raise ValueError("Assembly layout is incomplete")
    if not summary.get("scheduleComplete"):
        raise ValueError("Assembly program schedule is incomplete or conflicting")

    branch_reagent_indices = assign_branch_reagent_indices(candidate, plan)
    source_reagent_indices = sorted({
        int(operation.metadata["reagentIndex"])
        for operation in plan.operations
        if operation.kind == "source" and operation.metadata.get("reagentIndex") is not None
    })
    raw_parts = list(synchronized_layout.get("parts", []))
    parts = []
    pruned_parts = []
    input_alignments = []
    source_part_map: dict[str, str] = {}
    arm_number = 1
    for index, raw_part in enumerate(raw_parts):
        part = _clean_part(raw_part, part_id=f"part-{index}")
        source_part_id = str(raw_part.get("id") or "")
        if source_part_id:
            source_part_map[source_part_id] = part["id"]
        part_type = part["type"]
        if not part_is_available(puzzle, part_type):
            category, capability = part_capability_requirement(puzzle, part_type) or ("unknown", "unknown")
            pruned_parts.append({
                "sourcePartId": source_part_id,
                "partType": part_type,
                "requiredCapability": capability,
                "category": category,
            })
            continue
        if part_type == "input":
            reagent_index = resolve_input_reagent_index(
                raw_part,
                branch_reagent_indices,
                source_reagent_indices,
                plan,
            )
            part["which"] = reagent_index
            alignment = singleton_input_alignment(raw_part, reagent_index, puzzle, raw_parts)
            if alignment is not None:
                part["position"] = list(alignment["position"])
                input_alignments.append({
                    "partId": part["id"],
                    "sourcePartId": source_part_id,
                    **alignment,
                })
        elif part_type.startswith("out-"):
            part["which"] = int(plan.product_index)
        if part_type in ARM_TYPES:
            part["armNumber"] = arm_number
            arm_number += 1
        parts.append(part)

    accumulator = rotary_singleton_accumulator_adaptation(
        parts,
        puzzle,
        plan,
        input_alignments,
        source_part_map,
    )
    if accumulator is not None:
        parts = accumulator["parts"]

    return {
        "schemaVersion": "0.1.0",
        "format": {"kind": "solution", "version": 7},
        "source": {
            "name": None,
            "generator": "opus_solver/composed-assembly",
            "prunedUnavailableParts": pruned_parts,
            "singletonInputAlignments": input_alignments,
            "rotarySingletonAccumulator": accumulator["metadata"] if accumulator is not None else None,
        },
        "puzzleFile": _puzzle_file_id(puzzle),
        "name": name,
        "metrics": {},
        "unknownMetrics": [],
        "parts": parts,
        "trailingBytes": 0,
    }


def serialize_candidate_roundtrip(solution: dict[str, Any]) -> dict[str, Any]:
    """Serialize a metric-free v7 candidate and parse it back for contract validation."""
    payload = write_solution_bytes(solution, version=7)
    parsed = parse_solution_bytes(payload, source_name="generated-candidate.solution")
    return {
        "bytes": payload,
        "parsed": parsed,
        "diagnostics": {
            "byteCount": len(payload),
            "partCount": len(parsed.get("parts", [])),
            "parserTrailingBytes": parsed.get("trailingBytes"),
            "puzzleFileMatches": str(parsed.get("puzzleFile") or "") == str(solution.get("puzzleFile") or ""),
            "roundTripClean": parsed.get("trailingBytes") == 0 and len(parsed.get("parts", [])) == len(solution.get("parts", [])),
        },
    }
