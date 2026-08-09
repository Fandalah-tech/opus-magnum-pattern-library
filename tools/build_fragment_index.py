from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from packages.opus_analysis import extract_solution_fragments
from packages.opus_parser import parse_solution


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a reusable functional-fragment index from a solution archive.")
    parser.add_argument("--archive-root", type=Path, default=Path(".datasets/solution-archive"))
    parser.add_argument("--output", type=Path, default=Path("database/fragment-index.json"))
    parser.add_argument("--sample-limit", type=int, default=5)
    args = parser.parse_args()

    archive_index = json.loads((args.archive_root / "index.json").read_text(encoding="utf-8"))
    groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    role_counts: Counter[str] = Counter()
    parse_errors = []
    solution_count = 0
    fragment_count = 0

    for item in archive_index.get("solutions", []):
        path = args.archive_root / str(item["file"])
        try:
            solution = parse_solution(path)
            solution_count += 1
            puzzle_key = str(solution.get("puzzleFile") or item.get("puzzleName") or "<unknown>")
            for fragment in extract_solution_fragments(solution):
                fragment_count += 1
                role = str(fragment["role"])
                mechanism_hash = str(fragment["canonicalMechanismHash"])
                role_counts[role] += 1
                groups[(role, mechanism_hash)].append({
                    "puzzleKey": puzzle_key,
                    "solutionSha256": item.get("sha256") or solution.get("source", {}).get("sha256"),
                    "solutionFile": item.get("file"),
                    **fragment,
                })
        except Exception as exc:
            parse_errors.append({
                "file": item.get("file"),
                "errorType": type(exc).__name__,
                "message": str(exc),
            })

    fragments = []
    for (role, mechanism_hash), records in sorted(groups.items()):
        structural_hashes = sorted({str(record["canonicalStructuralHash"]) for record in records})
        source_puzzles = sorted({str(record["puzzleKey"]) for record in records})
        part_types = sorted({
            part_type
            for record in records
            for part_type in record.get("summary", {}).get("partTypes", [])
        })
        fragments.append({
            "role": role,
            "canonicalMechanismHash": mechanism_hash,
            "occurrenceCount": len(records),
            "sourcePuzzleCount": len(source_puzzles),
            "sourcePuzzles": source_puzzles,
            "structuralVariantCount": len(structural_hashes),
            "canonicalStructuralHashes": structural_hashes,
            "partTypes": part_types,
            "samples": [
                {
                    "puzzleKey": record["puzzleKey"],
                    "solutionSha256": record["solutionSha256"],
                    "solutionFile": record["solutionFile"],
                    "anchorPartType": record["anchorPartType"],
                    "summary": record["summary"],
                }
                for record in records[:max(0, args.sample_limit)]
            ],
        })

    index = {
        "schemaVersion": "0.1.0",
        "summary": {
            "parsedSolutionCount": solution_count,
            "rawFragmentCount": fragment_count,
            "canonicalFragmentCount": len(fragments),
            "roleCounts": dict(sorted(role_counts.items())),
            "parseErrorCount": len(parse_errors),
        },
        "fragments": fragments,
        "errors": parse_errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(index["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
