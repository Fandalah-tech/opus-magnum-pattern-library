from __future__ import annotations

from collections import defaultdict
from typing import Any

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
INPUT_TYPES = {"input"}
OUTPUT_TYPES = {"out-std", "out-rep"}
TRACK_TYPE = "track"
TRACK_INSTRUCTIONS = {"track_plus", "track_minus"}


def _hex_distance(a: list[int] | tuple[int, int], b: list[int] | tuple[int, int]) -> int:
    dq = int(a[0]) - int(b[0])
    dr = int(a[1]) - int(b[1])
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
    if part["type"] == TRACK_TYPE:
        offsets = list(part.get("trackHexes", []))
        if offsets:
            # Track coordinates are serialized as offsets from an anchor. The
            # anchor itself is not an implicit rail cell unless [0, 0] appears
            # explicitly in the offset list.
            return {
                (int(x) + int(dx), int(y) + int(dy))
                for dx, dy in offsets
            }
    return {(int(x), int(y))}


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


def _uses_track_motion(part: dict[str, Any]) -> bool:
    return any(str(item.get("instruction") or "") in TRACK_INSTRUCTIONS for item in part.get("program", []))


def _mobile_arm_bases(
    arm: dict[str, Any],
    tracks: list[dict[str, Any]],
    footprints: dict[str, set[tuple[int, int]]],
) -> tuple[set[tuple[int, int]], list[str]]:
    """Return track cells an arm can occupy when its tape actually moves on track."""
    if str(arm.get("type") or "") not in ARM_TYPES or not _uses_track_motion(arm):
        return set(), []
    origin = tuple(int(value) for value in (arm.get("position") or (0, 0)))
    bases: set[tuple[int, int]] = set()
    track_ids: list[str] = []
    for track in tracks:
        track_id = str(track.get("id") or "")
        cells = footprints.get(track_id, set())
        if origin not in cells:
            continue
        bases.update(cells)
        track_ids.append(track_id)
    return bases, sorted(track_ids)


def build_solution_graph(solution: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic structural graph from a parsed solution.

    Edges are structural candidates rather than runtime transfer proofs. Track-
    mounted arms are nevertheless given their full reachable base envelope when
    their program contains track motion; this prevents feed/process fragments
    from losing the transport arm merely because its reset position is far from
    a glyph it serves later on the track.
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

    tracks = [part for part in parts if str(part.get("type") or "") == TRACK_TYPE]
    mobile_bases: dict[str, set[tuple[int, int]]] = {}
    mobile_tracks: dict[str, list[str]] = {}
    for part in parts:
        if str(part.get("type") or "") not in ARM_TYPES:
            continue
        bases, track_ids = _mobile_arm_bases(part, tracks, footprints)
        if bases:
            mobile_bases[str(part["id"])] = bases
            mobile_tracks[str(part["id"])] = track_ids

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

    def add_arm_reach(arm: dict[str, Any], target: dict[str, Any]) -> None:
        arm_id = str(arm["id"])
        target_id = str(target["id"])
        reach = _arm_reach(arm)
        distance = _hex_distance(arm["position"], target["position"])
        if distance <= reach:
            add_edge(arm_id, target_id, "within-arm-reach", "medium", {"distance": distance, "reach": reach})
            return

        bases = mobile_bases.get(arm_id)
        if not bases:
            return
        target_position = tuple(int(value) for value in (target.get("position") or (0, 0)))
        min_distance = min(_hex_distance(base, target_position) for base in bases)
        if min_distance <= reach:
            add_edge(
                arm_id,
                target_id,
                "within-track-arm-reach",
                "medium",
                {
                    "minDistance": min_distance,
                    "resetDistance": distance,
                    "reach": reach,
                    "trackIds": mobile_tracks.get(arm_id, []),
                    "mobileBaseCount": len(bases),
                },
            )

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
                add_arm_reach(left, right)
            if right_kind == "arm":
                add_arm_reach(right, left)

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
        "trackMobileArmCount": len(mobile_bases),
        "inputCount": sum(node["kind"] == "input" for node in nodes),
        "outputCount": sum(node["kind"] == "output" for node in nodes),
        "componentCount": len(components),
    }

    return {
        "schemaVersion": "0.2.1",
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
            "Track-mobile reach uses the full connected serialized track footprint, not a cycle-specific arm base.",
            "Track part anchors are coordinate origins only; only serialized trackHexes are rail cells when present.",
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
