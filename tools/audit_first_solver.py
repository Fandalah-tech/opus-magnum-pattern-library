from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver import solve_puzzle, validate_generated_solution


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and verify the first autonomous campaign solution.")
    parser.add_argument("--root", type=Path, default=Path(".datasets/campaign-corpus"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/generated"))
    args = parser.parse_args()

    puzzle_paths = list(args.root.glob("puzzles/**/P007.puzzle"))
    if len(puzzle_paths) != 1:
        raise SystemExit(f"Expected one P007 puzzle, found {len(puzzle_paths)}")
    puzzle_path = puzzle_paths[0]
    puzzle = parse_puzzle(puzzle_path)

    result = solve_puzzle(puzzle)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    solution_path = args.output_dir / "P007-auto.solution"
    report_path = args.output_dir / "P007-auto.json"
    write_solution(result.solution, solution_path)

    round_tripped = parse_solution(solution_path)
    round_trip_validation = validate_generated_solution(puzzle, round_tripped)
    reference_paths = sorted((args.root / "solutions" / "zlbb" / "P007").glob("*.solution"))
    generated_sha = _sha256(solution_path)
    reference_shas = {_sha256(path) for path in reference_paths}

    report = {
        **result.to_dict(include_solution=True),
        "puzzlePath": str(puzzle_path),
        "solutionPath": str(solution_path),
        "solutionSha256": generated_sha,
        "referenceSolutionCount": len(reference_paths),
        "matchesReferenceSolution": generated_sha in reference_shas,
        "roundTripValidation": round_trip_validation,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not result.validation.get("complete"):
        raise SystemExit("Generated in-memory solution did not complete P007")
    if not round_trip_validation.get("complete"):
        raise SystemExit("Serialized and reparsed solution did not complete P007")
    if generated_sha in reference_shas:
        raise SystemExit("Generated solution unexpectedly matches a downloaded reference solution")

    print(json.dumps({
        "puzzle": result.puzzle_name,
        "strategy": result.strategy,
        "solution": str(solution_path),
        "report": str(report_path),
        "validation": round_trip_validation,
        "matchesReferenceSolution": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
