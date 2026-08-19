from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_parser import parse_puzzle, parse_solution
from packages.opus_solver import build_manufacturing_plan
from packages.opus_solver.portfolio_learning import (
    bounded_worker_count,
    learn_objective_blueprint_portfolio,
)
from tools.omsim_adapter.validate import run_omsim


def _puzzle_file_id(puzzle_path: Path) -> str:
    return re.sub(r" \(\d+\)$", "", puzzle_path.stem)


def _scan_solution(
    path: Path,
    *,
    puzzle_path: Path,
    omsim: Path,
    timeout: int,
    solution_root: Path,
) -> dict[str, Any]:
    solution = parse_solution(path)
    oracle = run_omsim(
        omsim,
        puzzle_path,
        path,
        timeout,
        output_intervals=True,
    )
    metrics = dict(oracle.get("metrics") or {})
    metrics["rate"] = oracle.get("rate")
    return {
        "valid": bool(oracle.get("valid")),
        "solution": solution,
        "metrics": metrics,
        "sourceName": path.name,
        "sourcePath": path.relative_to(solution_root).as_posix(),
        "provenance": {
            "kind": "external-corpus-derived",
            "sourceName": path.name,
            "sourcePath": path.relative_to(solution_root).as_posix(),
            "originalSha256": (solution.get("source") or {}).get("sha256"),
        },
        "oracleValidation": oracle,
    }


def _text_report(report: dict[str, Any]) -> str:
    lines = [
        "OBJECTIVE PORTFOLIO LEARNING REPORT",
        "===================================",
        "",
        f"Puzzle: {report['puzzleName']}",
        f"Strategy: {report['puzzleStrategy']}",
        f"Corpus solutions: {report['summary']['matchingSolutionCount']}",
        f"OMSim-valid: {report['summary']['validSolutionCount']}",
        f"Workers: {report['summary']['workerCount']}",
        f"Learned architectures: {report['summary']['learnedArchitectureCount']}",
        "",
        "Objective winners",
        "-----------------",
    ]
    for blueprint in report["winners"]:
        metrics = blueprint["metrics"]
        lines.append(
            f"{','.join(blueprint['objectives']):18} {blueprint['architectureId']:38} "
            f"cost={metrics.get('cost')} cycles={metrics.get('cycles')} "
            f"area={metrics.get('area')} instructions={metrics.get('instructions')} "
            f"rate={metrics.get('rate')}"
        )
    lines.extend((
        "",
        "The raw external corpus is not copied into the repository. The learned",
        "registry contains only the distinct winning topologies, provenance and",
        "authoritative OMSim metrics.",
        "",
    ))
    return "\n".join(lines)


def learn_from_solution_root(
    puzzle_path: Path,
    solution_root: Path,
    output_path: Path,
    *,
    omsim: Path,
    report_dir: Path,
    jobs: int | None = None,
    timeout: int = 60,
    source_url: str | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    plan = build_manufacturing_plan(puzzle)
    if not plan.supported:
        raise ValueError(plan.reason or "Puzzle is not supported by the manufacturing planner")

    expected_id = _puzzle_file_id(puzzle_path)
    matching: list[Path] = []
    rejected = 0
    for path in sorted(solution_root.rglob("*.solution")):
        solution = parse_solution(path)
        if solution.get("puzzleFile") == expected_id:
            matching.append(path)
        else:
            rejected += 1
    if not matching:
        raise ValueError(f"No solutions associated with puzzle file {expected_id!r}")

    worker_count = bounded_worker_count(jobs, cpu_count=os.cpu_count())
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _scan_solution,
                path,
                puzzle_path=puzzle_path,
                omsim=omsim,
                timeout=timeout,
                solution_root=solution_root,
            ): path
            for path in matching
        }
        for processed, future in enumerate(as_completed(futures), start=1):
            records.append(future.result())
            if processed % 25 == 0 or processed == len(futures):
                print(json.dumps({
                    "processed": processed,
                    "total": len(futures),
                    "valid": sum(bool(record["valid"]) for record in records),
                }), flush=True)

    portfolio = learn_objective_blueprint_portfolio(
        puzzle,
        records,
        puzzle_strategy=plan.strategy,
        source={
            "kind": "external-reference-only",
            "root": str(solution_root),
            "url": source_url,
        },
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(portfolio, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    winners = [
        {
            "architectureId": blueprint["id"],
            "archetype": blueprint["archetype"],
            "objectives": blueprint["objectives"],
            "metrics": blueprint["referenceMetrics"],
            "provenance": blueprint["provenance"],
        }
        for blueprint in portfolio["blueprints"]
    ]
    report = {
        "schemaVersion": "0.1.0",
        "status": "ready",
        "puzzlePath": str(puzzle_path),
        "puzzleName": puzzle.get("name"),
        "puzzleStrategy": plan.strategy,
        "puzzleFeatureFingerprint": portfolio["puzzleFeatureFingerprint"],
        "blueprintPath": str(output_path),
        "summary": {
            "matchingSolutionCount": len(matching),
            "rejectedSolutionCount": rejected,
            "validSolutionCount": sum(bool(record["valid"]) for record in records),
            "workerCount": worker_count,
            "learnedArchitectureCount": len(portfolio["blueprints"]),
        },
        "baselineArchitectureId": portfolio["baselineArchitectureId"],
        "winners": winners,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "portfolio-learning-report.json"
    text_path = report_dir / "PORTFOLIO_LEARNING_REPORT.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text_path.write_text(_text_report(report), encoding="utf-8")
    return {**report, "reportPath": str(json_path), "textReportPath": str(text_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Learn an objective-specific architecture registry from an external solution corpus."
    )
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("solution_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--source-url")
    args = parser.parse_args()
    report = learn_from_solution_root(
        args.puzzle,
        args.solution_root,
        args.output,
        omsim=args.omsim,
        report_dir=args.report_dir,
        jobs=args.jobs,
        timeout=args.timeout,
        source_url=args.source_url,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
