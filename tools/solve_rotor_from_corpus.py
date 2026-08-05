from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.seed_solver import solve_from_reference_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and extract a Rotor seed solution from a solution corpus.")
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    result = solve_from_reference_corpus(puzzle, args.corpus)
    report = {
        "found": result.found,
        "filename": result.filename,
        "validation": result.validation,
        "attempted": result.attempted,
        "rejected": list(result.rejected),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not result.found or result.solution is None:
        return 1
    write_solution(result.solution, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
