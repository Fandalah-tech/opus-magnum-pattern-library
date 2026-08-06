from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-almost-solved.solution.b64")


def ordinary_atoms(simulator: Simulator):
    return [
        {
            "id": atom.id,
            "element": atom.element,
            "position": list(atom.position),
            "heldBy": sorted(atom.held_by),
        }
        for atom in sorted(simulator.world.atoms.values(), key=lambda item: item.id)
        if "-wheel-" not in atom.id
    ]


def ordinary_bonds(simulator: Simulator):
    return [
        {"a": bond.a, "b": bond.b, "type": bond.kind}
        for bond in simulator.world.bonds.values()
        if "-wheel-" not in bond.a and "-wheel-" not in bond.b
    ]


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-almost-solved.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    rows = []
    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
            if event.get("instruction")
        }
        simulator.step(instructions)
        meaningful = [
            {"kind": event.kind, **event.data}
            for event in simulator.world.events
            if event.kind != "arm-instruction"
        ]
        if simulator.world.cycle >= 120 or meaningful:
            rows.append({
                "cycle": simulator.world.cycle,
                "instructions": instructions,
                "events": meaningful,
                "atoms": ordinary_atoms(simulator),
                "bonds": ordinary_bonds(simulator),
                "inputSpawnCounts": {source.id: source.spawn_count for source in simulator.inputs},
                "delivered": dict(getattr(simulator, "delivered_products", {})),
            })
    print(json.dumps({
        "referenceSha256": solution.get("source", {}).get("sha256"),
        "parts": [
            {
                "id": part.get("id"),
                "type": part.get("type"),
                "position": part.get("position"),
                "rotation": part.get("rotation"),
                "length": part.get("length"),
            }
            for part in solution.get("parts", [])
        ],
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
