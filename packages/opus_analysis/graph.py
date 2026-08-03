from __future__ import annotations

from collections import defaultdict
from typing import Any

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
INPUT_TYPES = {"input"}
OUTPUT_TYPES = {"out-std", "out-rep"}
TRACK_TYPE = "track"


def _hex_distance(a: list[int], b: list[int]) -> int:
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return max(abs(dq), abs(dr), abs(dq + dr))


def _category(part_type: str) -> str:
    if part_type in ARM_TYPES:
        return "arm"
    if part_type in INPUT_TYPES:
        return "input"
    if part_type in OUTPUT_TYPES:
        return "output"
    if part_type == TRACK_TYPE:
        return "track"
    return "glyph"


def _footprint(part: dict[str, Any]) -> set[tuple[int, int]]:
    x, y = part["position"]
    cells = {(x, y)}
    if part["type"] == TRACK_TYPE:
        cells.update((x + dx, y + dy) for dx, dy in part.get("trackHexes", []))
    return cells


def _arm_reach(part: dict[str, Any]) -> int:
    if part["type"] == "piston":
        return max(1, int(part.get("length", 1))) + 2
    if part["type"] == "baron":
        return 3
    return max(1, int(part.get("length", 1)))


def _program_summary(part: dict[str, Any]) -> dict[str, Any]:
    program = part.get("program", [])
    cycles = sorted({int(item["cycle"]) for item in program})
    instructions = defaultdict(int)
    for item in program:
        instructions[item["instruction"]] += 1
    return {
        "instructionCount": len(program),
        "firstInstructionCycle": cycles[0] if cycles else None,
        "lastInstructionCycle": cycles[-1] if cycles else None,
        "instructionHistogram": dict(sorted(instructions.items())),
    }


def build_solution_graph(solution: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic structural graph from a parsed solution.

    Edges are intentionally classified as structural candidates. They do not
    assert runtime molecule transfer; dynamic dependencies require simulation.
    """
    parts = solution.get("parts", [])
    nodes = []
    footprints: dict[str, set[tuple[int, int]]] = {}

    for part in parts:
        node_id = part["id"]
        footprint = _footprint(part)
        footprints[node_id] = footprint
        nodes.append({
            "id": node_id,
            "kind": _category(part["type"]),
            "partType": part["type"],
            "position": part["position"],
            "rotation": part.get("rotation", 0),
            "length": part.get("length", 1),
            "armNumber": part.get("armNumber"),
            "footprint": [list(cell) for cell in sorted(footprint)],
            "program": _program_summary(part),
        })

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_edge(source: str, target: str, relation: str, confidence: str, evidence: dict[str, Any]) -> None:
        key = (source, target, relation)
        if key in seen:
            return
        seen.add(key)
        edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "confidence": confidence,
            "evidence": evidence,
        })

    for index, left in enumerate(parts):
        left_id = left["id"]
        left_kind = _category(left["type"])
        for right in parts[index + 1:]:
            right_id = right["id"]
            right_kind = _category(right["type"])
            overlap = footprints[left_id] & footprints[right_id]
            if overlap:
                add_edge(left_id, right_id, "shared-hex", "high", {"hexes": [list(cell) for cell in sorted(overlap)]})
                add_edge(right_id, left_id, "shared-hex", "high", {"hexes": [list(cell) for cell in sorted(overlap)]})

            if left_kind == "arm":
                distance = _hex_distance(left["position"], right["position"])
                reach = _arm_reach(left)
                if distance <= reach:
                    add_edge(left_id, right_id, "within-arm-reach", "medium", {"distance": distance, "reach": reach})
            if right_kind == "arm":
                distance = _hex_distance(right["position"], left["position"])
                reach = _arm_reach(right)
                if distance <= reach:
                    add_edge(right_id, left_id, "within-arm-reach", "medium", {"distance": distance, "reach": reach})

            if left_kind == "arm" and right_kind == "arm":
                distance = _hex_distance(left["position"], right["position"])
                combined = _arm_reach(left) + _arm_reach(right)
                if distance <= combined:
                    add_edge(left_id, right_id, "workspace-overlap", "low", {"distance": distance, "combinedReach": combined})
                    add_edge(right_id, left_id, "workspace-overlap", "low", {"distance": distance, "combinedReach": combined})

    degrees = defaultdict(lambda: {"in": 0, "out": 0})
    for edge in edges:
        degrees[edge["source"]]["out"] += 1
        degrees[edge["target"]]["in"] += 1

    components = _weak_components([node["id"] for node in nodes], edges)
    summary = {
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "armCount": sum(node["kind"] == "arm" for node in nodes),
        "glyphCount": sum(node["kind"] == "glyph" for node in nodes),
        "trackCount": sum(node["kind"] == "track" for node in nodes),
        "inputCount": sum(node["kind"] == "input" for node in nodes),
        "outputCount": sum(node["kind"] == "output" for node in nodes),
        "componentCount": len(components),
    }

    return {
        "schemaVersion": "0.1.0",
        "analysis": "structural-solution-graph",
        "source": {
            "solutionName": solution.get("name"),
            "puzzleFile": solution.get("puzzleFile"),
            "sha256": solution.get("source", {}).get("sha256"),
        },
        "summary": summary,
        "nodes": nodes,
        "edges": sorted(edges, key=lambda edge: (edge["source"], edge["target"], edge["relation"])),
        "degrees": dict(sorted(degrees.items())),
        "components": components,
        "limitations": [
            "Structural edges are candidates, not confirmed molecule transfers.",
            "Dynamic dependencies require cycle-accurate simulation traces.",
            "Arm reach is conservatively approximated from base position and length.",
        ],
    }


def _weak_components(node_ids: list[str], edges: list[dict[str, Any]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in edges:
        adjacency[edge["source"]].add(edge["target"])
        adjacency[edge["target"]].add(edge["source"])

    components: list[list[str]] = []
    unseen = set(node_ids)
    while unseen:
        start = min(unseen)
        stack = [start]
        component = []
        unseen.remove(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda component: (component[0], len(component)))
