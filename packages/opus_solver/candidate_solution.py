from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from typing import Any

from packages.opus_parser import parse_solution_bytes, write_solution_bytes

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
    """Assign target-puzzle atom flows to assembly branches by chemistry.

    For the current bonded-pair strategy, the calcifying branch is matched to
    the calcification AtomFlow and the remaining branch to the direct AtomFlow.
    The function is intentionally strict so historical input indices are never
    silently reused for the wrong target reagent.
    """
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


def _branch_index_for_part(part: dict[str, Any]) -> int | None:
    instances = list(part.get("sourceFragmentInstances", []))
    if part.get("sourceFragmentInstance"):
        instances.append(part.get("sourceFragmentInstance"))
    indexes = set()
    for instance in instances:
        value = str(instance or "")
        if not value.startswith("branch-"):
            continue
        prefix = value.split(":", 1)[0]
        try:
            indexes.add(int(prefix.split("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    if len(indexes) > 1:
        raise ValueError(f"Input part is shared across multiple source branches: {sorted(indexes)}")
    return next(iter(indexes)) if indexes else None


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

    branch_flows = assign_branch_atom_flows(candidate, plan) if plan.atom_flows else {}
    source_reagent_indices = sorted({
        int(operation.metadata["reagentIndex"])
        for operation in plan.operations
        if operation.kind == "source" and operation.metadata.get("reagentIndex") is not None
    })
    parts = []
    arm_number = 1
    for index, raw_part in enumerate(synchronized_layout.get("parts", [])):
        part = _clean_part(raw_part, part_id=f"part-{index}")
        part_type = part["type"]
        if part_type == "input":
            branch_index = _branch_index_for_part(raw_part) if branch_flows else None
            if branch_index is not None and branch_index in branch_flows:
                part["which"] = int(branch_flows[branch_index].reagent_index)
            elif len(source_reagent_indices) == 1:
                part["which"] = source_reagent_indices[0]
            else:
                raise ValueError(f"Could not resolve target reagent for input part {raw_part.get('id')}")
        elif part_type.startswith("out-"):
            part["which"] = int(plan.product_index)
        if part_type in ARM_TYPES:
            part["armNumber"] = arm_number
            arm_number += 1
        parts.append(part)

    return {
        "schemaVersion": "0.1.0",
        "format": {"kind": "solution", "version": 7},
        "source": {"name": None, "generator": "opus_solver/composed-assembly"},
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
