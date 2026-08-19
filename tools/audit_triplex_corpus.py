from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_analysis.engine_audit import (
    audit_engine_solution,
    bounded_audit_workers,
    has_triplex_product,
    render_engine_audit_report,
    summarize_engine_audit,
)
from packages.opus_parser import parse_puzzle, parse_solution


def _audit_pair(pair: tuple[str, str, str]) -> dict[str, Any]:
    puzzle_path, solution_path, solution_root = pair
    return audit_engine_solution(puzzle_path, solution_path, solution_root=solution_root)


def audit_triplex_corpus(
    puzzle_root: Path,
    solution_root: Path,
    *,
    workers: int = 10,
) -> dict[str, Any]:
    puzzle_paths: dict[str, Path] = {}
    parse_failures: list[dict[str, str]] = []
    for path in sorted(puzzle_root.rglob("*.puzzle")):
        try:
            puzzle = parse_puzzle(path)
        except Exception as exc:
            parse_failures.append({"path": str(path), "errorType": type(exc).__name__, "message": str(exc)})
            continue
        if has_triplex_product(puzzle):
            puzzle_paths.setdefault(path.stem, path)

    pairs: list[tuple[str, str, str]] = []
    solution_parse_failures: list[dict[str, str]] = []
    for path in sorted(solution_root.rglob("*.solution")):
        try:
            solution = parse_solution(path)
        except Exception as exc:
            solution_parse_failures.append({"path": str(path), "errorType": type(exc).__name__, "message": str(exc)})
            continue
        puzzle_path = puzzle_paths.get(str(solution.get("puzzleFile") or ""))
        if puzzle_path is not None:
            pairs.append((str(puzzle_path), str(path), str(solution_root)))

    worker_count = bounded_audit_workers(workers)
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(_audit_pair, pairs))
    results.sort(key=lambda record: (str(record.get("puzzleId") or ""), str(record.get("solutionPath") or "")))
    summary = summarize_engine_audit(results, workers=worker_count)
    summary["puzzleParseFailureCount"] = len(parse_failures)
    summary["solutionParseFailureCount"] = len(solution_parse_failures)
    return {
        "schemaVersion": "0.1.0",
        "analysis": "triplex-engine-corpus-audit",
        "puzzleRoot": str(puzzle_root),
        "solutionRoot": str(solution_root),
        "triplexPuzzleCount": len(puzzle_paths),
        "summary": summary,
        "results": results,
        "puzzleParseFailures": parse_failures,
        "solutionParseFailures": solution_parse_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit every solution associated with a triplex-product puzzle.")
    parser.add_argument("--puzzle-root", type=Path, required=True)
    parser.add_argument("--solution-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    report = audit_triplex_corpus(args.puzzle_root, args.solution_root, workers=args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.report.write_text(render_engine_audit_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 1 if report["summary"]["exceptionCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
