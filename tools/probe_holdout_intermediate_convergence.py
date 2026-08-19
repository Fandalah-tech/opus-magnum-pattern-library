from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.intermediate_convergence import search_intermediate_convergence


def _compact_validation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(value.get("complete")),
        "failureMode": value.get("failureMode"),
        "totalDelivered": int(value.get("totalDelivered") or 0),
        "totalDeficit": int(value.get("totalDeficit") or 0),
        "completedCycles": int(value.get("completedCycles") or 0),
        "terminatedWithError": bool(value.get("terminatedWithError")),
        "firstError": value.get("firstError"),
        "eventCounts": dict(value.get("eventCounts") or {}),
    }


def probe(
    puzzle_path: Path,
    baseline_solution_path: Path,
    *,
    element: str | None = None,
    max_cycles: int = 500,
    observation_limit: int = 80,
    result_limit: int = 20,
    solution_output: Path | None = None,
    candidate_dir: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_intermediate_convergence(
        puzzle,
        solution,
        element=element,
        max_cycles=max_cycles,
        observation_limit=observation_limit,
        result_limit=result_limit,
    )
    variants = []
    raw_variants = list(result.get("variants") or [])
    best_raw = (raw_variants or [None])[0]
    if candidate_dir is not None:
        candidate_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(raw_variants):
        candidate_output = None
        if candidate_dir is not None and item.get("solution"):
            path = candidate_dir / f"convergence-{index:02d}.solution"
            write_solution(item["solution"], path)
            candidate_output = str(path)
        variants.append({
            "observation": item.get("observation"),
            "movingAtomId": item.get("movingAtomId"),
            "move": item.get("move"),
            "purifierPose": item.get("purifierPose"),
            "grabDelay": item.get("grabDelay"),
            "purificationProfile": item.get("purificationProfile"),
            "validation": _compact_validation(item.get("validation") or {}),
            "solutionOutput": candidate_output,
        })

    output_solution = None
    if best_raw is not None and solution_output is not None and best_raw.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_raw["solution"], solution_output)
        output_solution = str(solution_output)

    return {
        "schemaVersion": "0.2.0",
        "kind": "strict-heldout-intermediate-convergence-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {
            "element": element,
            "maxCycles": max_cycles,
            "observationLimit": observation_limit,
            "resultLimit": result_limit,
        },
        "summary": result.get("summary"),
        "baselinePurificationProfile": result.get("baselinePurificationProfile"),
        "observations": list(result.get("observations") or [])[:40],
        "variants": variants,
        "candidateOutputs": [item["solutionOutput"] for item in variants if item.get("solutionOutput")],
        "bestSolutionOutput": output_solution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Converge two blind trace-produced intermediates into the next purification.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--element")
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--observation-limit", type=int, default=80)
    parser.add_argument("--result-limit", type=int, default=20)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.baseline_solution,
        element=args.element,
        max_cycles=args.max_cycles,
        observation_limit=args.observation_limit,
        result_limit=args.result_limit,
        solution_output=args.solution_output,
        candidate_dir=args.candidate_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "summary": report["summary"],
        "candidateOutputCount": len(report["candidateOutputs"]),
        "bestSolutionOutput": report["bestSolutionOutput"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
