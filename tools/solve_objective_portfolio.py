from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_parser.solution_writer import write_solution_bytes
from packages.opus_solver import (
    OBJECTIVES,
    generate_objective_candidates,
    objective_key,
    select_objective_winners,
)
from tools.omsim_adapter.validate import run_omsim


def _derived_values(metrics: dict[str, Any]) -> dict[str, int | None]:
    required = ("cost", "cycles", "area", "instructions")
    if not all(isinstance(metrics.get(key), int) for key in required):
        return {"costarea": None, "costcycles": None, "sum4": None}
    cost, cycles, area, instructions = (int(metrics[key]) for key in required)
    return {
        "costarea": cost * area,
        "costcycles": cost + cycles,
        "sum4": cost + cycles + area + instructions,
    }


def _primary_value(objective: str, metrics: dict[str, Any]) -> int | None:
    if objective in {"cost", "area", "cycles", "rate", "instructions"}:
        value = metrics.get(objective)
        return int(value) if isinstance(value, int) else None
    return _derived_values(metrics).get(objective)


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_validation_summary(validation: dict[str, Any]) -> dict[str, Any]:
    error = validation.get("firstError") or {}
    message = str(error.get("message") or "")
    return {
        "complete": bool(validation.get("complete")),
        "failureMode": validation.get("failureMode"),
        "completedCycles": validation.get("completedCycles"),
        "deliveredByProduct": deepcopy(validation.get("deliveredByProduct") or {}),
        "firstError": (
            {
                "cycle": error.get("cycle"),
                "message": message[:240] + ("..." if len(message) > 240 else ""),
            }
            if error
            else None
        ),
    }


def _text_report(report: dict[str, Any]) -> str:
    lines = [
        "OBJECTIVE ARCHITECTURE PORTFOLIO",
        "================================",
        "",
        f"Status: {report['status']}",
        f"Generated architectures: {report['summary']['candidateCount']}",
        f"OMSim-valid architectures: {report['summary']['oracleValidCandidateCount']}",
        f"Distinct binary architectures: {report['summary']['distinctCandidateCount']}",
        "",
        "Winners",
        "-------",
    ]
    for objective in OBJECTIVES:
        winner = report["winners"][objective]
        metrics = winner["metrics"]
        lines.append(
            f"{objective:12} {winner['architectureId']:36} "
            f"cost={metrics.get('cost')} cycles={metrics.get('cycles')} "
            f"area={metrics.get('area')} instructions={metrics.get('instructions')} "
            f"rate={metrics.get('rate')} score={winner['objectiveScore'][0]}"
        )
    lines.extend(("", "Baseline improvements", "---------------------"))
    for objective in ("cost", "area", "cycles", "rate", "instructions"):
        item = report["improvements"][objective]
        lines.append(
            f"{objective:12} {item['baseline']} -> {item['winner']} "
            f"({item['delta']:+d})"
        )
    lines.extend((
        "",
        "Validation note",
        "---------------",
        "OMSim is authoritative for final acceptance. Local-engine divergences remain",
        "recorded per candidate so they can drive the next simulator-fidelity work.",
        "",
    ))
    return "\n".join(lines)


def solve_objective_portfolio(
    puzzle_path: Path,
    output_dir: Path,
    *,
    omsim: Path,
    timeout: int = 60,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir = output_dir / "candidates"
    final_dir = output_dir / "final"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    candidates = generate_objective_candidates(puzzle)
    records: list[dict[str, Any]] = []
    candidate_by_id = {candidate.architecture_id: candidate for candidate in candidates}

    for candidate in candidates:
        path = candidate_dir / f"{candidate.architecture_id}.solution"
        write_solution(candidate.solution, path, version=7)
        reparsed = parse_solution(path)
        round_trip_clean = (
            reparsed.get("trailingBytes") == 0
            and reparsed.get("puzzleFile") == candidate.solution.get("puzzleFile")
            and write_solution_bytes(reparsed) == path.read_bytes()
        )
        oracle = run_omsim(
            omsim,
            puzzle_path,
            path,
            timeout,
            output_intervals=True,
        )
        oracle["knownDivergence"] = bool(
            oracle.get("valid") and not candidate.local_validation.get("complete")
        )
        metrics = deepcopy(oracle.get("metrics") or {})
        metrics["rate"] = oracle.get("rate")
        metrics.update(_derived_values(metrics))
        records.append({
            **candidate.to_dict(),
            "localValidation": _local_validation_summary(candidate.local_validation),
            "solutionPath": str(path),
            "solutionSha256": _fingerprint(path),
            "binaryRoundTripClean": round_trip_clean,
            "metrics": metrics,
            "oracleValidation": oracle,
        })

    winners = select_objective_winners(records)
    winner_report: dict[str, dict[str, Any]] = {}
    for objective, record in winners.items():
        architecture_id = str(record["architectureId"])
        destination = final_dir / f"best-{objective}.solution"
        write_solution(candidate_by_id[architecture_id].solution, destination, version=7)
        winner_report[objective] = {
            "architectureId": architecture_id,
            "archetype": record["archetype"],
            "metrics": record["metrics"],
            "objectiveScore": list(objective_key(objective, record["metrics"])),
            "solutionPath": str(destination),
            "solutionSha256": _fingerprint(destination),
        }

    baseline = next(
        (record for record in records if record["architectureId"] == "balanced-sum4-v1"),
        None,
    )
    improvements: dict[str, dict[str, Any]] = {}
    if baseline is not None:
        for objective in OBJECTIVES:
            if objective not in winner_report:
                continue
            before = _primary_value(objective, baseline["metrics"])
            after = _primary_value(objective, winner_report[objective]["metrics"])
            improvements[objective] = {
                "baseline": before,
                "winner": after,
                "delta": None if before is None or after is None else after - before,
                "improved": before is not None and after is not None and after < before,
            }

    valid_records = [record for record in records if record["oracleValidation"].get("valid")]
    distinct = len({record["solutionSha256"] for record in records})
    core_objectives = ("cost", "area", "cycles", "rate", "instructions")
    ready = (
        len(valid_records) == len(records)
        and distinct >= 4
        and set(winners) == set(OBJECTIVES)
        and all(improvements.get(objective, {}).get("improved") for objective in core_objectives)
    )
    report = {
        "schemaVersion": "0.1.0",
        "status": "ready" if ready else "incomplete",
        "puzzlePath": str(puzzle_path),
        "puzzleName": puzzle.get("name"),
        "strategy": "objective-architecture-portfolio-v1",
        "summary": {
            "candidateCount": len(records),
            "oracleValidCandidateCount": len(valid_records),
            "distinctCandidateCount": distinct,
            "objectiveCount": len(winners),
            "localCompleteCandidateCount": sum(
                bool(record["localValidation"].get("complete")) for record in records
            ),
        },
        "candidates": records,
        "winners": winner_report,
        "improvements": improvements,
        "readyForGameTest": ready,
    }
    json_path = output_dir / "objective-portfolio-report.json"
    text_path = output_dir / "OBJECTIVE_PORTFOLIO_REPORT.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text_path.write_text(_text_report(report), encoding="utf-8")
    return {**report, "reportPath": str(json_path), "textReportPath": str(text_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate, OMSim-score, and select independent objective architectures."
    )
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--omsim", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    binary = args.omsim or (Path(found) if (found := shutil.which("omsim")) else None)
    if binary is None:
        parser.error("OMSim is required for authoritative objective selection; pass --omsim")
    report = solve_objective_portfolio(
        args.puzzle,
        args.output_dir,
        omsim=binary,
        timeout=args.timeout,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["readyForGameTest"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
