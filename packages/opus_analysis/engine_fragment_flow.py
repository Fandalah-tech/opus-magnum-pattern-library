from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from packages.opus_engine import Simulator

from .canonical import rotate_hex
from .fragments import extract_solution_fragments
from .timeline import build_program_timeline

TRIPLEX_CHANNEL_ORDER = ("red", "black", "yellow")

EVENT_RELATIONS = {
    "bond-created": "bond-created",
    "bond-removed": "bond-removed",
    "atom-calcified": "calcify",
    "atom-duplicated": "duplicate",
    "atoms-animated": "animate",
    "atom-purified": "purify",
    "atom-projected": "project",
    "atom-rejected": "reject",
    "atom-divided": "divide",
    "atoms-unified": "unify",
    "atom-proliferated": "proliferate",
    "molecule-entered-conduit": "conduit-entered",
    "molecule-exited-conduit": "conduit-exited",
    "product-delivered": "delivered",
    "molecule-consumed": "consumed",
}


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


def _event_anchor(event: dict[str, Any]) -> str:
    for key in ("glyphPartId", "consumerPartId", "conduitPartId"):
        if event.get(key):
            return str(event[key])
    return ""


def _event_atoms(event: dict[str, Any]) -> set[str]:
    result = {
        str(event[key])
        for key in (
            "atomId", "fromAtomId", "toAtomId", "sourceAtomId", "transformedAtomId",
            "consumedAtomId", "producedAtomId",
        )
        if event.get(key)
    }
    for key in ("atomIds", "consumedAtomIds", "producedAtomIds"):
        result.update(str(value) for value in event.get(key, []) if value)
    return result


def _frame_components(frame: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for molecule in frame.get("world", {}).get("molecules", []):
        atom_ids = {str(value) for value in molecule.get("atomIds", []) if value}
        for atom_id in atom_ids:
            result[atom_id] = atom_ids
    return result


def _functional_events(frame: dict[str, Any]) -> list[tuple[str, str, set[str]]]:
    events = list(frame.get("events", []))
    result: list[tuple[str, str, set[str]]] = []
    triplex: defaultdict[str, dict[str, Any]] = defaultdict(lambda: {"channels": set(), "atoms": set()})
    for event in events:
        kind = str(event.get("kind") or "")
        anchor = _event_anchor(event)
        if kind == "bond-created" and event.get("triplexChannel") and anchor:
            triplex[anchor]["channels"].add(str(event["triplexChannel"]))
            triplex[anchor]["atoms"].update(_event_atoms(event))
            continue
        relation = EVENT_RELATIONS.get(kind)
        if relation and anchor:
            result.append((anchor, relation, _event_atoms(event)))
    for anchor, payload in sorted(triplex.items()):
        channels = [channel for channel in TRIPLEX_CHANNEL_ORDER if channel in payload["channels"]]
        relation = f"triplex-bond-created:{'+'.join(channels)}"
        result.append((anchor, relation, set(payload["atoms"])))
    return result


def _engine_complete(solution: dict[str, Any], simulator: Simulator) -> bool:
    standard_outputs = [
        str(part.get("id"))
        for part in solution.get("parts", [])
        if part.get("type") == "out-std"
    ]
    repeating_outputs = [
        str(part.get("id"))
        for part in solution.get("parts", [])
        if part.get("type") == "out-rep"
    ]
    return bool(standard_outputs or repeating_outputs) and (
        all(int(simulator.delivered_products.get(output_id, 0)) >= 6 for output_id in standard_outputs)
        and all(simulator.repeating_product_complete(output_id, 3) for output_id in repeating_outputs)
    )


def build_engine_fragment_flow_graph(puzzle: dict[str, Any], solution: dict[str, Any]) -> dict[str, Any]:
    """Learn fragment transitions only from the collision-aware engine trace."""

    fragments = extract_solution_fragments(solution)
    by_anchor = {str(fragment["anchorPartId"]): fragment for fragment in fragments}
    parts_by_id = {
        str(part.get("id") or ""): part
        for part in solution.get("parts", [])
        if part.get("id")
    }
    feed_anchors = {
        anchor for anchor, fragment in by_anchor.items() if fragment.get("role") == "feed"
    }
    timeline = build_program_timeline(solution)
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(timeline)

    atom_owner: dict[str, str] = {}
    if replay.get("frames"):
        for atom in replay["frames"][0].get("world", {}).get("atoms", []):
            atom_id = str(atom.get("id") or "")
            owner = next((anchor for anchor in feed_anchors if atom_id.startswith(f"{anchor}-spawn-")), None)
            if owner:
                atom_owner[atom_id] = owner

    edge_counts: Counter[tuple[str, str, str]] = Counter()
    edge_cycles: defaultdict[tuple[str, str, str], list[int]] = defaultdict(list)
    node_relations: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for frame in replay.get("frames", [])[1:]:
        cycle = int(frame.get("cycle") or 0)
        components = _frame_components(frame)
        owner_before_frame = dict(atom_owner)
        pending_owners: list[tuple[str, set[str]]] = []
        for event in frame.get("events", []):
            if event.get("kind") == "input-spawned" and str(event.get("inputId") or "") in feed_anchors:
                owner = str(event["inputId"])
                for atom_id in _event_atoms(event):
                    atom_owner[atom_id] = owner

        for anchor, relation, affected_atoms in _functional_events(frame):
            if anchor not in by_anchor or not affected_atoms:
                continue
            node_relations[anchor][relation] += 1
            predecessors = sorted({
                owner_before_frame[atom_id]
                for atom_id in affected_atoms
                if atom_id in owner_before_frame and owner_before_frame[atom_id] != anchor
            })
            for predecessor in predecessors:
                key = (predecessor, anchor, relation)
                edge_counts[key] += 1
                edge_cycles[key].append(cycle)
            owned_atoms = set(affected_atoms)
            for atom_id in tuple(affected_atoms):
                owned_atoms.update(components.get(atom_id, ()))
            pending_owners.append((anchor, owned_atoms))
        for anchor, atom_ids in pending_owners:
            for atom_id in atom_ids:
                atom_owner[atom_id] = anchor

    nodes = []
    for fragment in fragments:
        anchor = str(fragment["anchorPartId"])
        part = parts_by_id.get(anchor, {})
        relations = node_relations[anchor]
        nodes.append({
            "anchorPartId": anchor,
            "anchorPartType": fragment.get("anchorPartType"),
            "anchorPosition": list(part.get("position") or [0, 0]),
            "anchorRotation": int(part.get("rotation") or 0) % 6,
            "programStartCycle": _program_start(fragment),
            "role": fragment.get("role"),
            "canonicalMechanismHash": fragment.get("canonicalMechanismHash"),
            "canonicalStructuralHash": fragment.get("canonicalStructuralHash"),
            "evidenceLevel": "engine-confirmed" if relations else "engine-observed-structural",
            "observedRelations": dict(sorted(relations.items())),
        })

    edges = []
    for (source, target, relation), count in sorted(edge_counts.items()):
        source_fragment = by_anchor[source]
        target_fragment = by_anchor[target]
        cycles = edge_cycles[(source, target, relation)]
        edges.append({
            "sourceAnchorPartId": source,
            "targetAnchorPartId": target,
            "sourceRole": source_fragment.get("role"),
            "targetRole": target_fragment.get("role"),
            "sourceMechanismHash": source_fragment.get("canonicalMechanismHash"),
            "targetMechanismHash": target_fragment.get("canonicalMechanismHash"),
            "relation": relation,
            "relativeTransform": _relative_transform(parts_by_id.get(source, {}), parts_by_id.get(target, {})),
            "relativeTiming": _relative_timing(source_fragment, target_fragment, cycles),
            "observationCount": count,
            "firstCycle": min(cycles),
            "lastCycle": max(cycles),
            "engineValidated": True,
        })

    complete = _engine_complete(solution, simulator)
    terminated = bool(replay.get("summary", {}).get("terminatedWithError"))
    return {
        "schemaVersion": "0.1.0",
        "analysis": "collision-aware-engine-fragment-flow",
        "source": {
            "puzzleFile": solution.get("puzzleFile"),
            "solutionSha256": solution.get("source", {}).get("sha256"),
        },
        "engineValidation": {
            "complete": complete,
            "terminatedWithError": terminated,
            "terminatedAfterCompletion": bool(complete and terminated),
            "completedCycles": int(replay.get("summary", {}).get("completedCycles") or 0),
        },
        "summary": {
            "fragmentCount": len(nodes),
            "flowEdgeCount": len(edges),
            "flowObservationCount": sum(edge_counts.values()),
            "engineConfirmedFragmentCount": sum(node["evidenceLevel"] == "engine-confirmed" for node in nodes),
            "traceFrameCount": len(replay.get("frames", [])),
        },
        "nodes": nodes,
        "edges": edges,
    }
