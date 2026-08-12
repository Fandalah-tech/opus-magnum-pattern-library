from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


def _preferred_timing(edge: dict[str, Any]) -> dict[str, Any] | None:
    timings = edge.get("relativeTimings") or {}
    preferred = timings.get("preferred") if isinstance(timings, dict) else None
    if preferred:
        return preferred
    return edge.get("relativeTiming")


def _motif_input_timing(convergence: dict[str, Any], input_item: dict[str, Any], occurrence: int) -> dict[str, Any] | None:
    role = str(input_item.get("sourceRole") or "")
    mechanism = str(input_item.get("sourceMechanismHash") or "")
    for sample in convergence.get("samples", []):
        matches = [
            item for item in sample.get("inputs", [])
            if str(item.get("sourceRole") or "") == role and str(item.get("sourceMechanismHash") or "") == mechanism
        ]
        if occurrence < len(matches):
            timings = matches[occurrence].get("relativeTimings", [])
            if timings:
                return timings[0]
    return None


def materialize_assembly_schedule(candidate: dict[str, Any]) -> dict[str, Any]:
    convergence = candidate.get("convergence") or {}
    starts: dict[str, int] = {"convergence": 0}
    missing = []
    defaulted = []

    motif_inputs = list(convergence.get("inputs", []))
    occurrence_counter: defaultdict[tuple[str, str], int] = defaultdict(int)
    for branch_index, branch in enumerate(candidate.get("branches", [])):
        input_item = motif_inputs[branch_index] if branch_index < len(motif_inputs) else {}
        key = (str(input_item.get("sourceRole") or ""), str(input_item.get("sourceMechanismHash") or ""))
        occurrence = occurrence_counter[key]
        occurrence_counter[key] += 1
        timing = _motif_input_timing(convergence, input_item, occurrence)
        if not timing:
            missing.append({"branch": branch_index, "stage": "convergence-input"})
            continue
        delta = timing.get("programStartDelta")
        if delta is None:
            delta = 0
            defaulted.append({"branch": branch_index, "stage": "convergence-input", "reason": "passive-fragment-has-no-program-start"})
        current = -int(delta)
        starts[f"branch-{branch_index}:input"] = current

        for reverse_index, edge in enumerate(reversed(branch)):
            timing = _preferred_timing(edge)
            if not timing:
                missing.append({"branch": branch_index, "stage": "branch-edge", "edge": edge})
                break
            delta = timing.get("programStartDelta")
            if delta is None:
                delta = 0
                defaulted.append({"branch": branch_index, "stage": "branch-edge", "edgeIndex": reverse_index, "reason": "passive-fragment-has-no-program-start"})
            current -= int(delta)
            starts[f"branch-{branch_index}:upstream-{reverse_index}"] = current

    current = 0
    for tail_index, edge in enumerate(candidate.get("tail", [])):
        timing = _preferred_timing(edge)
        if not timing:
            missing.append({"tail": tail_index, "stage": "tail-edge", "edge": edge})
            break
        delta = timing.get("programStartDelta")
        if delta is None:
            delta = 0
            defaulted.append({"tail": tail_index, "stage": "tail-edge", "reason": "passive-fragment-has-no-program-start"})
        current += int(delta)
        starts[f"tail-{tail_index}"] = current

    global_shift = -min(starts.values()) if starts and min(starts.values()) < 0 else 0
    shifted = {key: value + global_shift for key, value in starts.items()}
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "instanceCount": len(shifted),
            "missingTimingCount": len(missing),
            "defaultedTimingCount": len(defaulted),
            "globalShift": global_shift,
            "scheduleComplete": not missing,
        },
        "instanceStartCycles": shifted,
        "missingTimings": missing,
        "defaultedTimings": defaulted,
    }


def materialize_fragment_chain_schedule(candidate: dict[str, Any]) -> dict[str, Any]:
    starts: dict[str, int] = {"chain-0": 0}
    missing = []
    defaulted = []
    current = 0
    for step_index, edge in enumerate(candidate.get("steps", [])):
        timing = _preferred_timing(edge)
        if not timing:
            missing.append({"step": step_index, "stage": "chain-edge", "edge": edge})
            break
        delta = timing.get("programStartDelta")
        if delta is None:
            # Passive fragments have no local program start. Their placement is
            # still fully observed, while a zero offset provides a deterministic
            # baseline for bounded timing repair of neighbouring active parts.
            delta = 0
            defaulted.append({"step": step_index, "reason": "passive-fragment-has-no-program-start"})
        current += int(delta)
        starts[f"chain-{step_index + 1}"] = current

    global_shift = -min(starts.values()) if starts and min(starts.values()) < 0 else 0
    shifted = {key: value + global_shift for key, value in starts.items()}
    expected = len(candidate.get("nodes", []))
    return {
        "schemaVersion": "0.1.0",
        "candidateKind": "linear-chain",
        "summary": {
            "instanceCount": len(shifted),
            "missingTimingCount": len(missing),
            "defaultedTimingCount": len(defaulted),
            "globalShift": global_shift,
            "scheduleComplete": not missing and len(shifted) == expected,
        },
        "instanceStartCycles": shifted,
        "missingTimings": missing,
        "defaultedTimings": defaulted,
    }


def materialize_candidate_schedule(candidate: dict[str, Any]) -> dict[str, Any]:
    if candidate.get("candidateKind") == "linear-chain" or (candidate.get("nodes") and candidate.get("steps")):
        return materialize_fragment_chain_schedule(candidate)
    return materialize_assembly_schedule(candidate)


def synchronize_layout_programs(layout: dict[str, Any], schedule: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(layout)
    starts = {str(key): int(value) for key, value in schedule.get("instanceStartCycles", {}).items()}
    program_conflicts = []

    for part in result.get("parts", []):
        contributions = part.get("programContributions") or {}
        merged: dict[int, str] = {}
        provenance: defaultdict[int, list[str]] = defaultdict(list)
        for instance_id, program in contributions.items():
            if instance_id not in starts:
                continue
            offset = starts[instance_id]
            for instruction in program:
                cycle = int(instruction.get("cycle") or 0) + offset
                action = str(instruction.get("instruction") or "")
                if cycle in merged and merged[cycle] != action:
                    program_conflicts.append({
                        "partId": part.get("id"),
                        "cycle": cycle,
                        "existingInstruction": merged[cycle],
                        "newInstruction": action,
                        "instances": provenance[cycle] + [instance_id],
                    })
                else:
                    merged[cycle] = action
                    provenance[cycle].append(instance_id)
        part["program"] = [{"cycle": cycle, "instruction": merged[cycle]} for cycle in sorted(merged)]

    result["programSchedule"] = schedule
    result["programConflicts"] = program_conflicts
    result.setdefault("summary", {})["programConflictCount"] = len(program_conflicts)
    result["summary"]["scheduleComplete"] = bool(schedule.get("summary", {}).get("scheduleComplete")) and not program_conflicts
    return result
