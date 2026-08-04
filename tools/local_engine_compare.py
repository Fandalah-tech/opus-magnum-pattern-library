from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline, build_replay_trace
from packages.opus_engine import Simulator, compare_replays
from packages.opus_parser import parse_puzzle, parse_solution


def compare_pair_locally(puzzle_path: Path, solution_path: Path) -> dict[str, Any]:
    """Compare legacy replay and opus_engine using the checked-out source tree."""
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(solution_path)
    timeline = build_program_timeline(solution)
    legacy = build_replay_trace(puzzle, solution, timeline)
    simulator = Simulator.from_models(puzzle, solution)

    try:
        engine = simulator.run_timeline(timeline)
    except Exception as exc:
        return {
            "schemaVersion": "0.2.0",
            "status": "engine-error",
            "errorType": type(exc).__name__,
            "message": str(exc),
            "completedFrameCount": len(simulator.frames),
        }

    return compare_replays(legacy, engine)
