from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_analysis import puzzle_feature_payload
from packages.opus_parser import parse_puzzle
from packages.opus_solver import rank_mechanisms


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank reusable Opus Magnum mechanisms for a target puzzle.")
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--features", type=Path, default=Path("database/puzzle-feature-index.json"))
    parser.add_argument("--solver-index", type=Path, default=Path("database/solver-index.json"))
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--include-incompatible", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    target = parse_puzzle(args.puzzle)
    feature_index = json.loads(args.features.read_text(encoding="utf-8"))
    solver_index = json.loads(args.solver_index.read_text(encoding="utf-8"))
    ranked = rank_mechanisms(
        puzzle_feature_payload(target),
        feature_index,
        solver_index,
        limit=args.limit,
        include_incompatible=args.include_incompatible,
    )

    result = {
        "schemaVersion": "0.1.0",
        "target": {
            "file": str(args.puzzle),
            "name": target.get("name"),
            "sha256": target.get("source", {}).get("sha256"),
        },
        "candidateCount": len(ranked),
        "candidates": ranked,
    }
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
