from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.product_delivery import search_singleton_product_delivery


def _compact_validation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(value.get("complete")),
        "failureMode": value.get("failureMode"),
        "totalDelivered": int(value.get("totalDelivered") or 0),
        "totalDeficit": int(value.get("totalDeficit") or 0),
        "completedCycles": int(value.get("completedCycles") or 0),
        "terminatedWithError": bool(value.get("terminatedWithError")),
        "firstError": value.get("firstError"),
        "missingProductOutputIndices": list(value.get("missingProductOutputIndices") or []),
        "eventCounts": dict(value.get("eventCounts") or {}),
    }


def probe(
    puzzle_path: Path,
    baseline_solution_path: Path,
    *,
    max_cycles: int = 500,
    opportunity_limit: int = 60,
    result_limit: int = 20,
    solution_output: Path | None = None,
    candidate_dir: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_singleton_product_delivery(
        puzzle,
        solution,
        max_cycles=max_cycles,
        opportunity_limit=opportunity_limit,
        result_limit=result_limit,
    )

    variants = []
    best_raw = (result.get("variants") or [None])[0]
    candidate_outputs: list[str] = []
    if candidate_dir is not None:
        candidate_dir.mkdir(parents=True, exist_ok=True)

    for index, item in enumerate(result.get("variants") or []):
        candidate_output = None
        if candidate_dir is not None and item.get("solution"):
            path = candidate_dir / f"candidate-{index:02d}.solution"
            write_solution(item["solution"], path)
            candidate_output = str(path)
            candidate_outputs.append(candidate_output)
        variants.append({
            "candidateIndex": index,
            "candidateOutput": candidate_output,
            "opportunity": item.get("opportunity"),
            "grabDelay": item.get("grabDelay"),
            "baseRotation": item.get("baseRotation"),
            "motionInstruction": item.get("motionInstruction"),
            "summary": item.get("summary"),
            "validation": _compact_validation(item.get("validation") or {}),
        })

    output_solution = None
    if best_raw is not None and solution_output is not None and best_raw.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_raw["solution"], solution_output)
        output_solution = str(solution_output)

    return {
        "schemaVersion": "0.2.0",
        "kind": "strict-heldout-product-delivery-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": max_cycles,
            "opportunityLimit": opportunity_limit,
            "resultLimit": result_limit,
        },
        "summary": result.get("summary"),
        "baseline": result.get("baseline"),
        "opportunities": list(result.get("opportunities") or [])[:40],
        "variants": variants,
        "candidateOutputs": candidate_outputs,
        "bestSolutionOutput": output_solution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver a strict-blind trace-produced singleton product.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--opportunity-limit", type=int, default=60)
    parser.add_argument("--result-limit", type=int, default=20)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.baseline_solution,
        max_cycles=args.max_cycles,
        opportunity_limit=args.opportunity_limit,
        result_limit=args.result_limit,
        solution_output=args.solution_output,
        candidate_dir=args.candidate_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "summary": report["summary"],
        "candidateCount": len(report["candidateOutputs"]),
        "bestSolutionOutput": report["bestSolutionOutput"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
