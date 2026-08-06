from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.simulator import SimulationError
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-almost-solved.solution.b64")


def atom_text(simulator: Simulator) -> str:
    rows = []
    for atom in sorted(simulator.world.atoms.values(), key=lambda item: item.id):
        if "-wheel-" in atom.id:
            continue
        held = "+".join(sorted(atom.held_by)) or "-"
        rows.append(f"{atom.id}={atom.element}@{atom.position[0]},{atom.position[1]}[{held}]")
    return ";".join(rows)


def emit(simulator: Simulator, instructions: dict[str, str], error: str = "-") -> None:
    events = ",".join(event.kind for event in simulator.world.events if event.kind != "arm-instruction") or "-"
    instruction_text = ",".join(f"{part}:{value}" for part, value in sorted(instructions.items())) or "-"
    spawn_text = ",".join(f"{source.id}:{source.spawn_count}" for source in simulator.inputs)
    print("|".join((str(simulator.world.cycle), instruction_text, events, spawn_text, atom_text(simulator), error)))


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")), source_name="van-berlos-rotor-area47-almost-solved.solution")
    simulator = Simulator.from_models(puzzle, solution)
    print("cycle|instructions|events|spawnCounts|atoms|error")
    for row in build_program_timeline(solution).get("cycles", []):
        instructions = {str(event.get("partId")): event.get("instruction") for event in row.get("events", []) if event.get("instruction")}
        try:
            simulator.step(instructions)
        except SimulationError as exc:
            emit(simulator, instructions, str(exc))
            break
        if simulator.world.cycle >= 97:
            emit(simulator, instructions)


if __name__ == "__main__":
    main()
