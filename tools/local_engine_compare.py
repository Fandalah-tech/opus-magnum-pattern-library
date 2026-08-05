from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_analysis.chemical_replay import build_chemical_replay_trace
from packages.opus_engine import Simulator, compare_replays
from packages.opus_parser import parse_puzzle, parse_solution


CHEMICAL_ORACLE_SUPPORTED = {
    "bonder",
    "glyph-calcification",
    "glyph-projection",
}

CHEMISTRY_PARTS = {
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


def _unsupported_oracle_parts(solution: dict[str, Any]) -> list[str]:
    return sorted({
        str(part.get("type") or "")
        for part in solution.get("parts", [])
        if str(part.get("type") or "") in CHEMISTRY_PARTS
        and str(part.get("type") or "") not in CHEMICAL_ORACLE_SUPPORTED
    })


def _oracle_solution(solution: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(solution)
    for part in normalized.get("parts", []):
        if part.get("type") != "track":
            continue
        origin = part.get("position") or [0, 0]
        part["trackHexes"] = [
            [int(origin[0]) + int(cell[0]), int(origin[1]) + int(cell[1])]
            for cell in (part.get("trackHexes") or [])
        ]
    return normalized


def _track_diagnostics(solution: dict[str, Any]) -> dict[str, Any]:
    return {
        "tracks": [
            {
                "partId": part.get("id"),
                "position": part.get("position"),
                "relativeTrackHexes": part.get("trackHexes") or [],
                "absoluteTrackHexes": [
                    [
                        int((part.get("position") or [0, 0])[0]) + int(cell[0]),
                        int((part.get("position") or [0, 0])[1]) + int(cell[1]),
                    ]
                    for cell in (part.get("trackHexes") or [])
                ],
            }
            for part in solution.get("parts", [])
            if part.get("type") == "track"
        ],
        "arms": [
            {
                "partId": part.get("id"),
                "type": part.get("type"),
                "position": part.get("position"),
                "rotation": part.get("rotation"),
                "length": part.get("length"),
                "program": part.get("program") or [],
            }
            for part in solution.get("parts", [])
            if str(part.get("type") or "").startswith("arm")
            or part.get("type") in {"piston", "baron"}
        ],
    }


def compare_pair_locally(puzzle_path: Path, solution_path: Path) -> dict[str, Any]:
    """Compare opus_engine against an independently implemented chemical replay."""
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(solution_path)
    timeline = build_program_timeline(solution)
    unsupported = _unsupported_oracle_parts(solution)
    if unsupported:
        return {
            "schemaVersion": "0.4.0",
            "status": "reference-gap",
            "reason": "chemical-oracle-does-not-simulate-required-parts",
            "unsupportedLegacyParts": unsupported,
        }

    oracle = build_chemical_replay_trace(puzzle, _oracle_solution(solution), timeline)
    simulator = Simulator.from_models(puzzle, solution)
    try:
        engine = simulator.run_timeline(timeline)
    except Exception as exc:
        return {
            "schemaVersion": "0.4.0",
            "status": "engine-error",
            "errorType": type(exc).__name__,
            "message": str(exc),
            "completedFrameCount": len(simulator.frames),
        }

    comparison = compare_replays(oracle, engine)
    comparison["oracle"] = {
        "traceType": oracle.get("traceType"),
        "capabilities": oracle.get("capabilities"),
    }
    if comparison.get("status") == "diverged":
        divergence = comparison.get("firstDivergence") or {}
        categories = divergence.setdefault("categories", {})
        categories["trackDiagnostics"] = _track_diagnostics(solution)
    return comparison
