from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver import (
    generate_blind_transfer_candidates,
    validate_blind_transfer_contract,
)
from tools.omsim_adapter.validate import run_omsim


def _winner_key(record: dict[str, Any]) -> tuple[int, ...]:
    metrics = record["oracleValidation"]["metrics"]
    return tuple(
        int(metrics.get(name)) if isinstance(metrics.get(name), int) else 10**12
        for name in ("cost", "instructions", "cycles", "area")
    )


def _text_report(report: dict[str, Any]) -> str:
    contract = report["blindContract"]
    summary = report["summary"]
    winner = report.get("winner") or {}
    metrics = (winner.get("oracleValidation") or {}).get("metrics") or {}
    lines = [
        "BLIND CROSS-PUZZLE MECHANISM TRANSFER",
        "======================================",
        "",
        f"Target: {report['target']['name']} ({contract['targetPuzzleId']})",
        f"Donor: {report['donor']['name']} ({contract['donorPuzzleId']})",
        f"Target solutions read: {contract['targetSolutionsRead']}",
        f"Candidates generated from donor fragments: {summary['candidateCount']}",
        f"OMSim-valid candidates: {summary['validCandidateCount']}",
        "",
    ]
    if winner:
        lines.extend((
            "Accepted transfer",
            "-----------------",
            f"Candidate: {winner['candidateId']}",
            f"Donor parts: {', '.join(winner['sourcePartIds'])}",
            f"Cost: {metrics.get('cost')}",
            f"Instructions: {metrics.get('instructions')}",
            f"Cycles: {metrics.get('cycles')}",
            f"Area: {metrics.get('area')}",
            f"Solution: {winner['selectedSolutionPath']}",
            "",
        ))
    lines.extend((
        "Protocol",
        "--------",
        "The generator accepts exactly one donor solution and rejects it unless",
        "its puzzle ID matches the donor and differs from the target. It has no",
        "target-solution-root input, so target solutions cannot enter retrieval,",
        "ranking, fragment extraction, or validation.",
        "",
    ))
    return "\n".join(lines)


def transfer_solution_blind(
    target_puzzle_path: Path,
    donor_puzzle_path: Path,
    donor_solution_path: Path,
    output_dir: Path,
    *,
    omsim: Path,
    timeout: int = 60,
) -> dict[str, Any]:
    target = parse_puzzle(target_puzzle_path)
    donor = parse_puzzle(donor_puzzle_path)
    donor_solution = parse_solution(donor_solution_path)
    contract = validate_blind_transfer_contract(target, donor, donor_solution)
    candidates = generate_blind_transfer_candidates(target, donor, donor_solution)

    candidate_dir = output_dir / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for candidate in candidates:
        path = candidate_dir / f"{candidate.candidate_id}.solution"
        write_solution(candidate.solution, path, version=7)
        oracle = run_omsim(
            omsim,
            target_puzzle_path,
            path,
            timeout,
            output_intervals=True,
        )
        records.append({
            **candidate.to_dict(),
            "candidatePath": str(path),
            "oracleValidation": oracle,
        })

    valid = [record for record in records if record["oracleValidation"].get("valid")]
    winner = min(valid, key=_winner_key) if valid else None
    selected_path = None
    if winner:
        selected = next(
            candidate for candidate in candidates
            if candidate.candidate_id == winner["candidateId"]
        )
        selected_solution = deepcopy(selected.solution)
        selected_solution["name"] = "Opus Solver - blind cross-puzzle transfer"
        selected_path = output_dir / "blind-transfer.solution"
        write_solution(selected_solution, selected_path, version=7)
        winner = {**winner, "selectedSolutionPath": str(selected_path)}

    report = {
        "schemaVersion": "0.1.0",
        "status": "ready" if winner else "no-valid-transfer",
        "target": {
            "path": str(target_puzzle_path),
            "name": target.get("name"),
            "sha256": (target.get("source") or {}).get("sha256"),
        },
        "donor": {
            "puzzlePath": str(donor_puzzle_path),
            "solutionPath": str(donor_solution_path),
            "name": donor.get("name"),
            "puzzleSha256": (donor.get("source") or {}).get("sha256"),
            "solutionSha256": (donor_solution.get("source") or {}).get("sha256"),
        },
        "blindContract": contract,
        "summary": {
            "candidateCount": len(records),
            "validCandidateCount": len(valid),
            "targetSolutionCountRead": 0,
        },
        "candidates": records,
        "winner": winner,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "blind-transfer-report.json"
    text_path = output_dir / "BLIND_TRANSFER_REPORT.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text_path.write_text(_text_report(report), encoding="utf-8")
    return {
        **report,
        "reportPath": str(json_path),
        "textReportPath": str(text_path),
        "selectedSolutionPath": str(selected_path) if selected_path else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transfer a donor-only direct mechanism to a target puzzle and validate it with OMSim."
    )
    parser.add_argument("target_puzzle", type=Path)
    parser.add_argument("donor_puzzle", type=Path)
    parser.add_argument("donor_solution", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    report = transfer_solution_blind(
        args.target_puzzle,
        args.donor_puzzle,
        args.donor_solution,
        args.output_dir,
        omsim=args.omsim,
        timeout=args.timeout,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
