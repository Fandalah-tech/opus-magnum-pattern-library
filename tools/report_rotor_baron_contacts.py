from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.final_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")


def ordinary_at(simulator: Simulator, position):
    return [
        atom.id
        for atom in simulator._atoms_at(position)
        if not simulator._is_wheel_atom_id(atom.id)
    ]


def state(simulator: Simulator, baron):
    contacts = {
        str(branch): {
            "position": list(position),
            "atoms": ordinary_at(simulator, position),
        }
        for branch, position in baron.tips().items()
        if ordinary_at(simulator, position)
    }
    inputs = {
        source.id: {
            "spawnCount": source.spawn_count,
            "occupiedCount": sum(bool(ordinary_at(simulator, position)) for position in source.footprint),
            "occupied": [
                {"position": list(position), "atoms": ordinary_at(simulator, position)}
                for position in source.footprint
                if ordinary_at(simulator, position)
            ],
        }
        for source in simulator.inputs
    }
    return {
        "rotation": baron.rotation,
        "grabbing": baron.grabbing,
        "contacts": contacts,
        "inputs": inputs,
        "ordinaryAtomCount": sum(
            1 for atom in simulator.world.atoms.values()
            if not simulator._is_wheel_atom_id(atom.id)
        ),
    }


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-final-mechanical-prefix.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    baron = next(arm for arm in simulator.arms.values() if arm.part_type == "baron")
    rows = []
    previous = state(simulator, baron)
    rows.append({"cycle": 0, "phase": "initial", **previous})

    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        baron_instruction = instructions.get(baron.id)
        before = state(simulator, baron)
        simulator.step(instructions)
        after = state(simulator, baron)
        meaningful_events = [
            {"kind": event.kind, **event.data}
            for event in simulator.world.events
            if event.kind != "arm-instruction"
        ]
        changed_inputs = before["inputs"] != after["inputs"]
        changed_contacts = before["contacts"] != after["contacts"]
        changed_atom_count = before["ordinaryAtomCount"] != after["ordinaryAtomCount"]
        if baron_instruction or changed_inputs or changed_contacts or changed_atom_count or meaningful_events:
            rows.append({
                "cycle": simulator.world.cycle,
                "baronInstruction": baron_instruction,
                "events": meaningful_events,
                "beforeContacts": before["contacts"],
                "afterContacts": after["contacts"],
                "beforeInputs": before["inputs"],
                "afterInputs": after["inputs"],
                "beforeAtomCount": before["ordinaryAtomCount"],
                "afterAtomCount": after["ordinaryAtomCount"],
                "baronRotation": after["rotation"],
                "baronGrabbing": after["grabbing"],
            })
        previous = after

    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "baronId": baron.id,
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
