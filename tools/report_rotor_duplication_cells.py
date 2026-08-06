from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.van_berlo_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-final-mechanical-prefix.solution.b64")


def occupants(simulator: Simulator, position):
    return [
        {"id": atom.id, "element": atom.element, "wheel": simulator._is_wheel_atom_id(atom.id)}
        for atom in simulator._atoms_at(position)
    ]


def cell_state(simulator: Simulator):
    return [
        {
            "partId": part_id,
            "sourcePosition": list(source),
            "source": occupants(simulator, source),
            "saltPosition": list(salt),
            "salt": occupants(simulator, salt),
        }
        for source, salt, part_id in simulator.duplication_glyphs
    ]


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
            if event.kind in {"atom-duplicated", "input-spawned", "atom-grabbed", "atoms-dropped"}
        ]
        if current != previous or events:
            rows.append({"cycle": simulator.world.cycle, "cells": current, "events": events})
        previous = current

    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "rows": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
