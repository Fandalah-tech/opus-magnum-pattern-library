from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
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
    return {
        "rotation": baron.rotation,
        "grabbing": baron.grabbing,
        "tips": {str(branch): list(position) for branch, position in baron.tips().items()},
        "contacts": contacts,
        "ordinaryAtomCount": sum(
            1 for atom in simulator.world.atoms.values()
            if not simulator._is_wheel_atom_id(atom.id)
        ),
        "bonds": [
            {
                "a": bond.a,
                "b": bond.b,
                "kind": bond.kind,
                "aPosition": list(simulator.world.atoms[bond.a].position),
                "bPosition": list(simulator.world.atoms[bond.b].position),
                "floatingRoot": simulator.floating_bond_roots.get(key),
            }
            for key, bond in sorted(simulator.world.bonds.items())
        ],
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

    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        before = state(simulator, baron)
        simulator.step(instructions)
        after = state(simulator, baron)
        cycle = simulator.world.cycle
        if 50 <= cycle <= 110 and (
            instructions.get(baron.id)
            or before["contacts"] != after["contacts"]
            or before["bonds"] != after["bonds"]
            or simulator.world.events
        ):
            rows.append({
                "cycle": cycle,
                "instructions": instructions,
                "events": [{"kind": event.kind, **event.data} for event in simulator.world.events],
                "before": before,
                "after": after,
            })

    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "baronId": baron.id,
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
