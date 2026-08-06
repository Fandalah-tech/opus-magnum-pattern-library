from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
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


def bond_text(simulator: Simulator) -> str:
    return ";".join(
        f"{bond.a}-{bond.b}:{bond.kind}"
        for bond in simulator.world.bonds.values()
        if "-wheel-" not in bond.a and "-wheel-" not in bond.b
    ) or "-"


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-almost-solved.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    print("cycle|instructions|events|spawnCounts|bonds|atoms|delivered")
    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
            if event.get("instruction")
        }
        simulator.step(instructions)
        meaningful = [event.kind for event in simulator.world.events if event.kind != "arm-instruction"]
        if simulator.world.cycle < 110 and not meaningful:
            continue
        instruction_text = ",".join(f"{part}:{value}" for part, value in sorted(instructions.items())) or "-"
        spawn_text = ",".join(f"{source.id}:{source.spawn_count}" for source in simulator.inputs)
        delivered = json.dumps(dict(getattr(simulator, "delivered_products", {})), separators=(",", ":"))
        print("|".join((
            str(simulator.world.cycle),
            instruction_text,
            ",".join(meaningful) or "-",
            spawn_text,
            bond_text(simulator),
            atom_text(simulator),
            delivered,
        )))


if __name__ == "__main__":
    main()
