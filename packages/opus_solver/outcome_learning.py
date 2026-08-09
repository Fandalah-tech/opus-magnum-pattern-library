from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any, Iterable

from packages.opus_analysis import puzzle_feature_fingerprint


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validation_progress(validation: dict[str, Any] | None) -> dict[str, Any]:
    validation = validation or {}
    return {
        "complete": bool(validation.get("complete")),
        "failureMode": validation.get("failureMode"),
        "totalDelivered": int(validation.get("totalDelivered") or 0),
        "totalDeficit": int(validation.get("totalDeficit") or 0),
        "completedCycles": int(validation.get("completedCycles") or 0),
        "terminatedWithError": bool(validation.get("terminatedWithError")),
        "blockedInputCount": len(validation.get("blockedInputsAtStart") or []),
        "firstError": validation.get("firstError"),
    }


def _progress_rank(progress: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        int(bool(progress.get("complete"))),
        int(not bool(progress.get("terminatedWithError"))),
        int(progress.get("totalDelivered") or 0),
        -int(progress.get("totalDeficit") or 0),
        int(progress.get("completedCycles") or 0),
    )


def _best_search_progress(search: dict[str, Any] | None) -> dict[str, Any] | None:
    search = search or {}
    best = None
    for variant in search.get("variants", []):
        validation = variant.get("validation") or {}
        progress = _validation_progress(validation)
        candidate = {
            **progress,
            "variantIndex": variant.get("variantIndex"),
            "displacement": int(variant.get("displacement") or 0),
        }
        if best is None or _progress_rank(candidate) > _progress_rank(best):
            best = candidate
    return best


def _assembly_signature(assembly: dict[str, Any]) -> dict[str, Any]:
    convergence = assembly.get("convergence") or {}
    branches = []
    for branch in assembly.get("branches", []):
        branches.append([
            {
                "sourceRole": edge.get("sourceRole"),
                "sourceMechanismHash": edge.get("sourceMechanismHash"),
                "targetRole": edge.get("targetRole"),
                "targetMechanismHash": edge.get("targetMechanismHash"),
                "relation": edge.get("relation"),
            }
            for edge in branch
        ])
    tail = [
        {
            "sourceRole": edge.get("sourceRole"),
            "sourceMechanismHash": edge.get("sourceMechanismHash"),
            "targetRole": edge.get("targetRole"),
            "targetMechanismHash": edge.get("targetMechanismHash"),
            "relation": edge.get("relation"),
        }
        for edge in assembly.get("tail", [])
    ]
    return {
        "convergence": {
            "targetRole": convergence.get("targetRole"),
            "targetMechanismHash": convergence.get("targetMechanismHash"),
            "inputs": [
                {
                    "sourceRole": item.get("sourceRole"),
                    "sourceMechanismHash": item.get("sourceMechanismHash"),
                    "relations": list(item.get("relations", [])),
                }
                for item in convergence.get("inputs", [])
            ],
        },
        "branches": branches,
        "tail": tail,
    }


def generation_outcome_records(puzzle: dict[str, Any], generation: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a verbose generation report into compact learning records.

    No solution geometry/program payload is retained. Records capture the target
    problem fingerprint, assembly identity, initial diagnosis, repair route and
    best observed progress for each bounded repair dimension.
    """
    puzzle_fingerprint = puzzle_feature_fingerprint(puzzle)
    puzzle_name = str(puzzle.get("name") or (puzzle.get("source") or {}).get("name") or "<unknown>")
    plan = generation.get("plan") or {}
    records = []

    for candidate in generation.get("candidates", []):
        assembly = candidate.get("assembly") or {}
        assembly_signature = _assembly_signature(assembly)
        base = _validation_progress(candidate.get("engineValidation"))
        temporal = _best_search_progress(candidate.get("temporalSearch"))
        geometry = _best_search_progress(candidate.get("geometricSearch"))
        attempts = []
        for repair, search in (("timing", candidate.get("temporalSearch")), ("geometry", candidate.get("geometricSearch"))):
            if not search:
                continue
            summary = search.get("summary", {})
            attempts.append({
                "repair": repair,
                "searchedVariantCount": int(summary.get("searchedVariantCount") or 0),
                "completeVariantCount": int(summary.get("completeVariantCount") or 0),
                "succeeded": bool(summary.get("hasCompleteSolution")),
            })

        progress_candidates = [("base", base)]
        if temporal is not None:
            progress_candidates.append(("timing", temporal))
        if geometry is not None:
            progress_candidates.append(("geometry", geometry))
        best_source, best_progress = max(progress_candidates, key=lambda item: _progress_rank(item[1]))

        identity_payload = {
            "puzzleFingerprint": puzzle_fingerprint,
            "assembly": assembly_signature,
            "candidateRank": candidate.get("rank"),
            "baseFailureMode": base.get("failureMode"),
            "route": (candidate.get("repairPolicy") or {}).get("order", []),
        }
        records.append({
            "id": f"out-{_stable_hash(identity_payload)[:20]}",
            "schemaVersion": "0.1.0",
            "puzzleFingerprint": puzzle_fingerprint,
            "puzzleName": puzzle_name,
            "manufacturingStrategy": plan.get("strategy"),
            "candidateRank": candidate.get("rank"),
            "assemblyScore": candidate.get("assemblyScore"),
            "assemblyHash": _stable_hash(assembly_signature),
            "assembly": assembly_signature,
            "layoutSignals": {
                "exactStaticConflictCount": int((candidate.get("layoutSummary") or {}).get("exactStaticConflictCount") or 0),
                "approximateStaticConflictCount": int((candidate.get("layoutSummary") or {}).get("approximateStaticConflictCount") or 0),
                "armWorkspaceOverlapCount": int((candidate.get("layoutSummary") or {}).get("armWorkspaceOverlapCount") or 0),
            },
            "baseProgress": base,
            "repairPolicy": candidate.get("repairPolicy"),
            "repairSucceededWith": candidate.get("repairSucceededWith"),
            "attempts": attempts,
            "bestProgressSource": best_source,
            "bestProgress": best_progress,
            "solved": bool(best_progress.get("complete")),
        })
    return records


def merge_outcome_records(existing: Iterable[dict[str, Any]], incoming: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge records by stable id, preferring the observation with best progress."""
    merged: dict[str, dict[str, Any]] = {}
    for record in [*existing, *incoming]:
        record_id = str(record.get("id") or f"out-{_stable_hash(record)[:20]}")
        previous = merged.get(record_id)
        if previous is None or _progress_rank(record.get("bestProgress") or {}) > _progress_rank(previous.get("bestProgress") or {}):
            merged[record_id] = record
    return [merged[key] for key in sorted(merged)]


def aggregate_repair_outcomes(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate repair success priors by initial failure mode and first route."""
    records = list(records)
    groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        failure = str((record.get("baseProgress") or {}).get("failureMode") or "<none>")
        order = list((record.get("repairPolicy") or {}).get("order", []))
        first = str(order[0]) if order else "none"
        groups[(failure, first)].append(record)

    priors = []
    for (failure, first), items in sorted(groups.items()):
        solved = sum(bool(item.get("solved")) for item in items)
        first_success = sum(str(item.get("repairSucceededWith") or "") == first for item in items)
        attempts: Counter[str] = Counter()
        successes: Counter[str] = Counter()
        for item in items:
            for attempt in item.get("attempts", []):
                repair = str(attempt.get("repair") or "unknown")
                attempts[repair] += 1
                successes[repair] += int(bool(attempt.get("succeeded")))
        priors.append({
            "failureMode": failure,
            "firstRepair": first,
            "observationCount": len(items),
            "solvedCount": solved,
            "solveRate": round(solved / len(items), 6) if items else 0.0,
            "firstRepairSuccessCount": first_success,
            "firstRepairSuccessRate": round(first_success / len(items), 6) if items else 0.0,
            "repairAttempts": dict(sorted(attempts.items())),
            "repairSuccesses": dict(sorted(successes.items())),
        })

    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "outcomeCount": len(records),
            "solvedOutcomeCount": sum(bool(item.get("solved")) for item in records),
            "priorGroupCount": len(priors),
        },
        "priors": priors,
    }
