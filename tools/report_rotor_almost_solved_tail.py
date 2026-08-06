from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_engine.simulator import SimulationError
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-almost-solved.solution.b64")


def arm_text(simulator: Simulator, arm_id: str) -> str:
    arm = simulator.arms[arm_id]
    tips = ",".join(f"{k}:{v[0]},{v[1]}" for k, v in arm.tips().items())
    held = "+".join(sorted(set(arm.held_atoms.values()))) or "-"
    return f"o={arm.origin[0]},{arm.origin[1]};r={arm.rotation};l={arm.length};t={arm.track_index};tips={tips};held={held}"


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
    print("cycle|instructions|events|p8|p10|bonds|atoms|error")
    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
            if event.get("instruction")
        }
        error = "-"
        try:
            simulator.step(instructions)
        except SimulationError as exc:
            error = str(exc)
        if 58 <= simulator.world.cycle <= 105:
            meaningful = [event.kind for event in simulator.world.events if event.kind != "arm-instruction"]
            instruction_text = ",".join(f"{part}:{value}" for part, value in sorted(instructions.items())) or "-"
            print("|".join((
                str(simulator.world.cycle), instruction_text, ",".join(meaningful) or "-",
                arm_text(simulator, "part-8"), arm_text(simulator, "part-10"),
                bond_text(simulator), atom_text(simulator), error,
            )))
        if error != "-":
            break


if __name__ == "__main__":
    main()
