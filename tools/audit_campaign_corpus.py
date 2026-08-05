from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_parser import parse_puzzle, parse_solution

STANDARD_PRODUCT_TARGET = 6
REPEATING_PRODUCT_TARGET = 3


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
    incomplete_by_part: defaultdict[str, int] = defaultdict(int)
    errors_by_part: defaultdict[str, int] = defaultdict(int)

    for item in index.get("solutions", []):
        if not item.get("file"):
            continue
        solution_path = args.root / item["file"]
        record: dict[str, Any] = {
            "puzzleId": item.get("puzzleId"),
            "category": item.get("category"),
            "solution": item.get("file"),
            "partTypes": [],
        }
        try:
            solution = parse_solution(solution_path)
            puzzle_key = str(solution.get("puzzleFile") or item.get("puzzleId") or "")
            puzzle_path = puzzle_paths.get(puzzle_key)
            if puzzle_path is None:
                raise FileNotFoundError(f"No puzzle found for {puzzle_key}")
            puzzle = parse_puzzle(puzzle_path)
            part_types = sorted({str(part.get("type") or "") for part in solution.get("parts", [])})
            record["partTypes"] = part_types
            for part_type in part_types:
                part_usage[part_type] += 1

            standard_outputs = [
                str(part.get("id"))
                for part in solution.get("parts", [])
                if part.get("type") == "out-std"
            ]
            repeating_outputs = [
                str(part.get("id"))
                for part in solution.get("parts", [])
                if part.get("type") == "out-rep"
            ]

            timeline = build_program_timeline(solution)
            simulator = Simulator.from_models(puzzle, solution)
            replay = simulator.run_timeline(timeline)
            delivered = dict(simulator.delivered_products)
            repeating_complete = {
                output_id: simulator.repeating_product_complete(output_id, REPEATING_PRODUCT_TARGET)
                for output_id in repeating_outputs
            }
            record.update({
                "frames": len(simulator.frames),
                "requestedCycles": len(timeline.get("cycles", [])),
                "deliveredProducts": delivered,
                "standardOutputs": standard_outputs,
                "repeatingOutputs": repeating_outputs,
                "repeatingComplete": repeating_complete,
            })

            targets_complete = (
                all(int(delivered.get(output_id, 0)) >= STANDARD_PRODUCT_TARGET for output_id in standard_outputs)
                and all(repeating_complete.values())
            )
            # The game ends as soon as every target has been delivered. Tape
            # instructions after that point are unreachable and cannot invalidate
            # an already completed solution.
            if targets_complete:
                record["status"] = "engine-complete"
            elif replay.get("summary", {}).get("terminatedWithError"):
                last_frame = replay.get("frames", [])[-1] if replay.get("frames") else {}
                error_event = next(
                    (
                        event for event in reversed(last_frame.get("events", []))
                        if event.get("kind") == "simulation-error"
                    ),
                    {},
                )
                message = str(error_event.get("message") or "Simulation terminated with an unspecified error")
                record.update({
                    "status": "engine-error",
                    "errorType": "SimulationError",
                    "message": message,
                    "completedCycles": replay.get("summary", {}).get("completedCycles"),
                })
                for part_type in part_types:
                    errors_by_part[part_type] += 1
            else:
                missing_standard = {
                    output_id: {
                        "delivered": int(delivered.get(output_id, 0)),
                        "required": STANDARD_PRODUCT_TARGET,
                    }
                    for output_id in standard_outputs
                    if int(delivered.get(output_id, 0)) < STANDARD_PRODUCT_TARGET
                }
                missing_repeating = [
                    output_id for output_id, complete in repeating_complete.items() if not complete
                ]
                if missing_standard or missing_repeating:
                    record.update({
                        "status": "engine-incomplete",
                        "reason": "products-not-completed",
                        "missingProducts": missing_standard,
                        "missingRepeatingProducts": missing_repeating,
                    })
                    for part_type in part_types:
                        incomplete_by_part[part_type] += 1
                else:
                    record["status"] = "engine-complete"
        except Exception as exc:
            for part_type in record["partTypes"]:
                errors_by_part[part_type] += 1
            record.update({
                "status": "engine-error",
                "errorType": type(exc).__name__,
                "message": str(exc),
            })
        results.append(record)
        print(json.dumps(record), flush=True)

    statuses = Counter(item["status"] for item in results)
    summary = {
        "total": len(results),
        "engineComplete": statuses["engine-complete"],
        "engineIncomplete": statuses["engine-incomplete"],
        "semanticGaps": statuses["semantic-gap"],
        "engineErrors": statuses["engine-error"],
        "partUsage": dict(sorted(part_usage.items())),
        "incompleteByPart": dict(sorted(incomplete_by_part.items())),
        "errorsByPart": dict(sorted(errors_by_part.items())),
    }
    report = {"schemaVersion": "0.4.1", "summary": summary, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 1 if summary["engineErrors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
