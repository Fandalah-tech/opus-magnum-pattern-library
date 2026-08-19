from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.trace_output_placement import search_singleton_output_placement


def _compact_validation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(value.get("complete")),
        "failureMode": value.get("failureMode"),
        "totalDelivered": int(value.get("totalDelivered") or 0),
        "deliveredByProduct": dict(value.get("deliveredByProduct") or {}),
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
    product_index: int,
    max_cycles: int,
    opportunity_limit: int,
    result_limit: int,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_singleton_output_placement(
        puzzle,
        solution,
        product_index=product_index,
        max_cycles=max_cycles,
        opportunity_limit=opportunity_limit,
        result_limit=result_limit,
    )
    raw_variants = list(result.get("variants") or [])
    best = raw_variants[0] if raw_variants else None
    output_path = None
    if best is not None and solution_output is not None:
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best["solution"], solution_output)
        output_path = str(solution_output)
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-trace-singleton-output-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {
            "productIndex": int(product_index),
            "maxCycles": int(max_cycles),
            "opportunityLimit": int(opportunity_limit),
            "resultLimit": int(result_limit),
        },
        "summary": result.get("summary"),
        "opportunities": list(result.get("opportunities") or [])[:80],
        "variants": [
            {
                "opportunity": item.get("opportunity"),
                "delivered": item.get("delivered"),
                "validation": _compact_validation(item.get("validation") or {}),
            }
            for item in raw_variants
        ],
        "bestSolutionOutput": output_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Place a singleton product output from a generated blind trace.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--product-index", type=int, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--opportunity-limit", type=int, default=120)
    parser.add_argument("--result-limit", type=int, default=20)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = probe(
        args.puzzle,
        args.baseline_solution,
        product_index=args.product_index,
        max_cycles=args.max_cycles,
        opportunity_limit=args.opportunity_limit,
        result_limit=args.result_limit,
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"targetPuzzle": report["targetPuzzle"], "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
