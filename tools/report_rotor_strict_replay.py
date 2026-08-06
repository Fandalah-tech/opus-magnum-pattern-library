from __future__ import annotations

import base64
import json
from collections import deque
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.simulator import SimulationError
from packages.opus_engine.van_berlo_simulator import Simulator as VanBerloSimulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")


class StrictSimulator(VanBerloSimulator):
    def _capture_bonder_collisions(self, proposals) -> None:
        return None


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")))
    simulator = StrictSimulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    history = deque(maxlen=8)
    result = {"completed": True, "cycle": 0, "history": []}
    for row in timeline.get("cycles", []):
        instructions = {str(event.get("partId")): event.get("instruction") for event in row.get("events", [])}
        before = {
            atom.id: {"element": atom.element, "position": list(atom.position), "heldBy": sorted(atom.held_by)}
            for atom in simulator.world.atoms.values() if not simulator._is_wheel_atom_id(atom.id)
        }
        try:
            simulator.step(instructions)
        except SimulationError as error:
            result = {
                "completed": False,
                "cycle": simulator.world.cycle + 1,
                "instructions": instructions,
                "error": str(error),
                "beforeAtoms": before,
                "bonds": [
                    {"a": bond.a, "b": bond.b, "kind": bond.kind}
                    for bond in simulator.world.bonds.values()
                ],
                "arms": {arm_id: arm.snapshot() for arm_id, arm in simulator.arms.items()},
                "history": list(history),
            }
            break
        history.append({
            "cycle": simulator.world.cycle,
            "instructions": instructions,
            "events": [{"kind": event.kind, **event.data} for event in simulator.world.events],
        })
        result["cycle"] = simulator.world.cycle
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
