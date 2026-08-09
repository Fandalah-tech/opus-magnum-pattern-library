from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .canonical import rotate_hex
from .fragment_evidence import trace_fragment_evidence
from .fragments import extract_solution_fragments
from .replay_glyphs import build_replay_trace
from .timeline import build_program_timeline


def _atom_ids(molecule: dict[str, Any]) -> set[str]:
    return {str(atom.get("id") or "") for atom in molecule.get("atoms", []) if atom.get("id")}


def _molecules_by_id(frame: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(molecule.get("id") or ""): molecule for molecule in frame.get("molecules", []) if molecule.get("id")}


def _relative_transform(source_part: dict[str, Any], target_part: dict[str, Any]) -> dict[str, Any]:
    sq, sr = (int(value) for value in (source_part.get("position") or (0, 0)))
    tq, tr = (int(value) for value in (target_part.get("position") or (0, 0)))
    source_rotation = int(source_part.get("rotation") or 0) % 6
    target_rotation = int(target_part.get("rotation") or 0) % 6
    local_delta = rotate_hex((tq - sq, tr - sr), -source_rotation)
    return {
        "frame": "source-anchor-local",
        "delta": [int(local_delta[0]), int(local_delta[1])],
        "rotationDelta": (target_rotation - source_rotation) % 6,
    }


def _program_start(fragment: dict[str, Any]) -> int | None:
    value = fragment.get("summary", {}).get("firstInstructionCycle")
    return int(value) if isinstance(value, int) else None


def _relative_timing(source_fragment: dict[str, Any], target_fragment: dict[str, Any], cycles: list[int]) -> dict[str, Any]:
    source_start = _program_start(source_fragment)
    target_start = _program_start(target_fragment)
    event_first = min(cycles) if cycles else None
    event_last = max(cycles) if cycles else None
    return {
        "frame": "source-fragment-program-start",
        "sourceProgramStart": source_start,
        "targetProgramStart": target_start,
        "programStartDelta": (target_start - source_start) if source_start is not None and target_start is not None else None,
        "eventFirstCycle": event_first,
        "eventLastCycle": event_last,
        "eventFirstFromSourceStart": (event_first - source_start) if event_first is not None and source_start is not None else None,
        "eventFirstFromTargetStart": (event_first - target_start) if event_first is not None and target_start is not None else None,
    }


def build_fragment_flow_graph(puzzle: dict[str, Any], solution: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct replay-observed molecule flow between functional fragments.

    Edge geometry is expressed in the source anchor frame; edge timing is
    expressed relative to fragment program starts. Both remain stable under a
    global placement or global program-cycle shift of the historical solution.
    """
    fragments = extract_solution_fragments(solution)
    annotated = {item["anchorPartId"]: item for item in trace_fragment_evidence(puzzle, solution)}
    by_anchor = {item["anchorPartId"]: item for item in fragments}
    parts_by_id = {str(part.get("id") or ""): part for part in solution.get("parts", []) if part.get("id")}

    timeline = build_program_timeline(solution)
    trace = build_replay_trace(puzzle, solution, timeline)
    frames = list(trace.get("frames", []))

    atom_owner: dict[str, str] = {}
    edge_counts: Counter[tuple[str, str, str]] = Counter()
    edge_cycles: defaultdict[tuple[str, str, str], list[int]] = defaultdict(list)

    if frames:
        for molecule in frames[0].get("molecules", []):
            source = str(molecule.get("sourcePartId") or "")
            if source in by_anchor:
                for atom_id in _atom_ids(molecule):
                    atom_owner[atom_id] = source

    for frame_index, frame in enumerate(frames[1:], start=1):
        previous = frames[frame_index - 1]
        previous_molecules = _molecules_by_id(previous)
        current_molecules = _molecules_by_id(frame)
        cycle = int(frame.get("cycle", frame_index - 1))

        for molecule in frame.get("molecules", []):
            source = str(molecule.get("sourcePartId") or "")
            if source in by_anchor:
                for atom_id in _atom_ids(molecule):
                    atom_owner.setdefault(atom_id, source)

        for event in frame.get("events", []):
            kind = str(event.get("kind") or "")
            anchor = ""
            affected_atoms: set[str] = set()
            relation = ""

            if kind == "glyph-effect":
                anchor = str(event.get("glyphPartId") or "")
                relation = str(event.get("effect") or "glyph-effect")
                molecule_ids = []
                if event.get("moleculeId"):
                    molecule_ids.append(str(event["moleculeId"]))
                molecule_ids.extend(str(value) for value in event.get("moleculeIds", []) if value)
                for molecule_id in molecule_ids:
                    molecule = current_molecules.get(molecule_id) or previous_molecules.get(molecule_id)
                    if molecule:
                        affected_atoms.update(_atom_ids(molecule))
                if event.get("effect") == "bond-created" and event.get("moleculeId"):
                    molecule = current_molecules.get(str(event["moleculeId"]))
                    if molecule:
                        affected_atoms.update(_atom_ids(molecule))

            elif kind in {"product-delivered", "molecule-consumed"}:
                anchor = str(event.get("consumerPartId") or "")
                relation = "delivered" if kind == "product-delivered" else "consumed"
                molecule_id = str(event.get("moleculeId") or "")
                molecule = previous_molecules.get(molecule_id)
                if molecule:
                    affected_atoms.update(_atom_ids(molecule))

            if not anchor or anchor not in by_anchor or not affected_atoms:
                continue

            predecessors = sorted({atom_owner[atom_id] for atom_id in affected_atoms if atom_id in atom_owner and atom_owner[atom_id] != anchor})
            for predecessor in predecessors:
                key = (predecessor, anchor, relation)
                edge_counts[key] += 1
                edge_cycles[key].append(cycle)

            for atom_id in affected_atoms:
                atom_owner[atom_id] = anchor

    nodes = []
    for fragment in fragments:
        anchor = str(fragment["anchorPartId"])
        evidence = annotated.get(anchor, {}).get("evidence", {})
        part = parts_by_id.get(anchor, {})
        nodes.append({
            "anchorPartId": anchor,
            "anchorPartType": fragment.get("anchorPartType"),
            "anchorPosition": list(part.get("position") or [0, 0]),
            "anchorRotation": int(part.get("rotation") or 0) % 6,
            "programStartCycle": _program_start(fragment),
            "role": fragment.get("role"),
            "canonicalMechanismHash": fragment.get("canonicalMechanismHash"),
            "canonicalStructuralHash": fragment.get("canonicalStructuralHash"),
            "evidenceLevel": evidence.get("level", "structural-only"),
        })

    edges = []
    for (source, target, relation), count in sorted(edge_counts.items()):
        source_fragment = by_anchor[source]
        target_fragment = by_anchor[target]
        cycles = edge_cycles[(source, target, relation)]
        source_part = parts_by_id.get(source, {})
        target_part = parts_by_id.get(target, {})
        edges.append({
            "sourceAnchorPartId": source,
            "targetAnchorPartId": target,
            "sourceRole": source_fragment.get("role"),
            "targetRole": target_fragment.get("role"),
            "sourceMechanismHash": source_fragment.get("canonicalMechanismHash"),
            "targetMechanismHash": target_fragment.get("canonicalMechanismHash"),
            "relation": relation,
            "relativeTransform": _relative_transform(source_part, target_part),
            "relativeTiming": _relative_timing(source_fragment, target_fragment, cycles),
            "observationCount": count,
            "firstCycle": min(cycles),
            "lastCycle": max(cycles),
        })

    return {
        "schemaVersion": "0.3.0",
        "analysis": "replay-backed-fragment-molecule-flow",
        "source": {
            "puzzleFile": solution.get("puzzleFile"),
            "solutionSha256": solution.get("source", {}).get("sha256"),
        },
        "summary": {
            "fragmentCount": len(nodes),
            "flowEdgeCount": len(edges),
            "flowObservationCount": sum(edge_counts.values()),
            "dynamicConfirmedFragmentCount": sum(node["evidenceLevel"] == "dynamic-confirmed" for node in nodes),
            "traceFrameCount": len(frames),
        },
        "nodes": nodes,
        "edges": edges,
        "limitations": [
            "Only replay-observed functional events create flow edges.",
            "Unsupported glyphs cannot yet create transformation edges.",
            "Relative transforms describe anchor adjacency; relative timing describes fragment program starts.",
            "Collision correctness still requires external validation."
        ],
    }
