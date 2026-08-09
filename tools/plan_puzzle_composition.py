from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle
from packages.opus_solver import plan_puzzle_fragment_chains


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank historical fragment chains against a target puzzle manufacturing plan.")
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--flow-index", type=Path, default=Path("database/fragment-flow-index.json"))
    parser.add_argument("--fragment-index", type=Path, default=Path("database/fragment-index.json"))
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--min-observations", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    flow_index = json.loads(args.flow_index.read_text(encoding="utf-8"))
    fragment_index = json.loads(args.fragment_index.read_text(encoding="utf-8")) if args.fragment_index.exists() else None
    result = plan_puzzle_fragment_chains(
        puzzle,
        flow_index,
        fragment_index=fragment_index,
        max_depth=args.max_depth,
        limit=args.limit,
        min_observations=args.min_observations,
    )
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if result["summary"]["supported"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
