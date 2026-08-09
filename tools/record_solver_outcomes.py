from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle
from packages.opus_solver.outcome_learning import build_outcome_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a composed-generation report into the compact solver outcome learning index.")
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("generation_report", type=Path)
    parser.add_argument("--output", type=Path, default=Path("database/solver-outcomes.json"))
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    generation = json.loads(args.generation_report.read_text(encoding="utf-8"))
    existing = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else None
    index = build_outcome_index(puzzle, generation, existing_index=existing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(index.get("summary", {}), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
