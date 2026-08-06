from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.builder import InputSource
from packages.opus_engine.final_simulator import Simulator
from packages.opus_engine.model import Atom, Bond
from packages.opus_engine.simulator import SimulationError
from packages.opus_engine.world import WorldEvent
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-last-isolated-atom-prefix.solution.b64")


def spawn_whole(self: InputSource, world) -> bool:
    if not all(world.atom_at(position) is None for position in self.footprint):
        return False
    generation = self.spawn_count
    atom_ids = {}
    for index, (element, position) in enumerate(self.atom_templates):
        atom_id = f"{self.id}-spawn-{generation}-atom-{index}"
        world.add_atom(Atom(atom_id, element, position))
        atom_ids[index] = atom_id
    for first, second, kind in self.bond_templates:
        world.add_bond(Bond(atom_ids[first], atom_ids[second], kind))
    self.spawn_count += 1
    world.events.append(WorldEvent("input-spawned", world.cycle, {
        "inputId": self.id,
        "generation": generation,
        "atomIds": list(atom_ids.values()),
        "wholeReagent": True,
    }))
    return True


def replay(puzzle, solution):
    simulator = Simulator.from_models(puzzle, solution)
    history = []
    for row in build_program_timeline(solution).get("cycles", []):
        instructions = {str(event.get("partId")): event.get("instruction") for event in row.get("events", [])}
        try:
            simulator.step(instructions)
        except SimulationError as error:
            return {
                "completed": False,
                "cycle": simulator.world.cycle + 1,
                "instructions": instructions,
                "error": str(error),
                "atomCount": len([a for a in simulator.world.atoms.values() if not simulator._is_wheel_atom_id(a.id)]),
                "bondCount": len(simulator.world.bonds),
                "history": history[-8:],
            }
        history.append({
            "cycle": simulator.world.cycle,
            "instructions": instructions,
            "events": [{"kind": event.kind, **event.data} for event in simulator.world.events],
        })
    return {
        "completed": True,
        "cycle": simulator.world.cycle,
        "atomCount": len([a for a in simulator.world.atoms.values() if not simulator._is_wheel_atom_id(a.id)]),
        "bondCount": len(simulator.world.bonds),
        "delivered": simulator.delivered_products,
        "history": history[-8:],
    }


def main():
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")))
    original = InputSource.spawn
    independent = replay(puzzle, solution)
    InputSource.spawn = spawn_whole
    try:
        whole = replay(puzzle, solution)
    finally:
        InputSource.spawn = original
    print(json.dumps({"independentComponents": independent, "wholeReagent": whole}, indent=2))


if __name__ == "__main__":
    main()
