from __future__ import annotations

from collections import defaultdict
from typing import Any

from .canonical import canonical_solution_hash
from .graph import build_solution_graph

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
TRACK_TYPES = {"track"}
INPUT_TYPES = {"input"}
OUTPUT_TYPES = {"out-std", "out-rep"}
BOND_TYPES = {
    "bonder", "unbonder", "multibonder", "bonder-speed", "triplex-bonder",
    "glyph-bonder-prisma", "glyph-unbonder-prisma",
}
CONVERSION_TYPES = {
    "calcification", "glyph-calcification",
    "duplication", "glyph-duplication",
    "projection", "glyph-projection",
    "purification", "glyph-purification",
    "animismus", "glyph-life-and-death",
    "unification", "dispersion",
}
DISPOSAL_TYPES = {"disposal", "glyph-disposal"}
CONDUIT_TYPES = {"pipe"}


def functional_role(part_type: str) -> str | None:
    value = str(part_type or "")
    if value in INPUT_TYPES:
        return "feed"
    if value in OUTPUT_TYPES:
        return "output"
    if value in BOND_TYPES:
        return "bonding"
    if value in CONVERSION_TYPES:
        return "conversion"
    if value in DISPOSAL_TYPES:
        return "disposal"
    if value in CONDUIT_TYPES:
        return "conduit"
    if value in ARM_TYPES or value in TRACK_TYPES:
        return None
    return "process"


def _fragment_summary(parts: list[dict[str, Any]]) -> dict[str, Any]:
    instruction_count = sum(len(part.get("program", [])) for part in parts)
    cycles = [
        int(item.get("cycle") or 0)
        for part in parts
        for item in part.get("program", [])
    ]
    return {
        "partCount": len(parts),
        "armCount": sum(str(part.get("type")) in ARM_TYPES for part in parts),
        "trackCount": sum(str(part.get("type")) in TRACK_TYPES for part in parts),
        "instructionCount": instruction_count,
        "firstInstructionCycle": min(cycles) if cycles else None,
        "lastInstructionCycle": max(cycles) if cycles else None,
        "partTypes": sorted({str(part.get("type") or "") for part in parts}),
    }


def extract_solution_fragments(solution: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract local functional fragments around non-transfer anchor parts.

    A fragment contains one semantic anchor (input/output/glyph/pipe), arms that
    can structurally reach it, and tracks structurally reachable by those arms.
    This is deliberately a structural approximation; confirmed molecule-flow
    evidence is layered on top from cycle-accurate replay traces.
    """

    parts = list(solution.get("parts", []))
    parts_by_id = {str(part.get("id")): part for part in parts}
    graph = build_solution_graph(solution)

    incoming: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        incoming[str(edge["target"])].append(edge)
        outgoing[str(edge["source"])].append(edge)

    fragments = []
    seen: set[tuple[str, str]] = set()

    for anchor in parts:
        anchor_id = str(anchor.get("id"))
        role = functional_role(str(anchor.get("type") or ""))
        if role is None:
            continue

        member_ids = {anchor_id}
        arm_ids = set()

        for edge in incoming.get(anchor_id, []):
            if edge.get("relation") not in {"within-arm-reach", "shared-hex"}:
                continue
            source_id = str(edge["source"])
            source = parts_by_id.get(source_id)
            if source and str(source.get("type")) in ARM_TYPES:
                arm_ids.add(source_id)
                member_ids.add(source_id)

        for edge in outgoing.get(anchor_id, []):
            if edge.get("relation") != "shared-hex":
                continue
            target_id = str(edge["target"])
            target = parts_by_id.get(target_id)
            if target and str(target.get("type")) in ARM_TYPES:
                arm_ids.add(target_id)
                member_ids.add(target_id)

        for arm_id in arm_ids:
            for edge in outgoing.get(arm_id, []):
                if edge.get("relation") not in {"within-arm-reach", "shared-hex"}:
                    continue
                target_id = str(edge["target"])
                target = parts_by_id.get(target_id)
                if target and str(target.get("type")) in TRACK_TYPES:
                    member_ids.add(target_id)
            for edge in incoming.get(arm_id, []):
                if edge.get("relation") != "shared-hex":
                    continue
                source_id = str(edge["source"])
                source = parts_by_id.get(source_id)
                if source and str(source.get("type")) in TRACK_TYPES:
                    member_ids.add(source_id)

        selected = [part for part in parts if str(part.get("id")) in member_ids]
        subsolution = {"puzzleFile": "", "parts": selected}
        structural_hash = canonical_solution_hash(subsolution, normalize_time=False)
        mechanism_hash = canonical_solution_hash(subsolution, normalize_time=True)
        dedupe_key = (anchor_id, mechanism_hash)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        fragments.append({
            "role": role,
            "anchorPartId": anchor_id,
            "anchorPartType": str(anchor.get("type") or ""),
            "memberPartIds": sorted(member_ids),
            "canonicalStructuralHash": structural_hash,
            "canonicalMechanismHash": mechanism_hash,
            "summary": _fragment_summary(selected),
        })

    return sorted(
        fragments,
        key=lambda item: (
            item["role"],
            item["anchorPartType"],
            item["canonicalMechanismHash"],
            item["anchorPartId"],
        ),
    )
