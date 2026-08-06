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
    rows = []
    previous_atoms = None
    previous_delivered = None
    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        simulator.step(instructions)
        ordinary = [atom for atom in simulator.world.atoms.values() if "-wheel-" not in atom.id]
        atom_count = len(ordinary)
        delivered = dict(getattr(simulator, "delivered_products", {}))
        meaningful = [
            {"kind": event.kind, **event.data}
            for event in simulator.world.events
            if event.kind != "arm-instruction"
        ]
        if atom_count != previous_atoms or delivered != previous_delivered or meaningful or simulator.world.cycle >= 115:
            rows.append({
                "cycle": simulator.world.cycle,
                "atomCount": atom_count,
                "bondCount": sum(
                    1 for bond in simulator.world.bonds.values()
                    if "-wheel-" not in bond.a and "-wheel-" not in bond.b
                ),
                "moleculeCount": len([
                    molecule for molecule in simulator.world.molecules()
                    if any("-wheel-" not in atom_id for atom_id in molecule.atom_ids)
                ]),
                "delivered": delivered,
                "events": meaningful,
                "atoms": [
                    {"id": atom.id, "element": atom.element, "position": list(atom.position), "heldBy": sorted(atom.held_by)}
                    for atom in sorted(ordinary, key=lambda item: item.id)
                ] if simulator.world.cycle >= 120 else None,
            })
        previous_atoms = atom_count
        previous_delivered = delivered
    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
