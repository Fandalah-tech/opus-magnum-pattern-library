from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline, build_replay_trace
from packages.opus_engine import Simulator, compare_replays
from packages.opus_parser import parse_puzzle, parse_solution


LEGACY_UNSUPPORTED_GLYPHS = {
    "bonder",
    "unbonder",
    "bonder-speed",
    "glyph-calcification",
    "glyph-equilibrium",
    "glyph-projection",
    "glyph-purification",
    "glyph-duplication",
    "glyph-life-and-death",
    "glyph-bonder-prisma",
    "glyph-unbonder-prisma",
}


def _unsupported_legacy_parts(solution: dict[str, Any]) -> list[str]:
    return sorted({
        str(part.get("type") or "")
        for part in solution.get("parts", [])
        if str(part.get("type") or "") in LEGACY_UNSUPPORTED_GLYPHS
    })


def compare_pair_locally(puzzle_path: Path, solution_path: Path) -> dict[str, Any]:
    """Compare legacy replay and opus_engine using the checked-out source tree.

    The legacy replay intentionally does not simulate chemistry glyphs. A world
    state comparison after one of those glyphs can therefore only measure a
    reference limitation, not engine fidelity. Such cases are reported as a
    reference gap instead of a false engine divergence.
    """
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(solution_path)
    timeline = build_program_timeline(solution)
    legacy = build_replay_trace(puzzle, solution, timeline)
    simulator = Simulator.from_models(puzzle, solution)

    try:
        engine = simulator.run_timeline(timeline)
    except Exception as exc:
        return {
            "schemaVersion": "0.3.0",
            "status": "engine-error",
            "errorType": type(exc).__name__,
            "message": str(exc),
            "completedFrameCount": len(simulator.frames),
        }

    comparison = compare_replays(legacy, engine)
    unsupported = _unsupported_legacy_parts(solution)
    if comparison.get("status") == "diverged" and unsupported:
        return {
            "schemaVersion": "0.3.0",
            "status": "reference-gap",
            "reason": "legacy-replay-does-not-simulate-glyph-effects",
            "unsupportedLegacyParts": unsupported,
            "firstObservedDifference": comparison.get("firstDivergence"),
            "engineSummary": engine.get("summary"),
            "legacyCapabilities": legacy.get("capabilities"),
        }

    return comparison
