from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.purification_chain import search_purification_chain


def _compact_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(validation.get("complete")),
        "failureMode": validation.get("failureMode"),
        "totalDelivered": int(validation.get("totalDelivered") or 0),
        "totalDeficit": int(validation.get("totalDeficit") or 0),
        "completedCycles": int(validation.get("completedCycles") or 0),
        "terminatedWithError": bool(validation.get("terminatedWithError")),
        "firstError": validation.get("firstError"),
        "missingProductOutputIndices": list(validation.get("missingProductOutputIndices") or []),
        "observedRequiredChemistryEventKinds": list(validation.get("observedRequiredChemistryEventKinds") or []),
        "distinctRequiredChemistryEventCount": int(validation.get("distinctRequiredChemistryEventCount") or 0),
        "requiredChemistryEventCount": int(validation.get("requiredChemistryEventCount") or 0),
        "chemistryEventCount": int(validation.get("chemistryEventCount") or 0),
        "eventCounts": dict(validation.get("eventCounts") or {}),
    }


def probe(
    puzzle_path: Path,
    baseline_solution_path: Path,
    *,
    max_cycles: int = 256,
    depth: int = 4,
    beam_width: int = 3,
    opportunity_limit: int = 60,
    variant_limit: int = 120,
    result_limit: int = 10,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_purification_chain(
        puzzle,
        solution,
        max_cycles=max_cycles,
        depth=depth,
        beam_width=beam_width,
        opportunity_limit=opportunity_limit,
        variant_limit=variant_limit,
        result_limit=result_limit,
    )

    best_raw = result.get("best") or {}
    output_solution = None
    if solution_output is not None and best_raw.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_raw["solution"], solution_output)
        output_solution = str(solution_output)

    best = {
        "purificationProfile": best_raw.get("purificationProfile"),
        "steps": best_raw.get("steps") or [],
        "validation": _compact_validation(best_raw.get("validation") or {}),
        "solutionOutput": output_solution,
    }
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-purification-chain-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": max_cycles,
            "depth": depth,
            "beamWidth": beam_width,
            "opportunityLimit": opportunity_limit,
            "variantLimit": variant_limit,
            "resultLimit": result_limit,
        },
        "summary": result.get("summary"),
        "initialPurificationProfile": result.get("initialPurificationProfile"),
        "generations": result.get("generations") or [],
        "best": best,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Iteratively extend a strict-blind purification chain from a generated candidate.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-cycles", type=int, default=256)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--beam-width", type=int, default=3)
    parser.add_argument("--opportunity-limit", type=int, default=60)
    parser.add_argument("--variant-limit", type=int, default=120)
    parser.add_argument("--result-limit", type=int, default=10)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.baseline_solution,
        max_cycles=args.max_cycles,
        depth=args.depth,
        beam_width=args.beam_width,
        opportunity_limit=args.opportunity_limit,
        variant_limit=args.variant_limit,
        result_limit=args.result_limit,
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "summary": report["summary"],
        "bestProfile": report["best"]["purificationProfile"],
        "stepCount": len(report["best"]["steps"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
