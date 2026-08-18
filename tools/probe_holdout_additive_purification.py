from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.additive_purification_search import search_additive_purification_stations


def compact_validation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(value.get("complete")),
        "failureMode": value.get("failureMode"),
        "completedCycles": int(value.get("completedCycles") or 0),
        "terminatedWithError": bool(value.get("terminatedWithError")),
        "firstError": value.get("firstError"),
        "totalDelivered": int(value.get("totalDelivered") or 0),
        "totalDeficit": int(value.get("totalDeficit") or 0),
        "observedRequiredChemistryEventKinds": list(value.get("observedRequiredChemistryEventKinds") or []),
        "eventCounts": dict(value.get("eventCounts") or {}),
    }


def compact_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "element": item.get("element"),
        "producedElement": item.get("producedElement"),
        "origin": item.get("origin"),
        "rotation": item.get("rotation"),
        "second": item.get("second"),
        "output": item.get("output"),
        "firstCycle": item.get("firstCycle"),
        "lastCycle": item.get("lastCycle"),
        "observationCount": item.get("observationCount"),
        "readyObservationCount": item.get("readyObservationCount"),
        "minimumBlockerCount": item.get("minimumBlockerCount"),
        "blockersAtBestObservation": item.get("blockersAtBestObservation"),
        "unbondCandidates": item.get("unbondCandidates") or [],
    }


def probe(
    puzzle_path: Path,
    baseline_solution_path: Path,
    *,
    max_cycles: int = 400,
    opportunity_limit: int = 160,
    result_limit: int = 20,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)
    result = search_additive_purification_stations(
        puzzle,
        solution,
        max_cycles=max_cycles,
        opportunity_limit=opportunity_limit,
        result_limit=result_limit,
    )
    variants = result.get("variants") or []
    best = variants[0] if variants else None
    output_solution = None
    if best is not None and solution_output is not None and best.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best["solution"], solution_output)
        output_solution = str(solution_output)
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-additive-purification-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": max_cycles,
            "opportunityLimit": opportunity_limit,
            "resultLimit": result_limit,
        },
        "summary": result.get("summary"),
        "baselinePurificationProfile": result.get("baselinePurificationProfile"),
        "opportunities": [compact_opportunity(item) for item in (result.get("opportunities") or [])[:80]],
        "variants": [
            {
                "repairMode": item.get("repairMode"),
                "addedUnbonderCount": item.get("addedUnbonderCount"),
                "purificationDelta": item.get("purificationDelta"),
                "purificationProfile": item.get("purificationProfile"),
                "opportunity": compact_opportunity(item.get("opportunity") or {}),
                "validation": compact_validation(item.get("validation") or {}),
            }
            for item in variants
        ],
        "bestSolutionOutput": output_solution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Add new blind purification stations without moving earlier chemistry.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-cycles", type=int, default=400)
    parser.add_argument("--opportunity-limit", type=int, default=160)
    parser.add_argument("--result-limit", type=int, default=20)
    args = parser.parse_args()
    report = probe(
        args.puzzle,
        args.baseline_solution,
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
