from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle
from packages.opus_solver import build_disjoint_product_plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the logical components and chemistry lower bounds of a disjoint puzzle."
    )
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    plan = build_disjoint_product_plan(puzzle)
    payload = {
        "puzzle": puzzle.get("name"),
        "source": puzzle.get("source"),
        "plan": plan.to_dict(),
    }
    encoded = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if plan.supported else 1


if __name__ == "__main__":
    raise SystemExit(main())
