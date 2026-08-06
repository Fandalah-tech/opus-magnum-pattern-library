from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-almost-solved.solution.b64")


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-almost-solved.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    simulator.run_timeline(timeline)
    events = [
        {"cycle": event.cycle, **event.data}
        for event in simulator.world.events
        if event.kind == "atom-duplicated"
    ]
    baron = next(arm for arm in simulator.arms.values() if arm.part_type == "baron")
    print(json.dumps({
        "duplicationEvents": events,
        "finalBaronRotation": baron.rotation,
        "wheel": [
            {
                "id": atom_id,
                "element": simulator.world.atoms[atom_id].element,
                "position": list(simulator.world.atoms[atom_id].position),
            }
            for atom_id in baron.held_atoms.values()
            if atom_id in simulator.world.atoms
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
