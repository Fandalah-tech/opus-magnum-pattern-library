from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")
WATCH = {
    "part-9-spawn-0-atom-0",
    "part-9-spawn-0-atom-1",
    "part-4-spawn-0-atom-0",
    "part-4-spawn-0-atom-1",
    "part-4-spawn-0-atom-2",
}


def snapshot(simulator: Simulator):
    return {
        "atoms": {
            atom_id: {
                "position": list(simulator.world.atoms[atom_id].position),
                "element": simulator.world.atoms[atom_id].element,
                "heldBy": sorted(simulator.world.atoms[atom_id].held_by),
            }
            for atom_id in sorted(WATCH)
            if atom_id in simulator.world.atoms
        },
        "arms": {
            arm_id: {
                "origin": list(arm.origin),
                "rotation": arm.rotation,
                "length": arm.length,
                "tip": list(arm.tip()),
                "grabbing": arm.grabbing,
                "held": sorted(set(arm.held_atoms.values())),
                "trackIndex": arm.track_index,
            }
            for arm_id, arm in simulator.arms.items()
            if arm.part_type == "piston"
        },
    }


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-final-mechanical-prefix.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    rows = [{"cycle": 0, **snapshot(simulator)}]
    previous = snapshot(simulator)

    for row in timeline.get("cycles", []):
        if simulator.world.cycle >= 70:
            break
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        simulator.step(instructions)
        current = snapshot(simulator)
        if current != previous or any(
            event.kind != "arm-instruction" for event in simulator.world.events
        ):
            rows.append({
                "cycle": simulator.world.cycle,
                "instructions": {key: value for key, value in instructions.items() if value},
                "events": [
                    {"kind": event.kind, **event.data}
                    for event in simulator.world.events
                    if event.kind != "arm-instruction"
                ],
                **current,
            })
        previous = current

    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
