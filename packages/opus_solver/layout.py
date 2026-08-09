from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from packages.opus_analysis.canonical import rotate_hex

FragmentKey = tuple[str, str]


def _key(role: Any, mechanism: Any) -> FragmentKey:
    return str(role or ""), str(mechanism or "")


def _geometry_lookup(fragment_index: dict[str, Any]) -> dict[FragmentKey, dict[str, Any]]:
    result = {}
    for item in fragment_index.get("fragments", []):
        geometry = item.get("representativeGeometry")
        if geometry:
            result[_key(item.get("role"), item.get("canonicalMechanismHash"))] = geometry
    return result


def _preferred_transform(edge: dict[str, Any]) -> dict[str, Any] | None:
    transforms = edge.get("relativeTransforms") or {}
    preferred = transforms.get("preferred") if isinstance(transforms, dict) else None
    if preferred:
        return preferred
    if edge.get("relativeTransform"):
        return edge["relativeTransform"]
    return None


def apply_forward_transform(source_position: tuple[int, int], source_rotation: int, transform: dict[str, Any]) -> tuple[tuple[int, int], int]:
    delta = tuple(int(value) for value in transform.get("delta", (0, 0)))
    world_delta = rotate_hex(delta, int(source_rotation))
    target = (int(source_position[0]) + world_delta[0], int(source_position[1]) + world_delta[1])
    rotation = (int(source_rotation) + int(transform.get("rotationDelta") or 0)) % 6
    return target, rotation


def apply_inverse_transform(target_position: tuple[int, int], target_rotation: int, transform: dict[str, Any]) -> tuple[tuple[int, int], int]:
    rotation_delta = int(transform.get("rotationDelta") or 0) % 6
    source_rotation = (int(target_rotation) - rotation_delta) % 6
    delta = tuple(int(value) for value in transform.get("delta", (0, 0)))
    world_delta = rotate_hex(delta, source_rotation)
    source = (int(target_position[0]) - world_delta[0], int(target_position[1]) - world_delta[1])
    return source, source_rotation


def _motif_input_transform(convergence: dict[str, Any], input_item: dict[str, Any], occurrence: int) -> dict[str, Any] | None:
    role = str(input_item.get("sourceRole") or "")
    mechanism = str(input_item.get("sourceMechanismHash") or "")
    for sample in convergence.get("samples", []):
        matches = [
            item for item in sample.get("inputs", [])
            if str(item.get("sourceRole") or "") == role and str(item.get("sourceMechanismHash") or "") == mechanism
        ]
        if occurrence < len(matches):
            transforms = matches[occurrence].get("relativeTransforms", [])
            if transforms:
                return transforms[0]
    return None


def _anchor_part(geometry: dict[str, Any]) -> dict[str, Any] | None:
    anchor_type = str(geometry.get("anchorPartType") or "")
    return next((part for part in geometry.get("parts", []) if str(part.get("type") or "") == anchor_type), None)


def transplant_geometry(geometry: dict[str, Any], *, anchor_position: tuple[int, int], anchor_rotation: int, instance_id: str) -> list[dict[str, Any]]:
    anchor = _anchor_part(geometry)
    if anchor is None:
        return []
    canonical_anchor_position = tuple(int(value) for value in (anchor.get("position") or (0, 0)))
    canonical_anchor_rotation = int(anchor.get("rotation") or 0) % 6
    rotation_steps = (int(anchor_rotation) - canonical_anchor_rotation) % 6

    def transform_point(raw: list[int] | tuple[int, int]) -> list[int]:
        point = tuple(int(value) for value in raw)
        relative = (point[0] - canonical_anchor_position[0], point[1] - canonical_anchor_position[1])
        rotated = rotate_hex(relative, rotation_steps)
        return [int(anchor_position[0]) + rotated[0], int(anchor_position[1]) + rotated[1]]

    result = []
    for index, raw_part in enumerate(geometry.get("parts", [])):
        part = deepcopy(raw_part)
        part["id"] = f"{instance_id}:part-{index}"
        part["position"] = transform_point(part.get("position") or [0, 0])
        part["rotation"] = (int(part.get("rotation") or 0) + rotation_steps) % 6
        if part.get("trackHexes"):
            part["trackHexes"] = [transform_point(cell) for cell in part.get("trackHexes", [])]
        if part.get("pipeHexes"):
            part["pipeHexes"] = [transform_point(cell) for cell in part.get("pipeHexes", [])]
        part["sourceFragmentInstance"] = instance_id
        result.append(part)
    return result


def _part_signature(part: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(part.get("type") or ""),
        tuple(part.get("position") or (0, 0)),
        int(part.get("rotation") or 0),
        int(part.get("length") or 0),
        int(part.get("which") or 0),
        tuple(tuple(cell) for cell in part.get("trackHexes", [])),
        tuple(tuple(cell) for cell in part.get("pipeHexes", [])),
    )


def _dedupe_parts(parts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    origins: defaultdict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for part in parts:
        signature = _part_signature(part)
        unique.setdefault(signature, part)
    for part in unique.values():
        origins[tuple(part.get("position") or (0, 0))].append(part)

    conflicts = []
    for position, colocated in sorted(origins.items()):
        types = sorted({str(part.get("type") or "") for part in colocated})
        if len(colocated) > 1 and len(types) > 1:
            conflicts.append({
                "position": list(position),
                "partTypes": types,
                "partIds": [part.get("id") for part in colocated],
                "kind": "part-origin-overlap",
            })
    return list(unique.values()), conflicts


def materialize_assembly_layout(candidate: dict[str, Any], fragment_index: dict[str, Any]) -> dict[str, Any]:
    """Materialize a convergence-aware assembly candidate in one axial frame.

    The convergence target is anchored at (0,0), rotation 0. Branches are
    propagated backwards using same-solution convergence transforms and
    transition transforms; the tail is propagated forwards toward output.
    """
    geometries = _geometry_lookup(fragment_index)
    convergence = candidate.get("convergence") or {}
    target_key = _key(convergence.get("targetRole"), convergence.get("targetMechanismHash"))

    placements: list[dict[str, Any]] = []
    all_parts: list[dict[str, Any]] = []
    missing_geometry = []
    missing_transform = []

    def add_instance(instance_id: str, key: FragmentKey, position: tuple[int, int], rotation: int) -> None:
        geometry = geometries.get(key)
        placements.append({
            "instanceId": instance_id,
            "role": key[0],
            "canonicalMechanismHash": key[1],
            "anchorPosition": list(position),
            "anchorRotation": rotation,
        })
        if geometry is None:
            missing_geometry.append({"instanceId": instance_id, "role": key[0], "canonicalMechanismHash": key[1]})
            return
        all_parts.extend(transplant_geometry(geometry, anchor_position=position, anchor_rotation=rotation, instance_id=instance_id))

    convergence_position = (0, 0)
    convergence_rotation = 0
    add_instance("convergence", target_key, convergence_position, convergence_rotation)

    occurrence_counter: defaultdict[FragmentKey, int] = defaultdict(int)
    motif_inputs = list(convergence.get("inputs", []))
    branches = list(candidate.get("branches", []))
    for branch_index, branch in enumerate(branches):
        input_item = motif_inputs[branch_index] if branch_index < len(motif_inputs) else {}
        input_key = _key(input_item.get("sourceRole"), input_item.get("sourceMechanismHash"))
        occurrence = occurrence_counter[input_key]
        occurrence_counter[input_key] += 1
        transform = _motif_input_transform(convergence, input_item, occurrence)
        if transform is None:
            missing_transform.append({"branch": branch_index, "stage": "convergence-input", "key": list(input_key)})
            continue
        current_position, current_rotation = apply_inverse_transform(convergence_position, convergence_rotation, transform)
        current_key = input_key
        add_instance(f"branch-{branch_index}:input", current_key, current_position, current_rotation)

        for reverse_index, edge in enumerate(reversed(branch)):
            edge_transform = _preferred_transform(edge)
            source_key = _key(edge.get("sourceRole"), edge.get("sourceMechanismHash"))
            if edge_transform is None:
                missing_transform.append({"branch": branch_index, "stage": "branch-edge", "edge": edge})
                break
            current_position, current_rotation = apply_inverse_transform(current_position, current_rotation, edge_transform)
            current_key = source_key
            add_instance(f"branch-{branch_index}:upstream-{reverse_index}", current_key, current_position, current_rotation)

    current_position, current_rotation = convergence_position, convergence_rotation
    for tail_index, edge in enumerate(candidate.get("tail", [])):
        transform = _preferred_transform(edge)
        target = _key(edge.get("targetRole"), edge.get("targetMechanismHash"))
        if transform is None:
            missing_transform.append({"tail": tail_index, "stage": "tail-edge", "edge": edge})
            break
        current_position, current_rotation = apply_forward_transform(current_position, current_rotation, transform)
        add_instance(f"tail-{tail_index}", target, current_position, current_rotation)

    parts, conflicts = _dedupe_parts(all_parts)
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "instanceCount": len(placements),
            "materializedPartCount": len(parts),
            "missingGeometryCount": len(missing_geometry),
            "missingTransformCount": len(missing_transform),
            "originConflictCount": len(conflicts),
            "layoutComplete": not missing_geometry and not missing_transform,
        },
        "placements": placements,
        "parts": parts,
        "conflicts": conflicts,
        "missingGeometry": missing_geometry,
        "missingTransforms": missing_transform,
        "limitations": [
            "Conflict detection currently checks part-origin overlap only, not full occupied footprints or swept arm paths.",
            "Programs remain fragment-local normalized tapes and are not yet globally synchronized.",
            "A materialized layout is a geometry candidate, not yet a valid Opus Magnum solution."
        ],
    }
