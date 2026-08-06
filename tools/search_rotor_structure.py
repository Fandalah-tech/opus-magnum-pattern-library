from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver import (
    StructureGoal,
    build_rotor_seed_macro_library,
    explore_simulator_beam,
    explore_simulator_macro_beam,
    learn_action_windows,
)
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
    eligible_count = len(goal._eligible_atom_ids(best)) if best else None
    return {
        "label": label,
        "found": result.found,
        "depth": result.depth,
        "bestScore": result.best_score,
        "visitedStates": result.visited_states,
        "expandedStates": result.expanded_states,
        "stoppedReason": result.stopped_reason,
        "macros": getattr(result, "macros", []),
        "actions": result.actions,
        "matchedPositions": match.occupied_positions if match else None,
        "matchedEdges": match.matched_edges if match else None,
        "matchRotation": match.rotation if match else None,
        "matchTranslation": list(match.translation) if match else None,
        "eligibleAtomCount": eligible_count,
        "targetAtomCount": goal.atom_count,
        "targetBondCount": goal.bond_count,
        "bestAtomCount": len(best.world.atoms) if best else None,
        "bestBondCount": len(best.world.bonds) if best else None,
    }


def _plateau_score(goal, minimum_edges: int):
    def score(simulator) -> int:
        match = goal.best_match(simulator)
        if match.matched_edges < minimum_edges:
            return -100_000 + match.matched_edges * 1_000 + match.occupied_positions
        eligible = goal._eligible_atom_ids(simulator)
        atom_delta = abs(len(eligible) - goal.atom_count)
        return (
            match.matched_edges * 10_000
            + match.occupied_positions * 500
            - atom_delta * 250
        )
    return score


def _fixed_inventory(goal, atom_count: int):
    def admissible(simulator) -> bool:
        return len(goal._eligible_atom_ids(simulator)) == atom_count
    return admissible


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
        max_depth=20,
        beam_width=180,
        max_states=40_000,
        max_active_arms=1,
        time_limit_seconds=45,
    )
    stages = [_summary("single-arm-frontier", stage1, goal)]
    current = stage1

    if not current.found and current.simulator is not None:
        stage2 = explore_simulator_beam(
            current.simulator,
            _actions(current.simulator),
            goal.reached,
            goal.score,
            max_depth=14,
            beam_width=120,
            max_states=32_000,
            max_active_arms=2,
            time_limit_seconds=45,
        )
        stage2.actions = [*current.actions, *stage2.actions]
        stages.append(_summary("coordinated-refinement", stage2, goal))
        current = stage2

    if not current.found and current.simulator is not None:
        current_match = goal.best_match(current.simulator)
        stage3 = explore_simulator_beam(
            current.simulator,
            _actions(current.simulator),
            goal.reached,
            _plateau_score(goal, current_match.matched_edges),
            max_depth=14,
            beam_width=140,
            max_states=36_000,
            max_active_arms=2,
            time_limit_seconds=45,
        )
        stage3.actions = [*current.actions, *stage3.actions]
        stages.append(_summary("edge-plateau-position-refinement", stage3, goal))
        current = stage3

    if not current.found and current.simulator is not None and current.actions:
        current_match = goal.best_match(current.simulator)
        inventory_count = len(goal._eligible_atom_ids(current.simulator))
        trajectory_macros = learn_action_windows(
            current.actions,
            lengths=(2, 3, 4, 6, 8),
            tag="rotor-discovered",
        )
        macro_library = (*build_rotor_seed_macro_library(solution), *trajectory_macros)
        stage4 = explore_simulator_macro_beam(
            current.simulator,
            macro_library,
            goal.reached,
            _plateau_score(goal, current_match.matched_edges),
            max_depth=8,
            beam_width=180,
            max_states=30_000,
            time_limit_seconds=45,
            state_filter=_fixed_inventory(goal, inventory_count),
        )
        stage4.actions = [*current.actions, *stage4.actions]
        stages.append(_summary("fixed-inventory-macro-refinement", stage4, goal))
        current = stage4

    print(json.dumps({
        "stages": stages,
        "best": stages[-1],
        "learnedMacroCount": len(learn_action_windows(current.actions)) if current.actions else 0,
    }, indent=2))


if __name__ == "__main__":
    main()
