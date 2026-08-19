from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution
from packages.opus_solver.input_footprint_repair import replay_summary
from packages.opus_solver.purification_chain import purification_profile
from packages.opus_solver.additive_purification_search import search_additive_purification_stations
from packages.opus_solver.intermediate_convergence import search_intermediate_convergence


def probe(puzzle_path: Path, solution_path: Path, *, max_cycles: int = 500) -> dict:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(solution_path)
    profile = purification_profile(puzzle, solution, max_cycles=max_cycles)
    replayed = replay_summary(puzzle, solution, max_cycles=max_cycles)
    replayed.pop("replay", None)

    additive = search_additive_purification_stations(
        puzzle,
        solution,
        max_cycles=max_cycles,
        opportunity_limit=200,
        result_limit=12,
    )
    frontier = str(profile.get("frontierElement") or "")
    convergence = None
    if frontier:
        convergence = search_intermediate_convergence(
            puzzle,
            solution,
            element=frontier,
            max_cycles=max_cycles,
            observation_limit=120,
            result_limit=12,
        )

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-safe-seed-frontier-probe",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": solution_path.name,
        "targetSolutionBytesUsed": 0,
        "request": {"maxCycles": max_cycles},
        "purificationProfile": profile,
        "replaySummary": replayed,
        "additiveSummary": additive.get("summary"),
        "additiveOpportunities": list(additive.get("opportunities") or [])[:20],
        "convergenceSummary": (convergence or {}).get("summary"),
        "convergenceObservations": list((convergence or {}).get("observations") or [])[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe local chemistry after an authoritative mechanical repair.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    args = parser.parse_args()

    report = probe(args.puzzle, args.solution, max_cycles=args.max_cycles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "purificationProfile": report["purificationProfile"],
        "replaySummary": report["replaySummary"],
        "additiveSummary": report["additiveSummary"],
        "convergenceSummary": report["convergenceSummary"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
