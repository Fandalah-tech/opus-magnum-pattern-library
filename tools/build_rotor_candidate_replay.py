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
        "schemaVersion": 2,
        "title": "Van Berlo's Rotor — candidat score 599",
        "isCompleteSolution": False,
        "source": "reports/rotor-tail-best-candidate.json",
        "bestScore": candidate["result"]["bestScore"],
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
                "frames": len(frames),
                "prefixFrames": solver_start_index + 1,
                "solverFrames": solver_end_index - solver_start_index + 1,
                "solverStartIndex": solver_start_index,
                "finalCycle": frames[-1]["state"]["cycle"],
                "finalScore": frames[-1]["state"]["score"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
