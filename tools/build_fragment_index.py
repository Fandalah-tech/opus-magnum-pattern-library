from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from packages.opus_analysis import extract_solution_fragments, trace_fragment_evidence
from packages.opus_parser import parse_puzzle, parse_solution


def _puzzle_lookup(root: Path) -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    if not root.exists():
        return lookup
    for path in root.rglob("*.puzzle"):
        lookup.setdefault(path.name.lower(), path)
        lookup.setdefault(path.stem.lower(), path)
    return lookup


def _representative_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_rank = {"dynamic-confirmed": 0, "dynamic-arm-observed": 1, "structural-only": 2}
    return min(
        records,
        key=lambda record: (
            evidence_rank.get(str(record.get("evidence", {}).get("level") or "structural-only"), 3),
            int(record.get("summary", {}).get("partCount") or 10**9),
            int(record.get("summary", {}).get("instructionCount") or 10**9),
            str(record.get("solutionSha256") or ""),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a reusable functional-fragment index from a solution archive.")
    parser.add_argument("--archive-root", type=Path, default=Path(".datasets/solution-archive"))
    parser.add_argument("--puzzle-root", type=Path, default=Path(".datasets/archive-campaign-reference"))
    parser.add_argument("--output", type=Path, default=Path("database/fragment-index.json"))
    parser.add_argument("--sample-limit", type=int, default=5)
    args = parser.parse_args()

    archive_index = json.loads((args.archive_root / "index.json").read_text(encoding="utf-8"))
    puzzle_lookup = _puzzle_lookup(args.puzzle_root)
    puzzle_cache: dict[Path, dict[str, Any]] = {}
    groups: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    role_counts: Counter[str] = Counter()
    evidence_levels: Counter[str] = Counter()
    parse_errors = []
    solution_count = 0
    fragment_count = 0
    replay_solution_count = 0

    for item in archive_index.get("solutions", []):
        path = args.archive_root / str(item["file"])
        try:
            solution = parse_solution(path)
            solution_count += 1
            puzzle_key = str(solution.get("puzzleFile") or item.get("puzzleName") or "<unknown>")
            puzzle_path = puzzle_lookup.get(Path(puzzle_key).name.lower()) or puzzle_lookup.get(Path(puzzle_key).stem.lower())
            if puzzle_path is not None:
                puzzle = puzzle_cache.setdefault(puzzle_path, parse_puzzle(puzzle_path))
                solution_fragments = trace_fragment_evidence(puzzle, solution)
                replay_solution_count += 1
            else:
                solution_fragments = extract_solution_fragments(solution)
                for fragment in solution_fragments:
                    fragment["evidence"] = {"level": "structural-only", "glyphSimulationAvailable": False}

            for fragment in solution_fragments:
                fragment_count += 1
                role = str(fragment["role"])
                mechanism_hash = str(fragment["canonicalMechanismHash"])
                role_counts[role] += 1
                evidence_levels[str(fragment.get("evidence", {}).get("level") or "structural-only")] += 1
                groups[(role, mechanism_hash)].append({
                    "puzzleKey": puzzle_key,
                    "solutionSha256": item.get("sha256") or solution.get("source", {}).get("sha256"),
                    "solutionFile": item.get("file"),
                    **fragment,
                })
        except Exception as exc:
            parse_errors.append({"file": item.get("file"), "errorType": type(exc).__name__, "message": str(exc)})

    fragments = []
    for (role, mechanism_hash), records in sorted(groups.items()):
        structural_hashes = sorted({str(record["canonicalStructuralHash"]) for record in records})
        source_puzzles = sorted({str(record["puzzleKey"]) for record in records})
        level_counts = Counter(str(record.get("evidence", {}).get("level") or "structural-only") for record in records)
        part_types = sorted({part_type for record in records for part_type in record.get("summary", {}).get("partTypes", [])})
        representative = _representative_record(records)
        fragments.append({
            "role": role,
            "canonicalMechanismHash": mechanism_hash,
            "occurrenceCount": len(records),
            "sourcePuzzleCount": len(source_puzzles),
            "sourcePuzzles": source_puzzles,
            "structuralVariantCount": len(structural_hashes),
            "canonicalStructuralHashes": structural_hashes,
            "partTypes": part_types,
            "representativeGeometry": representative.get("geometry"),
            "representativeSource": {
                "puzzleKey": representative.get("puzzleKey"),
                "solutionSha256": representative.get("solutionSha256"),
                "solutionFile": representative.get("solutionFile"),
                "evidenceLevel": representative.get("evidence", {}).get("level", "structural-only"),
            },
            "evidence": {
                "levels": dict(sorted(level_counts.items())),
                "dynamicConfirmedCount": level_counts["dynamic-confirmed"],
                "dynamicArmObservedCount": level_counts["dynamic-arm-observed"],
            },
            "samples": [
                {
                    "puzzleKey": record["puzzleKey"],
                    "solutionSha256": record["solutionSha256"],
                    "solutionFile": record["solutionFile"],
                    "anchorPartType": record["anchorPartType"],
                    "summary": record["summary"],
                    "evidence": record.get("evidence", {}),
                    "geometry": record.get("geometry"),
                }
                for record in records[:max(0, args.sample_limit)]
            ],
        })

    index = {
        "schemaVersion": "0.3.0",
        "summary": {
            "parsedSolutionCount": solution_count,
            "replaySolutionCount": replay_solution_count,
            "rawFragmentCount": fragment_count,
            "canonicalFragmentCount": len(fragments),
            "roleCounts": dict(sorted(role_counts.items())),
            "evidenceLevels": dict(sorted(evidence_levels.items())),
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
