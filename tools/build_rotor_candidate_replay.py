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


def main() -> int:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")))
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    simulator = Simulator.from_models(puzzle, solution)

    for row in build_program_timeline(solution).get("cycles", []):
        instructions = {str(event.get("partId")): event.get("instruction") for event in row.get("events", [])}
        simulator.step(instructions)

    frames = [{"index": 0, "action": {}, "state": snapshot(simulator)}]
    for index, action in enumerate(candidate["result"]["actions"], start=1):
        simulator.step(action)
        frames.append({"index": index, "action": action, "state": snapshot(simulator)})

    payload = {
        "schemaVersion": 1,
        "title": "Van Berlo's Rotor — candidat score 599",
        "isCompleteSolution": False,
        "source": "reports/rotor-tail-best-candidate.json",
        "bestScore": candidate["result"]["bestScore"],
        "frames": frames,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"frames": len(frames), "finalCycle": frames[-1]["state"]["cycle"], "finalScore": frames[-1]["state"]["score"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
