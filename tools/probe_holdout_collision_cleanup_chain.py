from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.collision_cleanup_chain import search_collision_cleanup_chain


def compact(value: dict[str, Any]) -> dict[str, Any]:
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
    depth: int = 4,
    beam_width: int = 2,
    variants_per_state: int = 8,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_collision_cleanup_chain(
        puzzle,
        solution,
        max_cycles=max_cycles,
        depth=depth,
        beam_width=beam_width,
        variants_per_state=variants_per_state,
    )
    best_raw = result.get("best") or {}
    output_solution = None
    if solution_output is not None and best_raw.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_raw["solution"], solution_output)
        output_solution = str(solution_output)
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-collision-cleanup-chain-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": max_cycles,
            "depth": depth,
            "beamWidth": beam_width,
            "variantsPerState": variants_per_state,
        },
        "summary": result.get("summary"),
        "baseline": compact(result.get("baseline") or {}),
        "generations": result.get("generations") or [],
        "best": {
            "summary": compact(best_raw.get("summary") or {}),
            "steps": best_raw.get("steps") or [],
            "solutionOutput": output_solution,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Iteratively synthesize cleanup arms from blind collision traces.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-cycles", type=int, default=400)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--beam-width", type=int, default=2)
    parser.add_argument("--variants-per-state", type=int, default=8)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.baseline_solution,
        max_cycles=args.max_cycles,
        depth=args.depth,
        beam_width=args.beam_width,
        variants_per_state=args.variants_per_state,
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"targetPuzzle": report["targetPuzzle"], "summary": report["summary"], "best": report["best"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
