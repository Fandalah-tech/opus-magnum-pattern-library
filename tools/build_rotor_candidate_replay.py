from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.final_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes
from tools.search_rotor_last_atom_tail import snapshot

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-last-isolated-atom-prefix.solution.b64")
CANDIDATE = Path("reports/rotor-tail-best-candidate.json")
OUTPUT = Path("reports/rotor-tail-best-candidate-replay.json")


def normalize_track_coordinates(simulator: Simulator, solution: dict) -> None:
    """Convert .solution track offsets to the world coordinates used by ArmState.

    The parser stores trackHexes relative to the track part's position. The
    engine's ArmState motion planner consumes world coordinates, so feeding the
    raw offsets makes tracked arms jump toward board origin.
    """
    track = next((part for part in solution.get("parts", []) if part.get("type") == "track"), None)
    if not track:
        return
    origin = tuple(track.get("position") or (0, 0))
    cells = tuple(
        (origin[0] + int(cell[0]), origin[1] + int(cell[1]))
        for cell in (track.get("trackHexes") or [])
    )
    for arm in simulator.arms.values():
        arm.track_cells = cells
        if arm.origin in cells:
            arm.track_index = cells.index(arm.origin)
            arm.base_track_index = arm.track_index


def frame(index: int, segment: str, action: dict, simulator: Simulator, *, source_cycle: int | None = None) -> dict:
    return {
        "index": index,
        "segment": segment,
        "sourceCycle": source_cycle,
        "action": action,
        "state": snapshot(simulator),
    }


def main() -> int:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")))
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    simulator = Simulator.from_models(puzzle, solution)
    normalize_track_coordinates(simulator, solution)

    frames = [frame(0, "prefix", {}, simulator, source_cycle=0)]
    timeline = build_program_timeline(solution).get("cycles", [])
    for row in timeline:
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
            if event.get("instruction")
        }
        simulator.step(instructions)
        frames.append(
            frame(
                len(frames),
                "prefix",
                instructions,
                simulator,
                source_cycle=int(row.get("cycle", simulator.world.cycle)),
            )
        )

    solver_start_index = len(frames) - 1
    solver_start_cycle = simulator.world.cycle
    for action in candidate["result"]["actions"]:
        simulator.step(action)
        frames.append(frame(len(frames), "solver", action, simulator))

    solver_end_index = len(frames) - 1
    payload = {
        "schemaVersion": 4,
        "title": "Van Berlo's Rotor — candidat score 599",
        "isCompleteSolution": False,
        "source": "reports/rotor-tail-best-candidate.json",
        "bestScore": candidate["result"]["bestScore"],
        "renderContext": {
            "puzzle": puzzle,
            "solution": solution,
            "renderer": "OpusScene/OpusSvgRenderer",
        },
        "replayFixes": {
            "trackCoordinates": "world",
            "trackOriginIncludedOnlyIfExplicit": True,
        },
        "segments": [
            {
                "id": "prefix",
                "label": "Préfixe humain",
                "startIndex": 0,
                "endIndex": solver_start_index,
                "startCycle": frames[0]["state"]["cycle"],
                "endCycle": solver_start_cycle,
            },
            {
                "id": "solver",
                "label": "Segment solver",
                "startIndex": solver_start_index,
                "endIndex": solver_end_index,
                "startCycle": solver_start_cycle,
                "endCycle": frames[-1]["state"]["cycle"],
            },
        ],
        "solverStartIndex": solver_start_index,
        "solverEndIndex": solver_end_index,
        "solverActionCount": len(candidate["result"]["actions"]),
        "frames": frames,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "schemaVersion": payload["schemaVersion"],
                "frames": len(frames),
                "prefixFrames": solver_start_index + 1,
                "solverFrames": solver_end_index - solver_start_index + 1,
                "solverStartIndex": solver_start_index,
                "finalCycle": frames[-1]["state"]["cycle"],
                "finalScore": frames[-1]["state"]["score"],
                "renderParts": len(solution.get("parts", [])),
                "trackCoordinates": "world",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
