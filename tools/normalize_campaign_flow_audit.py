from __future__ import annotations

import argparse
import json
from pathlib import Path


def normalize_campaign_audit(
    campaign_root: Path,
    audit_report: dict,
    campaign_index: dict,
) -> dict:
    puzzle_paths = {
        str(item.get("puzzleId") or ""): campaign_root / str(item.get("localPath") or "")
        for item in campaign_index.get("puzzles", [])
        if item.get("puzzleId") and item.get("localPath")
    }
    normalized = []
    missing_puzzles = []
    for record in audit_report.get("results", []):
        puzzle_id = str(record.get("puzzleId") or "")
        solution_path = str(record.get("solution") or record.get("solutionPath") or "")
        puzzle_path = puzzle_paths.get(puzzle_id)
        if puzzle_path is None:
            missing_puzzles.append(puzzle_id)
            continue
        normalized.append({
            **record,
            "puzzlePath": str(puzzle_path),
            "solutionPath": solution_path,
        })

    status_counts = {}
    for record in normalized:
        status = str(record.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "schemaVersion": "0.1.0-campaign-flow-adapter",
        "analysis": "campaign-engine-audit-flow-adapter",
        "solutionRoot": str(campaign_root),
        "source": {
            "campaignIndexSchemaVersion": campaign_index.get("schemaVersion"),
            "campaignAuditSchemaVersion": audit_report.get("schemaVersion"),
        },
        "summary": {
            "solutionCount": len(normalized),
            "engineComplete": status_counts.get("engine-complete", 0),
            "engineIncomplete": status_counts.get("engine-incomplete", 0),
            "engineErrors": status_counts.get("engine-error", 0),
            "missingPuzzleRecordCount": len(missing_puzzles),
        },
        "missingPuzzleIds": sorted(set(missing_puzzles)),
        "results": normalized,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt a campaign corpus audit to the generic flow-index learner contract.")
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    normalized = normalize_campaign_audit(args.campaign_root, audit, index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(normalized["summary"], sort_keys=True))
    return 1 if normalized["summary"]["missingPuzzleRecordCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
