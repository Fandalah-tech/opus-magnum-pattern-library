from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from packages.opus_analysis.canonical import rotate_hex

from .layout_diagnostics import analyze_layout_geometry

FragmentKey = tuple[str, str]
GeometryKey = tuple[str, str, str]


def _key(role: Any, mechanism: Any) -> FragmentKey:
    return str(role or ""), str(mechanism or "")


def _geometry_lookup(
    fragment_index: dict[str, Any],
    *,
    coherent_source_solution: str | None = None,
) -> dict[GeometryKey, dict[str, Any]]:
    result = {}
    for item in fragment_index.get("fragments", []):
        geometry = item.get("representativeGeometry")
        key = _key(item.get("role"), item.get("canonicalMechanismHash"))
        if geometry:
            result[(key[0], key[1], "")] = geometry
        if coherent_source_solution:
            for record in item.get("solutionGeometries", []):
                if (
                    str(record.get("solutionPath") or "") != coherent_source_solution
                    or not record.get("representativeGeometry")
                ):
                    continue
                source_anchor = str(
                    record.get("sourceAnchorPartId")
                    or (record.get("representativeGeometry") or {}).get("sourceAnchorPartId")
                    or ""
                )
                result[(key[0], key[1], source_anchor)] = record["representativeGeometry"]
        elif geometry:
            source_anchor = str(geometry.get("sourceAnchorPartId") or "")
            if source_anchor:
                result[(key[0], key[1], source_anchor)] = geometry
    return result


def _geometry_for(
    geometries: dict[GeometryKey, dict[str, Any]],
    key: FragmentKey,
    source_anchor_part_id: str | None,
) -> dict[str, Any] | None:
    source_anchor = str(source_anchor_part_id or "")
    return geometries.get((key[0], key[1], source_anchor)) or geometries.get((key[0], key[1], ""))


def _motif_input_record(
    convergence: dict[str, Any],
    input_item: dict[str, Any],
    occurrence: int,
) -> dict[str, Any] | None:
    role = str(input_item.get("sourceRole") or "")
    mechanism = str(input_item.get("sourceMechanismHash") or "")
    for sample in convergence.get("samples", []):
        matches = [
            item for item in sample.get("inputs", [])
            if str(item.get("sourceRole") or "") == role
            and str(item.get("sourceMechanismHash") or "") == mechanism
        ]
        if occurrence < len(matches):
            return matches[occurrence]
    return None


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
    record = _motif_input_record(convergence, input_item, occurrence)
    if record:
        transforms = record.get("relativeTransforms", [])
        if transforms:
            return transforms[0]
    return None


def _anchor_part(geometry: dict[str, Any]) -> dict[str, Any] | None:
    anchor_type = str(geometry.get("anchorPartType") or "")
    return next((part for part in geometry.get("parts", []) if str(part.get("type") or "") == anchor_type), None)


def transplant_geometry(
    geometry: dict[str, Any],
    *,
    anchor_position: tuple[int, int],
    anchor_rotation: int,
    instance_id: str,
    source_anchor_part_id: str | None = None,
) -> list[dict[str, Any]]:
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
            part["trackHexes"] = [
                list(rotate_hex(tuple(int(value) for value in cell), rotation_steps))
                for cell in part.get("trackHexes", [])
            ]
        if part.get("pipeHexes"):
            part["pipeHexes"] = [
                [int(value) for value in cell]
                for cell in part.get("pipeHexes", [])
            ]
        part["sourceFragmentInstance"] = instance_id
        part["sourceFragmentAnchorPartId"] = str(
            source_anchor_part_id
            or geometry.get("sourceAnchorPartId")
            or ""
        )
        source_namespace = str(
            geometry.get("sourceSolutionSha256")
            or geometry.get("sourceSolutionPath")
            or ""
        )
        source_part_id = str(part.get("sourcePartId") or "")
        if source_namespace and source_part_id:
            part["sourceComponentId"] = f"{source_namespace}::{source_part_id}"
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


def _part_identity(part: dict[str, Any]) -> tuple[Any, ...]:
    source_component_id = str(part.get("sourceComponentId") or "")
    if source_component_id:
        return "source-component", source_component_id
    return "physical-signature", *_part_signature(part)


def _proposal_priority(part: dict[str, Any]) -> tuple[Any, ...]:
    source_part_id = str(part.get("sourcePartId") or "")
    source_anchor = str(part.get("sourceFragmentAnchorPartId") or "")
    return (
        0 if source_part_id and source_part_id == source_anchor else 1,
        str(part.get("sourceFragmentInstance") or ""),
        _part_signature(part),
    )


def _dedupe_parts(
    parts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    proposals: defaultdict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for part in parts:
        proposals[_part_identity(part)].append(part)

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    resolved_pose_count = 0
    shared_identity_count = 0
    for identity, identity_proposals in proposals.items():
        retained = deepcopy(min(identity_proposals, key=_proposal_priority))
        signatures = {_part_signature(part) for part in identity_proposals}
        source_identity = identity[0] == "source-component"
        if source_identity and len(identity_proposals) > 1:
            shared_identity_count += 1
        if source_identity and len(signatures) > 1:
            resolved_pose_count += 1
        instances = sorted({
            str(part.get("sourceFragmentInstance") or "")
            for part in identity_proposals
            if part.get("sourceFragmentInstance")
        })
        retained["sourceFragmentInstances"] = instances
        retained["programContributions"] = {
            str(part.get("sourceFragmentInstance")): deepcopy(part.get("program", []))
            for part in identity_proposals
            if part.get("sourceFragmentInstance")
        }
        retained["sourcePoseProposalCount"] = len(identity_proposals)
        retained["sourcePoseVariantCount"] = len(signatures)
        unique[identity] = retained

    origins: defaultdict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
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
    return list(unique.values()), conflicts, {
        "sourceIdentityPartCount": sum(identity[0] == "source-component" for identity in unique),
        "sharedSourceIdentityCount": shared_identity_count,
        "resolvedSourcePoseCount": resolved_pose_count,
        "rawPartProposalCount": len(parts),
    }


def materialize_assembly_layout(
    candidate: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    transform_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    coherent_source_solution = str(candidate.get("coherentSourceSolution") or "") or None
    geometries = _geometry_lookup(
        fragment_index,
        coherent_source_solution=coherent_source_solution,
    )
    convergence = candidate.get("convergence") or {}
    target_key = _key(convergence.get("targetRole"), convergence.get("targetMechanismHash"))
    overrides = transform_overrides or {}

    placements: list[dict[str, Any]] = []
    all_parts: list[dict[str, Any]] = []
    missing_geometry = []
    missing_transform = []
    used_transforms: dict[str, dict[str, Any]] = {}

    def add_instance(
        instance_id: str,
        key: FragmentKey,
        position: tuple[int, int],
        rotation: int,
        source_anchor_part_id: str | None = None,
    ) -> None:
        geometry = _geometry_for(geometries, key, source_anchor_part_id)
        placements.append({
            "instanceId": instance_id,
            "role": key[0],
            "canonicalMechanismHash": key[1],
            "sourceAnchorPartId": source_anchor_part_id,
            "anchorPosition": list(position),
            "anchorRotation": rotation,
        })
        if geometry is None:
            missing_geometry.append({"instanceId": instance_id, "role": key[0], "canonicalMechanismHash": key[1]})
            return
        all_parts.extend(transplant_geometry(
            geometry,
            anchor_position=position,
            anchor_rotation=rotation,
            instance_id=instance_id,
            source_anchor_part_id=source_anchor_part_id,
        ))

    def select_transform(slot: str, fallback: dict[str, Any] | None) -> dict[str, Any] | None:
        selected = overrides.get(slot) or fallback
        if selected is not None:
            used_transforms[slot] = deepcopy(selected)
        return selected

    convergence_position = (0, 0)
    convergence_rotation = 0
    convergence_sample = next(iter(convergence.get("samples", [])), {})
    convergence_anchor_id = str(
        convergence_sample.get("targetAnchorPartId")
        or convergence.get("targetAnchorPartId")
        or ""
    ) or None
    add_instance(
        "convergence",
        target_key,
        convergence_position,
        convergence_rotation,
        convergence_anchor_id,
    )

    occurrence_counter: defaultdict[FragmentKey, int] = defaultdict(int)
    motif_inputs = list(convergence.get("inputs", []))
    branches = list(candidate.get("branches", []))
    for branch_index, branch in enumerate(branches):
        input_item = motif_inputs[branch_index] if branch_index < len(motif_inputs) else {}
        input_key = _key(input_item.get("sourceRole"), input_item.get("sourceMechanismHash"))
        occurrence = occurrence_counter[input_key]
        occurrence_counter[input_key] += 1
        input_record = _motif_input_record(convergence, input_item, occurrence) or {}
        input_anchor_id = str(input_record.get("sourceAnchorPartId") or "") or None
        slot = f"branch-{branch_index}:convergence-input"
        transform = select_transform(slot, _motif_input_transform(convergence, input_item, occurrence))
        if transform is None:
            missing_transform.append({"branch": branch_index, "stage": "convergence-input", "key": list(input_key), "slot": slot})
            continue
        current_position, current_rotation = apply_inverse_transform(convergence_position, convergence_rotation, transform)
        add_instance(
            f"branch-{branch_index}:input",
            input_key,
            current_position,
            current_rotation,
            input_anchor_id,
        )

        for reverse_index, edge in enumerate(reversed(branch)):
            slot = f"branch-{branch_index}:edge-{reverse_index}"
            edge_transform = select_transform(slot, _preferred_transform(edge))
            source_key = _key(edge.get("sourceRole"), edge.get("sourceMechanismHash"))
            if edge_transform is None:
                missing_transform.append({"branch": branch_index, "stage": "branch-edge", "edge": edge, "slot": slot})
                break
            current_position, current_rotation = apply_inverse_transform(current_position, current_rotation, edge_transform)
            add_instance(
                f"branch-{branch_index}:upstream-{reverse_index}",
                source_key,
                current_position,
                current_rotation,
                str(edge.get("sourceAnchorPartId") or "") or None,
            )

    current_position, current_rotation = convergence_position, convergence_rotation
    for tail_index, edge in enumerate(candidate.get("tail", [])):
        slot = f"tail-{tail_index}:edge"
        transform = select_transform(slot, _preferred_transform(edge))
        target = _key(edge.get("targetRole"), edge.get("targetMechanismHash"))
        if transform is None:
            missing_transform.append({"tail": tail_index, "stage": "tail-edge", "edge": edge, "slot": slot})
            break
        current_position, current_rotation = apply_forward_transform(current_position, current_rotation, transform)
        add_instance(
            f"tail-{tail_index}",
            target,
            current_position,
            current_rotation,
            str(edge.get("targetAnchorPartId") or "") or None,
        )

    parts, conflicts, component_summary = _dedupe_parts(all_parts)
    geometry_diagnostics = analyze_layout_geometry(parts)
    geometry_summary = geometry_diagnostics["summary"]
    return {
        "schemaVersion": "0.5.0",
        "summary": {
            "instanceCount": len(placements),
            "materializedPartCount": len(parts),
            "sharedPartCount": sum(len(part.get("sourceFragmentInstances", [])) > 1 for part in parts),
            "missingGeometryCount": len(missing_geometry),
            "missingTransformCount": len(missing_transform),
            "originConflictCount": len(conflicts),
            "exactStaticConflictCount": geometry_summary["exactStaticConflictCount"],
            "approximateStaticConflictCount": geometry_summary["approximateStaticConflictCount"],
            "armWorkspaceOverlapCount": geometry_summary["armWorkspaceOverlapCount"],
            "transformOverrideCount": len(overrides),
            "sourceSpecificGeometry": bool(coherent_source_solution),
            **component_summary,
            "layoutComplete": not missing_geometry and not missing_transform,
        },
        "placements": placements,
        "parts": parts,
        "conflicts": conflicts,
        "geometryDiagnostics": geometry_diagnostics,
        "missingGeometry": missing_geometry,
        "missingTransforms": missing_transform,
        "usedTransforms": used_transforms,
        "transformOverrides": deepcopy(overrides),
        "limitations": [
            "Static footprint conflicts and arm workspace overlaps are diagnostics; engine/OMSim validation remains authoritative.",
            "Arm workspace overlap is not treated as invalid because interacting mechanisms routinely share reachable cells.",
            "Deduplicated shared parts retain all fragment-local program contributions for later synchronization.",
            "A materialized layout is a geometry candidate, not yet a valid Opus Magnum solution."
        ],
    }


def materialize_fragment_chain_layout(
    candidate: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    transform_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Transplant a linear replay-backed fragment chain into one layout."""
    geometries = _geometry_lookup(fragment_index)
    overrides = transform_overrides or {}
    nodes = list(candidate.get("nodes", []))
    steps = list(candidate.get("steps", []))
    placements: list[dict[str, Any]] = []
    all_parts: list[dict[str, Any]] = []
    missing_geometry = []
    missing_transform = []
    used_transforms: dict[str, dict[str, Any]] = {}

    def add_instance(instance_id: str, key: FragmentKey, position: tuple[int, int], rotation: int) -> None:
        geometry = _geometry_for(geometries, key, None)
        placements.append({
            "instanceId": instance_id,
            "role": key[0],
            "canonicalMechanismHash": key[1],
            "anchorPosition": list(position),
            "anchorRotation": rotation,
        })
        if geometry is None:
            missing_geometry.append({
                "instanceId": instance_id,
                "role": key[0],
                "canonicalMechanismHash": key[1],
            })
            return
        all_parts.extend(transplant_geometry(
            geometry,
            anchor_position=position,
            anchor_rotation=rotation,
            instance_id=instance_id,
        ))

    if not nodes:
        missing_geometry.append({"instanceId": "chain-0", "reason": "chain-has-no-nodes"})
    else:
        current_position = (0, 0)
        current_rotation = 0
        first = nodes[0]
        add_instance(
            "chain-0",
            _key(first.get("role"), first.get("canonicalMechanismHash")),
            current_position,
            current_rotation,
        )
        for step_index, step in enumerate(steps):
            slot = f"chain-{step_index}:edge"
            transform = overrides.get(slot) or _preferred_transform(step)
            if transform is None:
                missing_transform.append({"step": step_index, "stage": "chain-edge", "edge": step, "slot": slot})
                break
            used_transforms[slot] = deepcopy(transform)
            current_position, current_rotation = apply_forward_transform(
                current_position,
                current_rotation,
                transform,
            )
            target = nodes[step_index + 1] if step_index + 1 < len(nodes) else step
            add_instance(
                f"chain-{step_index + 1}",
                _key(target.get("role") or step.get("targetRole"), target.get("canonicalMechanismHash") or step.get("targetMechanismHash")),
                current_position,
                current_rotation,
            )

    parts, conflicts, component_summary = _dedupe_parts(all_parts)
    geometry_diagnostics = analyze_layout_geometry(parts)
    geometry_summary = geometry_diagnostics["summary"]
    return {
        "schemaVersion": "0.2.0",
        "candidateKind": "linear-chain",
        "summary": {
            "instanceCount": len(placements),
            "materializedPartCount": len(parts),
            "sharedPartCount": sum(len(part.get("sourceFragmentInstances", [])) > 1 for part in parts),
            "missingGeometryCount": len(missing_geometry),
            "missingTransformCount": len(missing_transform),
            "originConflictCount": len(conflicts),
            "exactStaticConflictCount": geometry_summary["exactStaticConflictCount"],
            "approximateStaticConflictCount": geometry_summary["approximateStaticConflictCount"],
            "armWorkspaceOverlapCount": geometry_summary["armWorkspaceOverlapCount"],
            "transformOverrideCount": len(overrides),
            **component_summary,
            "layoutComplete": not missing_geometry and not missing_transform and len(placements) == len(nodes),
        },
        "placements": placements,
        "parts": parts,
        "conflicts": conflicts,
        "geometryDiagnostics": geometry_diagnostics,
        "missingGeometry": missing_geometry,
        "missingTransforms": missing_transform,
        "usedTransforms": used_transforms,
        "transformOverrides": deepcopy(overrides),
        "limitations": [
            "The chain joins canonical engine-validated fragments; the composed layout still requires engine replay.",
            "Static footprint conflicts are ranking signals, not authoritative simulation results.",
        ],
    }


def materialize_candidate_layout(
    candidate: dict[str, Any],
    fragment_index: dict[str, Any],
    *,
    transform_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if candidate.get("candidateKind") == "linear-chain" or (candidate.get("nodes") and candidate.get("steps")):
        return materialize_fragment_chain_layout(
            candidate,
            fragment_index,
            transform_overrides=transform_overrides,
        )
    return materialize_assembly_layout(
        candidate,
        fragment_index,
        transform_overrides=transform_overrides,
    )
