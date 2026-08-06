from __future__ import annotations

import base64
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_engine.simulator import SimulationError
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-almost-solved.solution.b64")


def atom_text(simulator: Simulator) -> str:
    atoms = [atom for atom in simulator.world.atoms.values() if "-wheel-" not in atom.id]
    return ";".join(
        f"{atom.id}={atom.element}@{atom.position[0]},{atom.position[1]}[{'+'.join(sorted(atom.held_by)) or '-'}]"
        for atom in sorted(atoms, key=lambda item: item.id)
    )


def bond_text(simulator: Simulator) -> str:
    return ";".join(
        f"{bond.a}-{bond.b}:{bond.kind}"
        for bond in simulator.world.bonds.values()
        if "-wheel-" not in bond.a and "-wheel-" not in bond.b
    ) or "-"


def main() -> None:
    import base64, json
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")), source_name="a47")
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    print("cycle|instructions|events|atoms|bonds|delivered|error")
    for row in timeline.get("cycles", []):
        instructions = {str(event.get("partId")): event.get("instruction") for event in row.get("events", []) if event.get("instruction")}
        error = "-"
        try:
            simulator.step(instructions)
        except SimulationError as exc:
            error = str(exc)
        if simulator.world.cycle >= 96:
            meaningful = [event.kind for event in simulator.world.events if event.kind != "arm-instruction"]
            print("|".join((
                str(simulator.world.cycle),
                ",".join(f"{part}:{value}" for part, value in sorted(instructions.items())) or "-",
                ",".join(meaningful) or "-",
                atom_text(simulator),
                bond_text(simulator),
                json.dumps(dict(getattr(simulator, "delivered_products", {})), separators=(",", ":")),
                error,
            )))
        if error != "-":
            break


if __name__ == "__main__":
    main()
