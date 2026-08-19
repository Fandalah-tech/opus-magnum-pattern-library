from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.reaction_placement import search_purification_placements


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
        "requiredChemistryEventKinds": list(validation.get("requiredChemistryEventKinds") or []),
        "observedRequiredChemistryEventKinds": list(validation.get("observedRequiredChemistryEventKinds") or []),
        "distinctRequiredChemistryEventCount": int(validation.get("distinctRequiredChemistryEventCount") or 0),
        "requiredChemistryEventCount": int(validation.get("requiredChemistryEventCount") or 0),
        "distinctChemistryEventCount": int(validation.get("distinctChemistryEventCount") or 0),
        "chemistryEventCount": int(validation.get("chemistryEventCount") or 0),
        "chemistryEventKinds": list(validation.get("chemistryEventKinds") or []),
        "chemistryEventTimeline": list(validation.get("chemistryEventTimeline") or [])[:80],
        "manipulationEventCount": int(validation.get("manipulationEventCount") or 0),
        "eventCounts": dict(validation.get("eventCounts") or {}),
    }


def _compact_variant(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "repairMode": item.get("repairMode"),
        "purifierIndex": item.get("purifierIndex"),
        "unbonderIndex": item.get("unbonderIndex"),
        "opportunity": item.get("opportunity"),
        "unbondCandidate": item.get("unbondCandidate"),
        "validation": _compact_validation(item.get("validation") or {}),
    }


def probe(
    puzzle_path: Path,
    baseline_solution_path: Path,
    *,
    max_cycles: int = 256,
    opportunity_limit: int = 80,
    variant_limit: int = 240,
    result_limit: int = 20,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_solution_path)

    result = search_purification_placements(
        puzzle,
        solution,
        max_cycles=max_cycles,
        opportunity_limit=opportunity_limit,
        variant_limit=variant_limit,
        result_limit=result_limit,
    )
    compact_variants = [_compact_variant(item) for item in result.get("variants") or []]
    best_raw = (result.get("variants") or [None])[0]

    output_solution = None
    if best_raw is not None and solution_output is not None and best_raw.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_raw["solution"], solution_output)
        output_solution = str(solution_output)

    best = None
    if best_raw is not None:
        best = {**_compact_variant(best_raw), "solutionOutput": output_solution}

    return {
        "schemaVersion": "0.2.0",
        "kind": "strict-heldout-trace-guided-purification-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": baseline_solution_path.name,
        "targetSolutionBytesUsed": 0,
        "baselinePartCount": len(solution.get("parts") or []),
        "baselinePurifierCount": sum(
            str(part.get("type") or "") == "glyph-purification"
            for part in solution.get("parts") or []
        ),
        "baselineUnbonderCount": sum(
            str(part.get("type") or "") == "unbonder"
            for part in solution.get("parts") or []
        ),
        "request": {
            "maxCycles": max_cycles,
            "opportunityLimit": opportunity_limit,
            "variantLimit": variant_limit,
            "resultLimit": result_limit,
        },
        "summary": result.get("summary"),
        "baseline": result.get("baseline"),
        "opportunities": list(result.get("opportunities") or [])[:40],
        "variants": compact_variants,
        "bestVariant": best,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Place purification glyphs from generated-trace chemistry opportunities.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline-solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-cycles", type=int, default=256)
    parser.add_argument("--opportunity-limit", type=int, default=80)
    parser.add_argument("--variant-limit", type=int, default=240)
    parser.add_argument("--result-limit", type=int, default=20)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.baseline_solution,
        max_cycles=args.max_cycles,
        opportunity_limit=args.opportunity_limit,
        variant_limit=args.variant_limit,
        result_limit=args.result_limit,
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "baselinePurifierCount": report["baselinePurifierCount"],
        "baselineUnbonderCount": report["baselineUnbonderCount"],
        "summary": report["summary"],
        "bestVariant": report["bestVariant"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
