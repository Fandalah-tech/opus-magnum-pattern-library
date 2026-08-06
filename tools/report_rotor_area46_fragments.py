from __future__ import annotations

import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE = Path("fixtures/solutions/van-berlos-rotor-area46-ideal-setup-8.parsed.json")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def component_summary(simulator: Simulator) -> list[dict]:
    result = []
    for molecule in simulator.world.molecules():
        atoms = [simulator.world.atoms[atom_id] for atom_id in molecule.atom_ids]
        result.append({
            "size": len(atoms),
            "bondCount": len(molecule.bond_keys),
            "atoms": [
                {
                    "id": atom.id,
                    "element": atom.element,
                    "position": list(atom.position),
                    "heldBy": sorted(atom.held_by),
                }
                for atom in sorted(atoms, key=lambda item: (item.position, item.id))
            ],
        })
    return sorted(result, key=lambda item: (-item["size"], -item["bondCount"], item["atoms"][0]["id"]))


def main() -> None:
    puzzle = load(PUZZLE)
    solution = load(REFERENCE)
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    records = []
    previous_signature = None

    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        frame = simulator.step(instructions)
        components = component_summary(simulator)
        signature = tuple((item["size"], item["bondCount"]) for item in components)
        event_kinds = [event.get("kind") for event in frame.get("events", [])]
        if signature != previous_signature or simulator.world.cycle >= 85 or event_kinds:
            records.append({
                "cycle": simulator.world.cycle,
                "instructions": instructions,
                "componentSignature": [list(item) for item in signature],
                "components": components,
                "events": frame.get("events", []),
            })
        previous_signature = signature

    print(json.dumps({
        "name": solution.get("name"),
        "completedCycles": simulator.world.cycle,
        "finalComponents": component_summary(simulator),
        "records": records,
    }, indent=2))


if __name__ == "__main__":
    main()
