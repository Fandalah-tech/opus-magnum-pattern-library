from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver import StructureGoal, explore_simulator_beam
from packages.opus_solver.rotor_prefix import build_locked_prefix_simulator

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
HALF = Path("fixtures/solutions/van-berlos-rotor-area43-half-complete.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _actions(simulator):
    options = {}
    for arm_id, arm in simulator.arms.items():
        if arm.part_type == "piston":
            options[arm_id] = (
                None, "grab", "drop", "rotate_cw", "rotate_ccw",
                "pivot_cw", "pivot_ccw", "extend", "retract",
                "track_plus", "track_minus",
            )
        elif arm.part_type == "baron":
            # Keep the completed half attached to the rotor.  The first search
            # phase learns only confined reorientation, not wholesale release.
            options[arm_id] = (None, "rotate_cw", "rotate_ccw")
    return options


def main() -> None:
    puzzle = _load(PUZZLE)
    simulator = build_locked_prefix_simulator(puzzle, _load(HALF))
    goal = StructureGoal.from_product(
        puzzle["products"][0],
        include_baron_held=True,
    )
    initial_atoms = len(simulator.world.atoms)

    def geometry_reached(state) -> bool:
        return goal.best_match(state).occupied_positions == goal.atom_count

    def admissible(state) -> bool:
        # The half checkpoint already contains every raw atom needed for the
        # geometric experiment.  Reject automatic reagent respawns and keep
        # the A43 workspace from filling with unrelated material.
        return len(state.world.atoms) == initial_atoms

    def score(state) -> int:
        match = goal.best_match(state)
        held = sum(len(arm.held_atoms) for arm in state.arms.values())
        return match.occupied_positions * 10_000 + match.matched_edges * 250 - held

    result = explore_simulator_beam(
        simulator,
        _actions(simulator),
        geometry_reached,
        score,
        max_depth=24,
        beam_width=700,
        max_states=180_000,
        max_active_arms=2,
        time_limit_seconds=180,
        state_filter=admissible,
    )
    best = result.simulator
    match = goal.best_match(best) if best else None
    print(json.dumps({
        "found": result.found,
        "depth": result.depth,
        "bestScore": result.best_score,
        "visitedStates": result.visited_states,
        "expandedStates": result.expanded_states,
        "stoppedReason": result.stopped_reason,
        "actions": result.actions,
        "matchedPositions": match.occupied_positions if match else None,
        "matchedEdges": match.matched_edges if match else None,
        "rotation": match.rotation if match else None,
        "translation": list(match.translation) if match else None,
        "atomCount": len(best.world.atoms) if best else None,
    }, indent=2))


if __name__ == "__main__":
    main()
