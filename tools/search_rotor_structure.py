from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver import StructureGoal, explore_simulator_beam
from packages.opus_solver.rotor_prefix import build_locked_prefix_simulator

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
SEED = Path("fixtures/solutions/van-berlos-rotor-area42-confined-seed.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _actions(simulator):
    return {
        arm_id: (
            None, "grab", "drop", "rotate_cw", "rotate_ccw",
            "pivot_cw", "pivot_ccw", "extend", "retract",
            "track_plus", "track_minus",
        )
        for arm_id, arm in simulator.arms.items()
        if arm.part_type == "piston"
    }


def _summary(label, result, goal):
    best = result.simulator
    match = goal.best_match(best) if best else None
    return {
        "label": label,
        "found": result.found,
        "depth": result.depth,
        "bestScore": result.best_score,
        "visitedStates": result.visited_states,
        "expandedStates": result.expanded_states,
        "stoppedReason": result.stopped_reason,
        "actions": result.actions,
        "matchedPositions": match.occupied_positions if match else None,
        "matchedEdges": match.matched_edges if match else None,
        "matchRotation": match.rotation if match else None,
        "matchTranslation": list(match.translation) if match else None,
        "bestAtomCount": len(best.world.atoms) if best else None,
        "bestBondCount": len(best.world.bonds) if best else None,
    }


def main() -> None:
    puzzle = _load(PUZZLE)
    solution = _load(SEED)
    simulator = build_locked_prefix_simulator(puzzle, solution, settle_cycles=1)
    goal = StructureGoal.from_product(puzzle["products"][0])

    stage1 = explore_simulator_beam(
        simulator,
        _actions(simulator),
        goal.reached,
        goal.score,
        max_depth=24,
        beam_width=180,
        max_states=45_000,
        max_active_arms=1,
        time_limit_seconds=68,
    )
    stages = [_summary("single-arm-frontier", stage1, goal)]

    if not stage1.found and stage1.simulator is not None:
        stage2 = explore_simulator_beam(
            stage1.simulator,
            _actions(stage1.simulator),
            goal.reached,
            goal.score,
            max_depth=16,
            beam_width=110,
            max_states=35_000,
            max_active_arms=2,
            time_limit_seconds=68,
        )
        combined_actions = [*stage1.actions, *stage2.actions]
        stage2.actions = combined_actions
        stages.append(_summary("coordinated-refinement", stage2, goal))

    print(json.dumps({"stages": stages, "best": stages[-1]}, indent=2))


if __name__ == "__main__":
    main()
