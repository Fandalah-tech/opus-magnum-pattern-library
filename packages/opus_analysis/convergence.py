from __future__ import annotations

from collections import defaultdict
from typing import Any


def extract_convergence_motifs(flow_graph: dict[str, Any], *, minimum_inputs: int = 2) -> list[dict[str, Any]]:
    """Extract same-solution multi-predecessor convergence motifs."""
    minimum_inputs = max(2, int(minimum_inputs))
    nodes = {str(node.get("anchorPartId") or ""): node for node in flow_graph.get("nodes", [])}
    incoming: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in flow_graph.get("edges", []):
        source = str(edge.get("sourceAnchorPartId") or "")
        target = str(edge.get("targetAnchorPartId") or "")
        if source and target:
            incoming[target].append(edge)
            outgoing[source].append(edge)

    motifs = []
    for target_id, edges in sorted(incoming.items()):
        predecessors = sorted({str(edge.get("sourceAnchorPartId") or "") for edge in edges if edge.get("sourceAnchorPartId")})
        if len(predecessors) < minimum_inputs:
            continue
        target = nodes.get(target_id, {})
        target_role = str(target.get("role") or "")
        if target_role not in {"bonding", "conversion", "process", "conduit"}:
            continue

        input_records = []
        for predecessor_id in predecessors:
            source = nodes.get(predecessor_id, {})
            matching = [edge for edge in edges if str(edge.get("sourceAnchorPartId") or "") == predecessor_id]
            input_records.append({
                "sourceAnchorPartId": predecessor_id,
                "sourceRole": source.get("role"),
                "sourceMechanismHash": source.get("canonicalMechanismHash"),
                "relations": sorted({str(edge.get("relation") or "") for edge in matching if edge.get("relation")}),
                "relativeTransforms": [edge.get("relativeTransform") for edge in matching if edge.get("relativeTransform")],
                "relativeTimings": [edge.get("relativeTiming") for edge in matching if edge.get("relativeTiming")],
                "observationCount": sum(int(edge.get("observationCount") or 0) for edge in matching),
                "firstCycle": min((int(edge.get("firstCycle") or 0) for edge in matching), default=None),
                "lastCycle": max((int(edge.get("lastCycle") or 0) for edge in matching), default=None),
            })

        outputs = []
        for edge in sorted(outgoing.get(target_id, []), key=lambda item: (str(item.get("targetRole") or ""), str(item.get("targetMechanismHash") or ""))):
            outputs.append({
                "targetAnchorPartId": edge.get("targetAnchorPartId"),
                "targetRole": edge.get("targetRole"),
                "targetMechanismHash": edge.get("targetMechanismHash"),
                "relation": edge.get("relation"),
                "relativeTransform": edge.get("relativeTransform"),
                "relativeTiming": edge.get("relativeTiming"),
                "observationCount": edge.get("observationCount"),
            })

        motifs.append({
            "targetAnchorPartId": target_id,
            "targetRole": target_role,
            "targetMechanismHash": target.get("canonicalMechanismHash"),
            "inputCount": len(input_records),
            "inputs": input_records,
            "outputs": outputs,
        })
    return motifs


def canonical_convergence_key(motif: dict[str, Any]) -> tuple[Any, ...]:
    inputs = sorted(
        (
            str(item.get("sourceRole") or ""),
            str(item.get("sourceMechanismHash") or ""),
            tuple(sorted(str(value) for value in item.get("relations", []) if value)),
        )
        for item in motif.get("inputs", [])
    )
    return (
        tuple(inputs),
        str(motif.get("targetRole") or ""),
        str(motif.get("targetMechanismHash") or ""),
    )
