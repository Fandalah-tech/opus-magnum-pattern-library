from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from packages.opus_engine import Simulator
from packages.opus_parser import parse_puzzle, parse_solution, triplex_bond_channels

from .timeline import build_program_timeline

STANDARD_PRODUCT_TARGET = 6
REPEATING_PRODUCT_TARGET = 3
MAX_AUDIT_WORKERS = 10


def bounded_audit_workers(requested: int | None) -> int:
    return min(MAX_AUDIT_WORKERS, max(1, int(requested or MAX_AUDIT_WORKERS)))


def has_triplex_product(puzzle: dict[str, Any]) -> bool:
    return any(
        triplex_bond_channels(bond)
        for molecule in puzzle.get("products", [])
        for bond in molecule.get("bonds", [])
    )


def _atom_origin(atom_id: str) -> tuple[str | None, str | None]:
    match = re.match(r"(.+?)-spawn-(\d+)-atom-\d+$", atom_id)
    if match is None:
        return None, None
    return match.group(1), match.group(2)


def classify_simulation_error(message: str) -> str:
    headline = str(message or "").split(";", 1)[0]
    atom_collision = re.match(
        r"Atom (.+?) collides with stationary atom (.+?) at ",
        headline,
    )
    if atom_collision:
        moving_input, moving_generation = _atom_origin(atom_collision.group(1))
        fixed_input, fixed_generation = _atom_origin(atom_collision.group(2))
        if moving_input and moving_input == fixed_input:
            if moving_generation == fixed_generation:
                return "atom-collision/same-molecule"
            return "atom-collision/same-input-different-spawn"
        return "atom-collision/different-sources"
    if headline.startswith("Motion collision at "):
        return "atom-collision/simultaneous-motion"
    if headline.startswith("Collision") or "collision during motion" in headline.lower():
        return "atom-collision/continuous-motion"
    if headline.startswith("Conflicting motions for atom "):
        return "motion/conflicting"
    if headline.startswith("Incompatible shared motions for atom "):
        return "motion/incompatible-shared"
    if headline.startswith("Conduit output collision at "):
        return "conduit/output-collision"
    if "track" in headline.lower():
        return "motion/track"
    return "simulation/other"


def _last_simulation_error(replay: dict[str, Any]) -> dict[str, Any] | None:
    for frame in reversed(replay.get("frames", [])):
        for event in reversed(frame.get("events", [])):
            if event.get("kind") == "simulation-error":
                return {
                    "cycle": event.get("cycle", frame.get("cycle")),
                    "message": str(event.get("message") or "Simulation terminated with an unspecified error"),
                }
    return None


def audit_engine_solution(
    puzzle_path: str | Path,
    solution_path: str | Path,
    *,
    solution_root: str | Path | None = None,
) -> dict[str, Any]:
    puzzle_path = Path(puzzle_path)
    solution_path = Path(solution_path)
    root = Path(solution_root) if solution_root is not None else solution_path.parent
    relative_path = str(solution_path.relative_to(root)) if solution_path.is_relative_to(root) else str(solution_path)
    record: dict[str, Any] = {
        "solutionPath": relative_path,
        "puzzlePath": str(puzzle_path),
        "partTypes": [],
    }
    try:
        puzzle = parse_puzzle(puzzle_path)
        solution = parse_solution(solution_path)
        record["puzzleId"] = str(solution.get("puzzleFile") or puzzle_path.stem)
        part_types = sorted({str(part.get("type") or "") for part in solution.get("parts", [])})
        record["partTypes"] = part_types
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
        delivered = {str(key): int(value) for key, value in simulator.delivered_products.items()}
        repeating_complete = {
            output_id: simulator.repeating_product_complete(output_id, REPEATING_PRODUCT_TARGET)
            for output_id in repeating_outputs
        }
        targets_complete = bool(standard_outputs or repeating_outputs) and (
            all(delivered.get(output_id, 0) >= STANDARD_PRODUCT_TARGET for output_id in standard_outputs)
            and all(repeating_complete.values())
        )
        terminated = bool(replay.get("summary", {}).get("terminatedWithError"))
        error = _last_simulation_error(replay)
        record.update({
            "requestedCycles": len(timeline.get("cycles", [])),
            "completedCycles": int(replay.get("summary", {}).get("completedCycles") or 0),
            "deliveredProducts": delivered,
            "standardOutputs": standard_outputs,
            "repeatingOutputs": repeating_outputs,
            "repeatingComplete": repeating_complete,
            "terminatedAfterCompletion": bool(targets_complete and terminated),
        })

        if targets_complete:
            record["status"] = "engine-complete"
            if error:
                record["postCompletionError"] = error
        elif terminated:
            message = error["message"] if error else "Simulation terminated with an unspecified error"
            record.update({
                "status": "engine-error",
                "errorCycle": error.get("cycle") if error else None,
                "errorCategory": classify_simulation_error(message),
                "message": message,
            })
        else:
            record.update({
                "status": "engine-incomplete",
                "missingStandard": {
                    output_id: {
                        "delivered": delivered.get(output_id, 0),
                        "required": STANDARD_PRODUCT_TARGET,
                    }
                    for output_id in standard_outputs
                    if delivered.get(output_id, 0) < STANDARD_PRODUCT_TARGET
                },
                "missingRepeating": [
                    output_id for output_id, complete in repeating_complete.items() if not complete
                ],
            })
    except Exception as exc:
        record.update({
            "status": "exception",
            "errorCategory": "audit/exception",
            "errorType": type(exc).__name__,
            "message": str(exc),
        })
    return record


def summarize_engine_audit(results: Iterable[dict[str, Any]], *, workers: int) -> dict[str, Any]:
    records = list(results)
    statuses = Counter(str(record.get("status") or "unknown") for record in records)
    failures = Counter(
        str(record.get("errorCategory") or "unknown")
        for record in records
        if record.get("status") in {"engine-error", "exception"}
    )
    by_puzzle: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        by_puzzle[str(record.get("puzzleId") or "<unknown>")][str(record.get("status") or "unknown")] += 1
    return {
        "solutionCount": len(records),
        "engineComplete": statuses["engine-complete"],
        "engineError": statuses["engine-error"],
        "engineIncomplete": statuses["engine-incomplete"],
        "exceptionCount": statuses["exception"],
        "terminatedAfterCompletion": sum(bool(record.get("terminatedAfterCompletion")) for record in records),
        "workerCount": bounded_audit_workers(workers),
        "failureCategories": dict(sorted(failures.items(), key=lambda item: (-item[1], item[0]))),
        "puzzles": {
            puzzle_id: dict(sorted(counts.items()))
            for puzzle_id, counts in sorted(by_puzzle.items())
        },
    }


def render_engine_audit_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "TRIPLEX ENGINE CORPUS AUDIT",
        "===========================",
        "",
        f"Status: {'VALIDATED' if not summary['exceptionCount'] else 'AUDIT EXCEPTIONS'}",
        "",
        "Coverage",
        "--------",
        f"Triplex product puzzles: {report['triplexPuzzleCount']}",
        f"Associated solutions: {summary['solutionCount']}",
        f"Audit workers: {summary['workerCount']} (hard maximum {MAX_AUDIT_WORKERS})",
        "",
        "Engine outcomes",
        "---------------",
        f"Complete: {summary['engineComplete']}",
        f"Error: {summary['engineError']}",
        f"Incomplete: {summary['engineIncomplete']}",
        f"Audit exceptions: {summary['exceptionCount']}",
        f"Completed before a later trace error: {summary['terminatedAfterCompletion']}",
        "",
        "Remaining failure categories",
        "----------------------------",
    ]
    if summary["failureCategories"]:
        for category, count in summary["failureCategories"].items():
            lines.append(f"{count:4}  {category}")
    else:
        lines.append("None")
    lines.extend((
        "",
        "Method",
        "------",
        "Every solution whose puzzle has a triplex product is parsed and replayed",
        "by opus_engine. Standard outputs require six deliveries; repeating outputs",
        "require three repetitions. A solution that reaches its output target before",
        "a later trace error remains classified complete and is flagged separately.",
        "",
    ))
    return "\n".join(lines)
