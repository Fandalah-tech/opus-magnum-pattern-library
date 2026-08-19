from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.input_footprint_repair import search_input_footprint_rotations


def _compact_summary(value: dict[str, Any]) -> dict[str, Any]:
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
    max_cycles: int = 256,
    beam_width: int = 4,
    depth: int = 2,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_input_footprint_rotations(
        puzzle,
        solution,
        max_cycles=max_cycles,
        beam_width=beam_width,
        depth=depth,
    )
    best_raw = result.get("best") or {}
    output_solution = None
    if solution_output is not None and best_raw.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_raw["solution"], solution_output)
        output_solution = str(solution_output)
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-input-footprint-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": max_cycles,
            "beamWidth": beam_width,
            "depth": depth,
        },
        "summary": result.get("summary"),
        "anchors": result.get("anchors") or [],
        "baseline": _compact_summary(result.get("baseline") or {}),
        "generations": result.get("generations") or [],
        "best": {
            "summary": _compact_summary(best_raw.get("summary") or {}),
            "edits": best_raw.get("edits") or [],
            "solutionOutput": output_solution,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate target reagent footprints around inherited first-grab anchors.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-cycles", type=int, default=256)
    parser.add_argument("--beam-width", type=int, default=4)
    parser.add_argument("--depth", type=int, default=2)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.baseline_solution,
        max_cycles=args.max_cycles,
        beam_width=args.beam_width,
        depth=args.depth,
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
