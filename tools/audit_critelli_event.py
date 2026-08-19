from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from packages.opus_analysis import bounded_audit_workers, build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_parser import parse_puzzle, parse_solution

STANDARD_PRODUCT_TARGET = 6
REPEATING_PRODUCT_TARGET = 3


def _audit_one(item: tuple[str, str, str, str]) -> dict[str, Any]:
    puzzle_path, solution_path, relative_path, puzzle_id = item
    record: dict[str, Any] = {
        "puzzleId": puzzle_id,
        "puzzlePath": puzzle_path,
        "solutionPath": relative_path,
    }
    try:
        puzzle = parse_puzzle(puzzle_path)
        solution = parse_solution(solution_path)
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
        if targets_complete:
            record["status"] = "engine-complete"
        elif replay.get("summary", {}).get("terminatedWithError"):
            last_frame = replay.get("frames", [])[-1] if replay.get("frames") else {}
            error_event = next(
                (event for event in reversed(last_frame.get("events", [])) if event.get("kind") == "simulation-error"),
                {},
            )
            record.update({
                "status": "engine-error",
                "errorType": "SimulationError",
                "message": str(error_event.get("message") or "Simulation terminated with an unspecified error"),
                "completedCycles": replay.get("summary", {}).get("completedCycles"),
            })
        else:
            record.update({
                "status": "engine-incomplete",
                "reason": "products-not-completed",
            })
    except Exception as exc:
        record.update({
            "status": "engine-error",
            "errorType": type(exc).__name__,
            "message": str(exc),
        })
    return record


def audit_critelli_event(root: Path, *, workers: int = 10) -> dict[str, Any]:
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    puzzle_record = index.get("puzzle") or {}
    if not puzzle_record.get("file"):
        raise ValueError("Critelli event index does not contain an imported puzzle file")
    puzzle_path = root / str(puzzle_record["file"])
    solution_root = root / "solutions"
    puzzle_id = str(index.get("puzzleName") or puzzle_path.stem)

    items: list[tuple[str, str, str, str]] = []
    for record in index.get("solutions", []):
        if not record.get("file"):
            continue
        source = root / str(record["file"])
        try:
            relative = source.relative_to(solution_root).as_posix()
        except ValueError:
            relative = source.name
        items.append((str(puzzle_path), str(source), relative, puzzle_id))

    worker_count = bounded_audit_workers(workers)
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(_audit_one, items))

    statuses = Counter(str(record.get("status") or "unknown") for record in results)
    summary = {
        "solutionCount": len(results),
        "engineComplete": statuses["engine-complete"],
        "engineIncomplete": statuses["engine-incomplete"],
        "engineErrors": statuses["engine-error"],
        "workerCount": worker_count,
    }
    return {
        "schemaVersion": "0.1.0",
        "source": "critelli-event",
        "eventId": index.get("eventId"),
        "puzzleId": puzzle_id,
        "puzzlePath": str(puzzle_path),
        "solutionRoot": str(solution_root),
        "summary": summary,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit every downloaded solution for one Critelli event against opus_engine.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = audit_critelli_event(args.root, workers=args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 1 if args.strict and (report["summary"]["engineIncomplete"] or report["summary"]["engineErrors"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
