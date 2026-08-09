from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline, canonical_solution_hash
from packages.opus_parser import parse_solution


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse, canonicalize, and structurally analyze an external Opus Magnum solution archive.")
    parser.add_argument("--archive-root", type=Path, default=Path(".datasets/solution-archive"))
    parser.add_argument("--campaign-root", type=Path, default=Path(".datasets/archive-campaign-reference"))
    parser.add_argument("--output", type=Path, default=Path("reports/solution-archive-analysis.json"))
    args = parser.parse_args()

    archive_index = json.loads((args.archive_root / "index.json").read_text(encoding="utf-8"))
    campaign_index = json.loads((args.campaign_root / "index.json").read_text(encoding="utf-8"))
    puzzle_ids = {Path(item["localPath"]).stem for item in campaign_index.get("puzzles", [])}

    results: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    part_usage: Counter[str] = Counter()
    puzzle_file_usage: Counter[str] = Counter()
    archive_puzzle_usage: Counter[str] = Counter()
    instructions_by_type: Counter[str] = Counter()
    programs_by_arm_count: Counter[int] = Counter()
    errors: Counter[str] = Counter()
    error_samples: defaultdict[str, list[str]] = defaultdict(list)
    structural_hashes: Counter[str] = Counter()
    mechanism_hashes: Counter[str] = Counter()
    structural_by_puzzle: defaultdict[str, Counter[str]] = defaultdict(Counter)
    mechanism_by_puzzle: defaultdict[str, Counter[str]] = defaultdict(Counter)
    matched_archive_names: defaultdict[str, set[str]] = defaultdict(set)

    items = archive_index.get("solutions", [])
    for number, item in enumerate(items, start=1):
        relative = str(item["file"])
        path = args.archive_root / relative
        record: dict[str, Any] = {
            "file": relative,
            "archivePuzzleName": item.get("puzzleName"),
            "sha256": item.get("sha256"),
        }
        try:
            solution = parse_solution(path)
            puzzle_file = str(solution.get("puzzleFile") or "")
            part_types = sorted({str(part.get("type") or "") for part in solution.get("parts", [])})
            arm_parts = [part for part in solution.get("parts", []) if str(part.get("type") or "").startswith("arm") or part.get("type") == "piston"]
            timeline = build_program_timeline(solution)
            cycles = timeline.get("cycles", [])
            structural_hash = canonical_solution_hash(solution, normalize_time=False)
            mechanism_hash = canonical_solution_hash(solution, normalize_time=True)
            structural_hashes[structural_hash] += 1
            mechanism_hashes[mechanism_hash] += 1
            structural_by_puzzle[puzzle_file][structural_hash] += 1
            mechanism_by_puzzle[puzzle_file][mechanism_hash] += 1

            instruction_count = 0
            for part in solution.get("parts", []):
                for instruction in part.get("program", []):
                    name = str(instruction.get("instruction") or "unknown")
                    instructions_by_type[name] += 1
                    instruction_count += 1

            matched = puzzle_file in puzzle_ids
            status = "parsed-matched" if matched else "parsed-unmatched"
            statuses[status] += 1
            for part_type in part_types:
                part_usage[part_type] += 1
            puzzle_file_usage[puzzle_file or "<empty>"] += 1
            archive_name = str(item.get("puzzleName") or "unknown")
            archive_puzzle_usage[archive_name] += 1
            if puzzle_file:
                matched_archive_names[archive_name].add(puzzle_file)
            programs_by_arm_count[len(arm_parts)] += 1
            record.update({
                "status": status,
                "puzzleFile": puzzle_file,
                "campaignPuzzleMatched": matched,
                "metrics": solution.get("metrics", {}),
                "partTypes": part_types,
                "partCount": len(solution.get("parts", [])),
                "armCount": len(arm_parts),
                "cycleSlots": len(cycles),
                "instructionCount": instruction_count,
                "canonicalStructuralHash": structural_hash,
                "canonicalMechanismHash": mechanism_hash,
            })
        except Exception as exc:
            status = "parse-error"
            statuses[status] += 1
            error_name = type(exc).__name__
            errors[error_name] += 1
            if len(error_samples[error_name]) < 5:
                error_samples[error_name].append(str(exc))
            record.update({"status": status, "errorType": error_name, "message": str(exc)})
        results.append(record)
        if number % 250 == 0:
            print(json.dumps({"processed": number, "total": len(items), "statuses": dict(statuses), "uniqueMechanisms": len(mechanism_hashes)}), flush=True)

    duplicate_structural_groups = {key: count for key, count in structural_hashes.items() if count > 1}
    duplicate_mechanism_groups = {key: count for key, count in mechanism_hashes.items() if count > 1}
    summary = {
        "total": len(results),
        "parsed": statuses["parsed-matched"] + statuses["parsed-unmatched"],
        "campaignMatched": statuses["parsed-matched"],
        "campaignUnmatched": statuses["parsed-unmatched"],
        "parseErrors": statuses["parse-error"],
        "distinctArchivePuzzleNames": len(archive_puzzle_usage),
        "distinctPuzzleFileIds": len([key for key in puzzle_file_usage if key != "<empty>"]),
        "uniqueCanonicalStructures": len(structural_hashes),
        "structuralDuplicateGroups": len(duplicate_structural_groups),
        "structuralDuplicateSolutions": sum(count - 1 for count in duplicate_structural_groups.values()),
        "uniqueCanonicalMechanisms": len(mechanism_hashes),
        "mechanismDuplicateGroups": len(duplicate_mechanism_groups),
        "mechanismDuplicateSolutions": sum(count - 1 for count in duplicate_mechanism_groups.values()),
        "partUsage": dict(sorted(part_usage.items())),
        "programsByArmCount": {str(k): v for k, v in sorted(programs_by_arm_count.items())},
        "instructionUsage": dict(instructions_by_type.most_common()),
        "parseErrorsByType": dict(sorted(errors.items())),
        "parseErrorSamples": dict(sorted(error_samples.items())),
        "archiveNameToPuzzleIds": {key: sorted(value) for key, value in sorted(matched_archive_names.items())},
        "uniqueStructuresByPuzzle": {key: len(value) for key, value in sorted(structural_by_puzzle.items())},
        "uniqueMechanismsByPuzzle": {key: len(value) for key, value in sorted(mechanism_by_puzzle.items())},
    }
    report = {"schemaVersion": "0.2.0", "summary": summary, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    concise_keys = (
        "total", "parsed", "campaignMatched", "campaignUnmatched", "parseErrors",
        "distinctArchivePuzzleNames", "distinctPuzzleFileIds", "uniqueCanonicalStructures",
        "structuralDuplicateSolutions", "uniqueCanonicalMechanisms", "mechanismDuplicateSolutions",
    )
    print(json.dumps({key: summary[key] for key in concise_keys}), flush=True)
    print(json.dumps({"parseErrorsByType": summary["parseErrorsByType"], "parseErrorSamples": summary["parseErrorSamples"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
