from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_parser import parse_puzzle, parse_solution


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit imported campaign solutions against opus_engine.")
    parser.add_argument("--root", type=Path, default=Path(".datasets/campaign-corpus"))
    parser.add_argument("--output", type=Path, default=Path("reports/campaign-corpus-audit.json"))
    args = parser.parse_args()

    index = json.loads((args.root / "index.json").read_text(encoding="utf-8"))
    puzzle_paths = {
        Path(item["localPath"]).stem: args.root / item["localPath"]
        for item in index.get("puzzles", [])
    }

    results: list[dict[str, Any]] = []
    part_usage: Counter[str] = Counter()
    failures_by_part: defaultdict[str, int] = defaultdict(int)

    for item in index.get("solutions", []):
        if not item.get("file"):
            continue
        solution_path = args.root / item["file"]
        record: dict[str, Any] = {
            "puzzleId": item.get("puzzleId"),
            "category": item.get("category"),
            "solution": item.get("file"),
        }
        try:
            solution = parse_solution(solution_path)
            puzzle_key = str(solution.get("puzzleFile") or item.get("puzzleId") or "")
            puzzle_path = puzzle_paths.get(puzzle_key)
            if puzzle_path is None:
                raise FileNotFoundError(f"No puzzle found for {puzzle_key}")
            puzzle = parse_puzzle(puzzle_path)
            part_types = sorted({str(part.get("type") or "") for part in solution.get("parts", [])})
            for part_type in part_types:
                part_usage[part_type] += 1
            timeline = build_program_timeline(solution)
            simulator = Simulator.from_models(puzzle, solution)
            simulator.run_timeline(timeline)
            record.update({
                "status": "simulated",
                "partTypes": part_types,
                "frames": len(simulator.frames),
                "deliveredProducts": dict(simulator.delivered_products),
            })
        except Exception as exc:
            part_types = record.get("partTypes") or []
            for part_type in part_types:
                failures_by_part[part_type] += 1
            record.update({
                "status": "engine-error",
                "errorType": type(exc).__name__,
                "message": str(exc),
                "partTypes": part_types,
            })
        results.append(record)
        print(json.dumps(record), flush=True)

    summary = {
        "total": len(results),
        "simulated": sum(1 for item in results if item["status"] == "simulated"),
        "engineErrors": sum(1 for item in results if item["status"] == "engine-error"),
        "partUsage": dict(sorted(part_usage.items())),
        "failuresByPart": dict(sorted(failures_by_part.items())),
    }
    report = {"schemaVersion": "0.1.0", "summary": summary, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 1 if summary["engineErrors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
