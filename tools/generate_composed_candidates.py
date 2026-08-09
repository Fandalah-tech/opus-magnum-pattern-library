from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver import generate_composed_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate database-driven Opus Magnum candidate solutions from fragment assembly priors.")
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--flow-index", type=Path, default=Path("database/fragment-flow-index.json"))
    parser.add_argument("--fragment-index", type=Path, default=Path("database/fragment-index.json"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--no-engine-validation", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("reports/composed-candidates.json"))
    parser.add_argument("--write-best", type=Path)
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    flow_index = json.loads(args.flow_index.read_text(encoding="utf-8"))
    fragment_index = json.loads(args.fragment_index.read_text(encoding="utf-8"))
    result = generate_composed_candidates(
        puzzle,
        flow_index,
        fragment_index,
        limit=args.limit,
        validate_engine=not args.no_engine_validation,
    )

    report = dict(result)
    # Binary payloads are never embedded in JSON reports.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.write_best:
        best = next(
            (
                item for item in result.get("candidates", [])
                if item.get("serialization", {}).get("roundTripClean") and item.get("solution")
            ),
            None,
        )
        if best is not None:
            write_solution(best["solution"], args.write_best, version=7)

    print(json.dumps(result.get("summary", {}), sort_keys=True))
    return 0 if result.get("summary", {}).get("supported") else 2


if __name__ == "__main__":
    raise SystemExit(main())
