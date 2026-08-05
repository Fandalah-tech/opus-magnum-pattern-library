from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle
from packages.opus_solver import solve_puzzle


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a solution with the bounded Opus solver MVP.")
    parser.add_argument("puzzle", type=Path, help="Path to an Opus Magnum .puzzle file")
    parser.add_argument("output", type=Path, help="Destination .solution file")
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report containing the manufacturing plan and validation",
    )
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    result = solve_puzzle(puzzle)
    result.write(args.output)

    report = result.to_dict(include_solution=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "puzzle": result.puzzle_name,
        "strategy": result.strategy,
        "output": str(args.output),
        "validation": result.validation,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
