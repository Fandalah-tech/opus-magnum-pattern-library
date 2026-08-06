from __future__ import annotations

import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_solver import apply_mechanical_macro, canonical_state_key, load_reference_macro


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
SOLUTION = Path("fixtures/solutions/van-berlos-rotor-area44-ideal-setup-6.parsed.json")
MACRO = Path("fixtures/macros/van-berlos-rotor-area44-confined-rotation.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_through(solution: dict, completed_cycles: int) -> list[dict]:
    rows = list(build_program_timeline(solution).get("cycles", []))
    return rows[:completed_cycles]


def _replay(puzzle: dict, solution: dict, completed_cycles: int) -> Simulator:
    simulator = Simulator.from_models(puzzle, solution)
    simulator.run_timeline({"cycles": _rows_through(solution, completed_cycles)})
    return simulator


def main() -> None:
    puzzle = _load(PUZZLE)
    solution = _load(SOLUTION)
    document = _load(MACRO)
    macro = load_reference_macro(MACRO)
    start = int(document["startCycle"])
    end = int(document["endCycle"])

    source = _replay(puzzle, solution, start)
    expected = _replay(puzzle, solution, end + 1)
    applied = apply_mechanical_macro(source, macro)

    compatibility: list[dict] = []
    for completed in range(0, end + 2):
        candidate = _replay(puzzle, solution, completed)
        result = apply_mechanical_macro(candidate, macro)
        compatibility.append({
            "completedCycles": completed,
            "legal": result is not None,
            "matchesReferenceEnd": bool(
                result is not None
                and canonical_state_key(result.simulator) == canonical_state_key(expected)
            ),
        })

    output = {
        "macro": macro.name,
        "actionFrames": len(macro.actions),
        "startCycle": start,
        "endCycle": end,
        "sourceCycle": source.world.cycle,
        "expectedCycle": expected.world.cycle,
        "appliesAtReferenceStart": applied is not None,
        "exactReferenceReplay": bool(
            applied is not None
            and canonical_state_key(applied.simulator) == canonical_state_key(expected)
        ),
        "legalCompletedCycles": [
            row["completedCycles"] for row in compatibility if row["legal"]
        ],
        "exactCompletedCycles": [
            row["completedCycles"] for row in compatibility if row["matchesReferenceEnd"]
        ],
        "referenceArmState": {
            arm.id: {
                "origin": list(arm.origin),
                "rotation": arm.rotation,
                "length": arm.length,
                "trackIndex": arm.track_index,
                "grabbing": arm.grabbing,
                "heldBranches": sorted(arm.held_atoms),
            }
            for arm in sorted(source.arms.values(), key=lambda item: item.id)
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
