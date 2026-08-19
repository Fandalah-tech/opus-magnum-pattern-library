from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.collision_cleanup_timing import search_phase_aware_cleanup_arms


def compact_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "completedCycles": int(value.get("completedCycles") or 0),
        "requestedCycles": int(value.get("requestedCycles") or 0),
        "terminatedWithError": bool(value.get("terminatedWithError")),
        "firstError": value.get("firstError"),
        "purificationCount": int(value.get("purificationCount") or 0),
        "productDeliveredCount": int(value.get("productDeliveredCount") or 0),
        "chemistryEventCount": int(value.get("chemistryEventCount") or 0),
        "manipulationEventCount": int(value.get("manipulationEventCount") or 0),
        "eventCounts": dict(value.get("eventCounts") or {}),
    }


def probe(
    puzzle_path: Path,
    baseline_solution_path: Path,
    *,
    max_cycles: int = 400,
    result_limit: int = 16,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_phase_aware_cleanup_arms(
        puzzle,
        solution,
        max_cycles=max_cycles,
        result_limit=result_limit,
    )
    best_raw = result.get("best") or {}
    output_solution = None
    if solution_output is not None and best_raw.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_raw["solution"], solution_output)
        output_solution = str(solution_output)
    return {
        "schemaVersion": "0.2.0",
        "kind": "strict-heldout-phase-aware-collision-cleanup-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {"maxCycles": max_cycles, "resultLimit": result_limit},
        "summary": result.get("summary"),
        "collision": result.get("collision"),
        "collisionMolecule": result.get("collisionMolecule"),
        "baseline": compact_summary(result.get("baseline") or {}),
        "variants": [
            {
                "motionLead": item.get("motionLead"),
                "grabLead": item.get("grabLead"),
                "baseDirectionIndex": item.get("baseDirectionIndex"),
                "motionInstruction": item.get("motionInstruction"),
                "summary": compact_summary(item.get("summary") or {}),
            }
            for item in result.get("variants", []) or []
        ],
        "best": {
            "motionLead": best_raw.get("motionLead"),
            "grabLead": best_raw.get("grabLead"),
            "baseDirectionIndex": best_raw.get("baseDirectionIndex"),
            "motionInstruction": best_raw.get("motionInstruction"),
            "summary": compact_summary(best_raw.get("summary") or {}),
            "repairs": (best_raw.get("solution") or {}).get("source", {}).get("collisionCleanupRepairs", []),
            "solutionOutput": output_solution,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize and phase a cleanup arm from a strict-blind stationary collision trace.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-cycles", type=int, default=400)
    parser.add_argument("--result-limit", type=int, default=16)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.baseline_solution,
        max_cycles=args.max_cycles,
        result_limit=args.result_limit,
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "summary": report["summary"],
        "best": report["best"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
