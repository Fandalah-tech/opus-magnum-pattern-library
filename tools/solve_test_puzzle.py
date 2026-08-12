from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver import GeneratedSolutionError, UnsupportedPuzzleError, solve_puzzle, validate_generated_solution
from tools.omsim_adapter.validate import run_omsim


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def solve_test_puzzle(puzzle_path: Path, output_dir: Path, *, omsim: Path | None = None) -> dict:
    puzzle = parse_puzzle(puzzle_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = puzzle_path.stem
    report_path = output_dir / f"{stem}-solver-report.json"
    solution_path = output_dir / f"{stem}-auto.solution"

    try:
        result = solve_puzzle(puzzle)
    except (UnsupportedPuzzleError, GeneratedSolutionError) as error:
        report = {
            "status": "unsupported" if isinstance(error, UnsupportedPuzzleError) else "generation-failed",
            "puzzlePath": str(puzzle_path),
            "puzzleName": puzzle.get("name"),
            "message": str(error),
            "readyForGameTest": False,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return {**report, "reportPath": str(report_path)}

    write_solution(result.solution, solution_path, version=7)
    parsed = parse_solution(solution_path)
    round_trip = validate_generated_solution(puzzle, parsed)
    binary_clean = parsed.get("trailingBytes") == 0 and parsed.get("puzzleFile") == result.solution.get("puzzleFile")

    binary = omsim or (Path(found) if (found := shutil.which("omsim")) else None)
    oracle = None
    if binary is not None:
        oracle = run_omsim(binary, puzzle_path, solution_path, 30)

    oracle_valid = bool(oracle and oracle.get("status") == "valid")
    local_ready = bool(result.validation.get("complete") and round_trip.get("complete") and binary_clean)
    report = {
        "status": "ready" if local_ready and (oracle is None or oracle_valid) else "validation-failed",
        "puzzlePath": str(puzzle_path),
        "puzzleName": result.puzzle_name,
        "strategy": result.strategy,
        "solutionPath": str(solution_path),
        "solutionSha256": _sha256(solution_path),
        "binaryRoundTripClean": binary_clean,
        "inMemoryValidation": result.validation,
        "roundTripValidation": round_trip,
        "omsimValidation": oracle or {"status": "unavailable", "message": "omsim executable not present"},
        "readyForGameTest": local_ready and (oracle is None or oracle_valid),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {**report, "reportPath": str(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and validate a first autonomous Opus Magnum test solution.")
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/generated"))
    parser.add_argument("--omsim", type=Path)
    args = parser.parse_args()
    report = solve_test_puzzle(args.puzzle, args.output_dir, omsim=args.omsim)
    print(json.dumps(report, indent=2))
    return 0 if report.get("readyForGameTest") else 2


if __name__ == "__main__":
    sys.exit(main())
