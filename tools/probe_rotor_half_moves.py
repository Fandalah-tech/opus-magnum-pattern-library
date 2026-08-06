from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from packages.opus_engine import SimulationError
from packages.opus_solver import StructureGoal, enumerate_joint_actions
from packages.opus_solver.rotor_prefix import build_locked_prefix_simulator

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
HALF = Path("fixtures/solutions/van-berlos-rotor-area43-half-complete.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    puzzle = _load(PUZZLE)
    simulator = build_locked_prefix_simulator(puzzle, _load(HALF))
    goal = StructureGoal.from_product(puzzle["products"][0], include_baron_held=True)
    options = {}
    for arm_id, arm in simulator.arms.items():
        if arm.part_type == "piston":
            options[arm_id] = (
                None, "grab", "drop", "rotate_cw", "rotate_ccw",
                "pivot_cw", "pivot_ccw", "extend", "retract",
                "track_plus", "track_minus",
            )
        elif arm.part_type == "baron":
            options[arm_id] = (None, "rotate_cw", "rotate_ccw")

    initial_atoms = len(simulator.world.atoms)
    root = goal.best_match(simulator)
    rows = []
    legal = 0
    for action in enumerate_joint_actions(options, max_active_arms=2):
        candidate = deepcopy(simulator)
        try:
            frame = candidate.step(action)
        except SimulationError:
            continue
        if frame.get("phase") == "error" or len(candidate.world.atoms) != initial_atoms:
            continue
        legal += 1
        match = goal.best_match(candidate)
        rows.append({
            "action": action,
            "matchedPositions": match.occupied_positions,
            "matchedEdges": match.matched_edges,
            "rotation": match.rotation,
            "translation": list(match.translation),
            "baronRotation": candidate.arms["part-2"].rotation,
        })
    rows.sort(
        key=lambda row: (
            row["matchedPositions"],
            row["matchedEdges"],
            "part-2" in row["action"],
        ),
        reverse=True,
    )
    print(json.dumps({
        "root": {
            "matchedPositions": root.occupied_positions,
            "matchedEdges": root.matched_edges,
            "rotation": root.rotation,
            "translation": list(root.translation),
        },
        "legalSuccessors": legal,
        "improvingSuccessors": sum(
            1 for row in rows
            if (row["matchedPositions"], row["matchedEdges"])
            > (root.occupied_positions, root.matched_edges)
        ),
        "top": rows[:40],
    }, indent=2))


if __name__ == "__main__":
    main()
