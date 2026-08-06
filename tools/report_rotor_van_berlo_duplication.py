from __future__ import annotations

import base64
import json
from collections import Counter
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")


def counts(simulator: Simulator) -> tuple[int, int]:
    atoms = sum(1 for atom in simulator.world.atoms.values() if "-wheel-" not in atom.id)
    bonds = sum(
        1 for bond in simulator.world.bonds.values()
        if "-wheel-" not in bond.a and "-wheel-" not in bond.b
    )
    return atoms, bonds


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-final-mechanical-prefix.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    event_counts: Counter[str] = Counter()
    notable = []
    max_atoms = max_bonds = 0
    previous_counts = counts(simulator)

    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        simulator.step(instructions)
        current = counts(simulator)
        max_atoms = max(max_atoms, current[0])
        max_bonds = max(max_bonds, current[1])
        events = [event for event in simulator.world.events if event.kind != "arm-instruction"]
        event_counts.update(event.kind for event in events)
        important = [
            {"kind": event.kind, **event.data}
            for event in events
            if event.kind in {
                "input-spawned", "atom-duplicated", "bond-created", "bond-removed",
                "molecule-consumed", "product-delivered", "simulation-error",
            }
        ]
        if current != previous_counts or important:
            notable.append({
                "cycle": simulator.world.cycle,
                "atomCount": current[0],
                "bondCount": current[1],
                "events": important,
            })
        previous_counts = current

    ordinary = [atom for atom in simulator.world.atoms.values() if "-wheel-" not in atom.id]
    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "completedCycle": simulator.world.cycle,
        "maxAtomCount": max_atoms,
        "maxBondCount": max_bonds,
        "finalAtomCount": len(ordinary),
        "finalBondCount": counts(simulator)[1],
        "eventCounts": dict(sorted(event_counts.items())),
        "notable": notable,
        "delivered": dict(getattr(simulator, "delivered_products", {})),
        "finalAtoms": [
            {"id": atom.id, "element": atom.element, "position": list(atom.position), "heldBy": sorted(atom.held_by)}
            for atom in sorted(ordinary, key=lambda item: item.id)
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
