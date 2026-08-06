from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.final_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-final-mechanical-prefix.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    simulator.run_timeline(timeline)
    baron = next(arm for arm in simulator.arms.values() if arm.part_type == "baron")
    last_cycle = max((row.get("cycle", 0) for row in timeline.get("cycles", [])), default=0)
    late_programs = {}
    for part in solution.get("parts", []):
        rows = [row for row in part.get("program", []) if row.get("cycle", 0) >= max(0, last_cycle - 45)]
        if rows:
            late_programs[part["id"]] = {"type": part["type"], "program": rows}
    atoms = [
        {
            "id": atom.id,
            "element": atom.element,
            "position": list(atom.position),
            "heldBy": sorted(atom.held_by),
        }
        for atom in simulator.world.atoms.values()
        if "-wheel-" not in atom.id
    ]
    bonds = [
        {"a": bond.a, "b": bond.b, "type": bond.kind}
        for bond in simulator.world.bonds.values()
        if "-wheel-" not in bond.a and "-wheel-" not in bond.b
    ]
    print(json.dumps({
        "name": solution.get("name"),
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "lastProgramCycle": last_cycle,
        "completedCycle": simulator.world.cycle,
        "finalBaronRotation": baron.rotation,
        "baronHeld": list(baron.held_atoms.values()),
        "latePrograms": late_programs,
        "atoms": atoms,
        "bonds": bonds,
        "finalFrame": simulator.frames[-1] if simulator.frames else None,
    }, indent=2))


if __name__ == "__main__":
    main()
