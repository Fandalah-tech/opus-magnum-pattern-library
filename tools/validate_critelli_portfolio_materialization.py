from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from packages.opus_analysis import canonical_solution_hash
from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.objective_portfolio import _materialize_blueprint
from packages.opus_solver.solver import validate_generated_solution


def _puzzle_file_id(puzzle: dict[str, Any], puzzle_path: Path) -> str:
    source_name = str((puzzle.get("source") or {}).get("name") or puzzle_path.name)
    return re.sub(r" \(\d+\)$", "", Path(source_name).stem)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_portfolio_materialization(
    puzzle_path: Path,
    portfolio_path: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    puzzle_file = _puzzle_file_id(puzzle, puzzle_path)
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    by_id = {str(item.get("id")): item for item in portfolio.get("blueprints", [])}
    winner_ids = dict(portfolio.get("winnerArchitectureIds") or {})
    results = []

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    for variant_index, objective in enumerate(("cga", "bca")):
        architecture_id = str(winner_ids.get(objective) or "")
        blueprint = by_id.get(architecture_id)
        if blueprint is None:
            results.append({
                "objective": objective,
                "architectureId": architecture_id,
                "complete": False,
                "error": "winner-blueprint-not-found",
            })
            continue
        candidate = _materialize_blueprint(
            puzzle,
            blueprint,
            variant_index=variant_index,
        )
        candidate["name"] = f"Learned Critelli {objective.upper()} winner"
        try:
            validation = validate_generated_solution(puzzle, candidate)
            complete = bool(validation.get("complete"))
            error = None
        except Exception as exc:
            validation = None
            complete = False
            error = f"{type(exc).__name__}: {exc}"

        output_file = None
        output_sha256 = None
        if output_dir is not None:
            output_file = output_dir / f"{puzzle_file}-{objective}-learned.solution"
            write_solution(candidate, output_file)
            output_sha256 = _sha256(output_file)

        results.append({
            "objective": objective,
            "architectureId": architecture_id,
            "referenceMetrics": blueprint.get("referenceMetrics", {}).get(objective),
            "canonicalStructuralHash": canonical_solution_hash(candidate, normalize_time=False),
            "canonicalMechanismHash": canonical_solution_hash(candidate, normalize_time=True),
            "provenance": blueprint.get("provenance", {}),
            "complete": complete,
            "error": error,
            "validation": validation,
            "outputFile": str(output_file) if output_file is not None else None,
            "outputSha256": output_sha256,
        })

    return {
        "schemaVersion": "0.2.0",
        "puzzle": str(puzzle.get("name") or puzzle_path.stem),
        "puzzleFile": puzzle_file,
        "puzzlePath": str(puzzle_path),
        "portfolio": str(portfolio_path),
        "portfolioSource": portfolio.get("source"),
        "summary": {
            "winnerCount": len(results),
            "completeCount": sum(bool(item.get("complete")) for item in results),
            "allComplete": bool(results) and all(bool(item.get("complete")) for item in results),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild learned Critelli winner blueprints and validate them without "
            "original solution bytes."
        )
    )
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--portfolio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = validate_portfolio_materialization(
        args.puzzle,
        args.portfolio,
        output_dir=args.solution_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if args.strict and not report["summary"]["allComplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
