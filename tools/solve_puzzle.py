from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle
from packages.opus_solver.autonomous import solve_puzzle_auto


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a solution with the autonomous Opus solver."
    )
    parser.add_argument("puzzle", type=Path, help="Path to an Opus Magnum .puzzle file")
    parser.add_argument("output", type=Path, help="Destination .solution file")
    parser.add_argument(
        "--flow-index",
        type=Path,
        help="Optional engine-coherent fragment-flow knowledge index used when the direct generator cannot solve the puzzle.",
    )
    parser.add_argument(
        "--fragment-index",
        type=Path,
        help="Optional fragment geometry index. Defaults to --flow-index when omitted.",
    )
    parser.add_argument(
        "--composition-limit",
        type=int,
        default=10,
        help="Maximum learned assemblies attempted by the autonomous composition fallback.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report containing the manufacturing plan and validation",
    )
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    flow_index = (
        json.loads(args.flow_index.read_text(encoding="utf-8"))
        if args.flow_index
        else None
    )
    fragment_index = (
        json.loads(args.fragment_index.read_text(encoding="utf-8"))
        if args.fragment_index
        else None
    )
    result = solve_puzzle_auto(
        puzzle,
        flow_index=flow_index,
        fragment_index=fragment_index,
        composition_limit=max(1, int(args.composition_limit)),
    )
    result.write(args.output)

    report = result.to_dict(include_solution=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "puzzle": result.puzzle_name,
        "strategy": result.strategy,
        "route": result.validation.get("solverRoute"),
        "output": str(args.output),
        "validation": result.validation,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
