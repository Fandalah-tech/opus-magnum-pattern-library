from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_parser import ParseError, parse_puzzle
from packages.opus_solver import BlindTransferContractError, puzzle_file_id
from tools.transfer_solution_blind import transfer_solution_blind


def _text_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "BLIND TRANSFER REGRESSION MATRIX",
        "================================",
        "",
        f"Donor puzzle: {report['donorPuzzleId']}",
        f"Puzzle files scanned: {summary['puzzleFileCount']}",
        f"Puzzle parse failures: {summary['parseFailureCount']}",
        f"Chemistry-compatible targets: {summary['compatibleTargetCount']}",
        f"Targets solved by OMSim: {summary['solvedTargetCount']}",
        f"Targets rejected by OMSim: {summary['unsolvedTargetCount']}",
        f"Target solutions read: {summary['targetSolutionCountRead']}",
        "",
        "Compatible targets",
        "------------------",
    ]
    for target in report["targets"]:
        winner = target.get("winner") or {}
        metrics = winner.get("metrics") or {}
        status = "VALID" if target["status"] == "ready" else "REJECTED"
        lines.append(
            f"{status:8} {target['targetPuzzleId']:28} "
            f"candidates={target['candidateCount']} valid={target['validCandidateCount']} "
            f"mapping={target.get('targetMapping')} "
            f"metrics={metrics or '-'}"
        )
    lines.extend((
        "",
        "Protocol",
        "--------",
        "Only .puzzle files are scanned for targets. The command accepts one",
        "explicit donor .solution and has no target solution directory input.",
        "Incompatible puzzles are rejected before OMSim candidate validation.",
        "",
    ))
    return "\n".join(lines)


def validate_blind_transfer_matrix(
    puzzle_root: Path,
    donor_puzzle_path: Path,
    donor_solution_path: Path,
    output_dir: Path,
    *,
    omsim: Path,
    excluded_target_ids: set[str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    donor = parse_puzzle(donor_puzzle_path)
    donor_id = puzzle_file_id(donor)
    excluded = set(excluded_target_ids or ()) | {donor_id}
    puzzle_paths = sorted(puzzle_root.rglob("*.puzzle"))
    targets: list[dict[str, Any]] = []
    incompatible: list[dict[str, str]] = []
    excluded_records: list[dict[str, str]] = []
    parse_failures: list[dict[str, str]] = []

    for target_path in puzzle_paths:
        try:
            target = parse_puzzle(target_path)
        except ParseError as error:
            parse_failures.append({
                "path": str(target_path),
                "reason": str(error),
            })
            continue
        target_id = puzzle_file_id(target)
        if target_id in excluded:
            excluded_records.append({
                "targetPuzzleId": target_id,
                "path": str(target_path),
            })
            continue
        try:
            result = transfer_solution_blind(
                target_path,
                donor_puzzle_path,
                donor_solution_path,
                output_dir / "targets" / target_id,
                omsim=omsim,
                timeout=timeout,
            )
        except BlindTransferContractError as error:
            incompatible.append({
                "targetPuzzleId": target_id,
                "path": str(target_path),
                "reason": str(error),
            })
            continue

        winner = result.get("winner") or {}
        oracle = winner.get("oracleValidation") or {}
        targets.append({
            "targetPuzzleId": target_id,
            "targetName": target.get("name"),
            "targetPath": str(target_path),
            "production": bool(target.get("production")),
            "status": result["status"],
            "candidateCount": result["summary"]["candidateCount"],
            "validCandidateCount": result["summary"]["validCandidateCount"],
            "targetSolutionCountRead": result["summary"]["targetSolutionCountRead"],
            "targetMapping": winner.get("targetMapping"),
            "winner": {
                "candidateId": winner.get("candidateId"),
                "metrics": oracle.get("metrics"),
                "rate": oracle.get("rate"),
                "sourcePartIds": winner.get("sourcePartIds"),
            } if winner else None,
        })

    solved = [target for target in targets if target["status"] == "ready"]
    report = {
        "schemaVersion": "0.1.0",
        "status": "ready" if solved else "no-valid-transfer",
        "puzzleRoot": str(puzzle_root),
        "donorPuzzleId": donor_id,
        "donorPuzzlePath": str(donor_puzzle_path),
        "donorSolutionPath": str(donor_solution_path),
        "excludedTargetIds": sorted(excluded),
        "summary": {
            "puzzleFileCount": len(puzzle_paths),
            "excludedTargetCount": len(excluded_records),
            "parseFailureCount": len(parse_failures),
            "incompatibleTargetCount": len(incompatible),
            "compatibleTargetCount": len(targets),
            "solvedTargetCount": len(solved),
            "unsolvedTargetCount": len(targets) - len(solved),
            "candidateCount": sum(target["candidateCount"] for target in targets),
            "validCandidateCount": sum(target["validCandidateCount"] for target in targets),
            "targetSolutionCountRead": 0,
        },
        "targets": targets,
        "parseFailures": parse_failures,
        "incompatibleTargets": incompatible,
        "excludedTargets": excluded_records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "blind-transfer-matrix-report.json"
    text_path = output_dir / "BLIND_TRANSFER_MATRIX_REPORT.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text_path.write_text(_text_report(report), encoding="utf-8")
    return {
        **report,
        "reportPath": str(json_path),
        "textReportPath": str(text_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one donor-only mechanism against a puzzle-only target matrix."
    )
    parser.add_argument("puzzle_root", type=Path)
    parser.add_argument("donor_puzzle", type=Path)
    parser.add_argument("donor_solution", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--exclude-target", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    report = validate_blind_transfer_matrix(
        args.puzzle_root,
        args.donor_puzzle,
        args.donor_solution,
        args.output_dir,
        omsim=args.omsim,
        excluded_target_ids=set(args.exclude_target),
        timeout=args.timeout,
    )
    print(json.dumps({
        "status": report["status"],
        "summary": report["summary"],
        "targets": report["targets"],
        "reportPath": report["reportPath"],
        "textReportPath": report["textReportPath"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
