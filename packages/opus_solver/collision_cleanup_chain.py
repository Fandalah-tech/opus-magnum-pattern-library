from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from .collision_cleanup import search_collision_cleanup_arms
from .input_footprint_repair import replay_summary


def _physical_signature(solution: dict[str, Any]) -> str:
    payload = [
        {
            "type": str(part.get("type") or ""),
            "position": list(part.get("position") or (0, 0)),
            "rotation": int(part.get("rotation") or 0) % 6,
            "length": int(part.get("length") or 1),
            "which": int(part.get("which") or 0),
            "program": [
                (int(item.get("cycle") or 0), str(item.get("instruction") or ""))
                for item in part.get("program", []) or []
            ],
        }
        for part in solution.get("parts", []) or []
    ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _rank(state: dict[str, Any]) -> tuple[Any, ...]:
    summary = state.get("summary") or {}
    return (
        int(summary.get("productDeliveredCount") or 0),
        int(summary.get("purificationCount") or 0),
        int(not bool(summary.get("terminatedWithError"))),
        int(summary.get("completedCycles") or 0),
        int(summary.get("chemistryEventCount") or 0),
        int(summary.get("manipulationEventCount") or 0),
        -len(state.get("steps", []) or []),
    )


def search_collision_cleanup_chain(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 400,
    depth: int = 4,
    beam_width: int = 2,
    variants_per_state: int = 8,
) -> dict[str, Any]:
    """Iteratively synthesize cleanup arms until the replay horizon survives.

    Every child must preserve the parent's purification count and strictly
    improve mechanical survival, unless it eliminates the error at the full
    requested horizon.  The chain remains entirely trace-derived.
    """

    horizon = max(1, int(max_cycles))
    baseline_full = replay_summary(puzzle, solution, max_cycles=horizon)
    baseline_full.pop("replay", None)
    beam = [{
        "solution": deepcopy(solution),
        "summary": baseline_full,
        "steps": [],
    }]
    generations: list[dict[str, Any]] = []

    for generation in range(max(0, int(depth))):
        children: list[dict[str, Any]] = []
        for parent_index, state in enumerate(beam):
            parent_summary = state.get("summary") or {}
            if not bool(parent_summary.get("terminatedWithError")) and int(parent_summary.get("completedCycles") or 0) >= horizon:
                children.append(state)
                continue
            search = search_collision_cleanup_arms(
                puzzle,
                state["solution"],
                max_cycles=horizon,
                result_limit=max(1, int(variants_per_state)),
            )
            for variant in search.get("variants", []) or []:
                summary = variant.get("summary") or {}
                if int(summary.get("purificationCount") or 0) < int(parent_summary.get("purificationCount") or 0):
                    continue
                parent_cycles = int(parent_summary.get("completedCycles") or 0)
                child_cycles = int(summary.get("completedCycles") or 0)
                child_complete_horizon = not bool(summary.get("terminatedWithError")) and child_cycles >= horizon
                if not child_complete_horizon and child_cycles <= parent_cycles:
                    continue
                repair = ((variant.get("solution") or {}).get("source") or {}).get("collisionCleanupRepairs", [])
                children.append({
                    "solution": variant["solution"],
                    "summary": summary,
                    "steps": [
                        *state.get("steps", []),
                        {
                            "generation": generation + 1,
                            "parentIndex": parent_index,
                            "collision": search.get("collision"),
                            "collisionMolecule": search.get("collisionMolecule"),
                            "grabLead": variant.get("grabLead"),
                            "baseDirectionIndex": variant.get("baseDirectionIndex"),
                            "motionInstruction": variant.get("motionInstruction"),
                            "repair": deepcopy(repair[-1] if repair else None),
                            "completedCycles": child_cycles,
                        },
                    ],
                })

        deduped: dict[str, dict[str, Any]] = {}
        for child in children:
            signature = _physical_signature(child["solution"])
            existing = deduped.get(signature)
            if existing is None or _rank(child) > _rank(existing):
                deduped[signature] = child
        ordered = sorted(deduped.values(), key=_rank, reverse=True)
        beam = ordered[:max(1, int(beam_width))]
        generations.append({
            "generation": generation + 1,
            "candidateCount": len(children),
            "dedupedCandidateCount": len(deduped),
            "beamCount": len(beam),
            "bestSummary": deepcopy(beam[0].get("summary") if beam else baseline_full),
            "bestStepCount": len(beam[0].get("steps", [])) if beam else 0,
        })
        if not beam:
            break
        best_summary = beam[0].get("summary") or {}
        if not bool(best_summary.get("terminatedWithError")) and int(best_summary.get("completedCycles") or 0) >= horizon:
            break

    ordered_final = sorted(beam, key=_rank, reverse=True) if beam else []
    best = ordered_final[0] if ordered_final else {
        "solution": deepcopy(solution),
        "summary": baseline_full,
        "steps": [],
    }
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-stationary-collision-cleanup-chain",
        "summary": {
            "maxCycles": horizon,
            "requestedDepth": max(0, int(depth)),
            "beamWidth": max(1, int(beam_width)),
            "generationCount": len(generations),
            "baselineCompletedCycles": int(baseline_full.get("completedCycles") or 0),
            "bestCompletedCycles": int((best.get("summary") or {}).get("completedCycles") or 0),
            "baselinePurificationCount": int(baseline_full.get("purificationCount") or 0),
            "bestPurificationCount": int((best.get("summary") or {}).get("purificationCount") or 0),
            "bestTerminatedWithError": bool((best.get("summary") or {}).get("terminatedWithError")),
            "stepCount": len(best.get("steps", [])),
            "targetSolutionBytesUsed": 0,
        },
        "baseline": baseline_full,
        "generations": generations,
        "best": best,
    }


__all__ = ["search_collision_cleanup_chain"]
