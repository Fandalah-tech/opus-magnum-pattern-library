from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .fragment_evidence import trace_fragment_evidence
from .fragments import extract_solution_fragments
from .replay_glyphs import build_replay_trace
from .timeline import build_program_timeline


def _atom_ids(molecule: dict[str, Any]) -> set[str]:
    return {str(atom.get("id") or "") for atom in molecule.get("atoms", []) if atom.get("id")}


def _molecules_by_id(frame: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(molecule.get("id") or ""): molecule for molecule in frame.get("molecules", []) if molecule.get("id")}


def build_fragment_flow_graph(puzzle: dict[str, Any], solution: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct replay-observed molecule flow between functional fragments.

    Atom ids are treated as lineage markers. This makes lineage robust to
    molecule merges at bonders and splits at unbonders because the atoms retain
    identity even when the containing replay molecule id changes.
    """
    fragments = extract_solution_fragments(solution)
    annotated = {item["anchorPartId"]: item for item in trace_fragment_evidence(puzzle, solution)}
    by_anchor = {item["anchorPartId"]: item for item in fragments}

    timeline = build_program_timeline(solution)
    trace = build_replay_trace(puzzle, solution, timeline)
    frames = list(trace.get("frames", []))

    atom_owner: dict[str, str] = {}
    edge_counts: Counter[tuple[str, str, str]] = Counter()
    edge_cycles: defaultdict[tuple[str, str, str], list[int]] = defaultdict(list)

    # Initial input molecules establish the first functional owner.
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

        # Input respawn can introduce new atoms after the functional events.
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

                # For a merge, the current molecule contains atoms from both
                # predecessor molecules, so collect all atom ids in that merged
                # molecule rather than relying on obsolete molecule ids.
                if event.get("effect") == "bond-created" and event.get("moleculeId"):
                    molecule = current_molecules.get(str(event["moleculeId"]))
                    if molecule:
                        affected_atoms.update(_atom_ids(molecule))

            elif kind in {"product-delivered", "molecule-consumed"}:
                anchor = str(event.get("consumerPartId") or "")
                relation = "delivered" if kind == "product-delivered" else "consumed"
                molecule_id = str(event.get("moleculeId") or "")
                # Consumers remove molecules before the frame snapshot, so use
                # the previous frame as the authoritative atom set.
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

            # A functional transformation/consumer becomes the latest known
            # owner of the atom lineage. Consumer ownership is kept so complete
            # source->sink paths remain queryable.
            for atom_id in affected_atoms:
                atom_owner[atom_id] = anchor

    nodes = []
    for fragment in fragments:
        anchor = str(fragment["anchorPartId"])
        evidence = annotated.get(anchor, {}).get("evidence", {})
        nodes.append({
            "anchorPartId": anchor,
            "anchorPartType": fragment.get("anchorPartType"),
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
        edges.append({
            "sourceAnchorPartId": source,
            "targetAnchorPartId": target,
            "sourceRole": source_fragment.get("role"),
            "targetRole": target_fragment.get("role"),
            "sourceMechanismHash": source_fragment.get("canonicalMechanismHash"),
            "targetMechanismHash": target_fragment.get("canonicalMechanismHash"),
            "relation": relation,
            "observationCount": count,
            "firstCycle": min(cycles),
            "lastCycle": max(cycles),
        })

    return {
        "schemaVersion": "0.1.0",
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
            "Arm motion is treated as transport inside/between functional fragments, not as a graph node.",
            "Collision correctness still requires external validation.",
        ],
    }
