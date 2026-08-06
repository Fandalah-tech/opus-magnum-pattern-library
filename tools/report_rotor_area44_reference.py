from __future__ import annotations

import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_solver import StructureGoal

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE = Path("fixtures/solutions/van-berlos-rotor-area44-ideal-setup-6.parsed.json")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    puzzle = load(PUZZLE)
    solution = load(REFERENCE)
    goal = StructureGoal.from_product(puzzle["products"][0], include_baron_held=True)
    simulator = Simulator.from_models(puzzle, solution)
    timeline = build_program_timeline(solution)

    records = []
    previous = None
    for row in timeline.get("cycles", []):
        instructions = {
            str(event.get("partId")): event.get("instruction")
            for event in row.get("events", [])
        }
        simulator.step(instructions)
        match = goal.best_match(simulator)
        record = {
            "cycle": simulator.world.cycle,
            "matchedPositions": match.occupied_positions,
            "matchedEdges": match.matched_edges,
            "rotation": match.rotation,
            "translation": list(match.translation),
            "baronRotation": simulator.arms["part-2"].rotation,
            "atomCount": len(simulator.world.atoms),
            "instructions": instructions,
        }
        signature = (record["matchedPositions"], record["matchedEdges"], record["rotation"], tuple(record["translation"]))
        if signature != previous or "part-2" in instructions:
            records.append(record)
        previous = signature

    final_match = goal.best_match(simulator)
    print(json.dumps({
        "name": solution.get("name"),
        "requestedCycles": len(timeline.get("cycles", [])),
        "completedCycles": simulator.world.cycle,
        "final": {
            "matchedPositions": final_match.occupied_positions,
            "matchedEdges": final_match.matched_edges,
            "rotation": final_match.rotation,
            "translation": list(final_match.translation),
            "atomCount": len(simulator.world.atoms),
        },
        "transitions": records,
    }, indent=2))


if __name__ == "__main__":
    main()
