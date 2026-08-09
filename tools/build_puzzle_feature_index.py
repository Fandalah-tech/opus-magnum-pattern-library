from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_analysis import puzzle_feature_fingerprint, puzzle_feature_payload
from packages.opus_parser import parse_puzzle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build solver-oriented feature fingerprints for a puzzle corpus.")
    parser.add_argument("--root", type=Path, default=Path(".datasets/archive-campaign-reference"))
    parser.add_argument("--output", type=Path, default=Path("database/puzzle-feature-index.json"))
    args = parser.parse_args()

    records = []
    errors = []
    for path in sorted(args.root.rglob("*.puzzle")):
        try:
            puzzle = parse_puzzle(path)
            records.append({
                "sourceFile": path.relative_to(args.root).as_posix(),
                "sha256": puzzle.get("source", {}).get("sha256"),
                "name": puzzle.get("name"),
                "fingerprint": puzzle_feature_fingerprint(puzzle),
                "features": puzzle_feature_payload(puzzle),
            })
        except Exception as exc:
            errors.append({
                "sourceFile": path.relative_to(args.root).as_posix(),
                "errorType": type(exc).__name__,
                "message": str(exc),
            })

    index = {
        "schemaVersion": "0.1.0",
        "summary": {
            "puzzleCount": len(records),
            "fingerprintCount": len({record["fingerprint"] for record in records}),
            "parseErrorCount": len(errors),
        },
        "puzzles": records,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(index["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
