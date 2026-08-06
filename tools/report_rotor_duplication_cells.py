from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.builder import DIRECTIONS
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")


def ordinary_occupants(simulator: Simulator, position):
    return [
        {"id": atom.id, "element": atom.element, "heldBy": sorted(atom.held_by)}
        for atom in simulator._atoms_at(position)
        if not simulator._is_wheel_atom_id(atom.id)
    ]


def cell_state(simulator: Simulator):
    result = []
    for source, configured_salt, part_id in simulator.duplication_glyphs:
        neighbors = []
        for direction, delta in enumerate(DIRECTIONS):
            position = (source[0] + delta[0], source[1] + delta[1])
            atoms = ordinary_occupants(simulator, position)
            if atoms:
                neighbors.append({
                    "direction": direction,
                    "position": list(position),
                    "configuredSalt": position == configured_salt,
                    "atoms": atoms,
                })
        result.append({
            "partId": part_id,
            "sourcePosition": list(source),
            "sourceWheel": [
                {"id": atom.id, "element": atom.element}
                for atom in simulator._atoms_at(source)
                if simulator._is_wheel_atom_id(atom.id)
            ],
            "configuredSaltPosition": list(configured_salt),
            "neighbors": neighbors,
        })
    return result


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(
        base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")),
        source_name="van-berlos-rotor-area47-final-mechanical-prefix.solution",
    )
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)
    rows = [{"cycle": 0, "cells": cell_state(simulator)}]
    previous = rows[0]["cells"]

    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        simulator.step(instructions)
        current = cell_state(simulator)
        events = [
            {"kind": event.kind, **event.data}
            for event in simulator.world.events
            if event.kind in {"atom-duplicated", "input-spawned"}
        ]
        has_neighbor = any(cell["neighbors"] for cell in current)
        if current != previous and has_neighbor or events:
            rows.append({"cycle": simulator.world.cycle, "cells": current, "events": events})
        previous = current

    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
