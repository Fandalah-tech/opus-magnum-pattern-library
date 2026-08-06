from __future__ import annotations

import base64
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.final_simulator import Simulator
from packages.opus_parser.solution import parse_solution_bytes
from packages.opus_solver.beam_explorer import explore_simulator_beam

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-last-isolated-atom-prefix.solution.b64")


def ordinary_atoms(simulator: Simulator):
    return [atom for atom in simulator.world.atoms.values() if not simulator._is_wheel_atom_id(atom.id)]


def output_score(simulator: Simulator) -> int:
    _, _, expected_atoms, expected_bonds = simulator.output_patterns[0]
    expected = dict(expected_atoms)
    atoms_by_pos = {}
    for atom in ordinary_atoms(simulator):
        atoms_by_pos.setdefault(atom.position, []).append(atom)
    score = 0
    for position, element in expected.items():
        candidates = atoms_by_pos.get(position, [])
        if len(candidates) == 1:
            score += 20
            if candidates[0].element == element:
                score += 100
            if not candidates[0].held_by:
                score += 5
    expected_bond_set = {(kind, tuple(sorted((a, b)))) for kind, a, b in expected_bonds}
    for bond in simulator.world.bonds.values():
        if simulator._is_wheel_atom_id(bond.a) or simulator._is_wheel_atom_id(bond.b):
            continue
        a = simulator.world.atoms[bond.a].position
        b = simulator.world.atoms[bond.b].position
        signature = (bond.kind, tuple(sorted((a, b))))
        score += 80 if signature in expected_bond_set else -35
    central = atoms_by_pos.get((3, -2), [])
    if len(central) == 1 and central[0].element == "salt":
        score += 150
    output_cells = set(expected)
    score -= 3 * sum(1 for atom in ordinary_atoms(simulator) if atom.position not in output_cells)
    return score


def snapshot(simulator: Simulator):
    atoms = [
        {
            "id": atom.id,
            "element": atom.element,
            "position": list(atom.position),
            "heldBy": sorted(atom.held_by),
        }
        for atom in ordinary_atoms(simulator)
    ]
    bonds = [
        {
            "a": bond.a,
            "b": bond.b,
            "kind": bond.kind,
            "aPosition": list(simulator.world.atoms[bond.a].position),
            "bPosition": list(simulator.world.atoms[bond.b].position),
        }
        for bond in simulator.world.bonds.values()
        if not simulator._is_wheel_atom_id(bond.a) and not simulator._is_wheel_atom_id(bond.b)
    ]
    return {
        "cycle": simulator.world.cycle,
        "score": output_score(simulator),
        "delivered": dict(simulator.delivered_products),
        "atoms": sorted(atoms, key=lambda item: item["id"]),
        "bonds": sorted(bonds, key=lambda item: (item["a"], item["b"])),
        "arms": {arm_id: arm.snapshot() for arm_id, arm in simulator.arms.items()},
    }


def main() -> None:
    puzzle = json.loads(PUZZLE.read_text(encoding="utf-8"))
    solution = parse_solution_bytes(base64.b64decode(REFERENCE_B64.read_text(encoding="ascii")))
    simulator = Simulator.from_models(puzzle, solution)
    for row in build_program_timeline(solution).get("cycles", []):
        instructions = {str(event.get("partId")): event.get("instruction") for event in row.get("events", [])}
        simulator.step(instructions)

    output_id = simulator.output_patterns[0][0]
    action_options = {}
    for arm_id, arm in sorted(simulator.arms.items()):
        if arm.part_type == "piston":
            action_options[arm_id] = (None, "grab", "drop", "rotate_cw", "rotate_ccw", "pivot_cw", "pivot_ccw", "extend", "retract", "track_plus", "track_minus")
        elif arm.part_type == "baron":
            action_options[arm_id] = (None, "rotate_cw", "rotate_ccw", "drop")

    result = explore_simulator_beam(
        simulator,
        action_options,
        lambda state: state.delivered_products.get(output_id, 0) > 0,
        output_score,
        max_depth=28,
        beam_width=3000,
        max_states=750000,
        max_active_arms=2,
        include_idle=False,
        time_limit_seconds=5400,
    )
    print(json.dumps({
        "sourceSha256": solution.get("source", {}).get("sha256"),
        "start": snapshot(simulator),
        "result": {
            "found": result.found,
            "actions": result.actions,
            "visitedStates": result.visited_states,
            "expandedStates": result.expanded_states,
            "depth": result.depth,
            "stoppedReason": result.stopped_reason,
            "bestScore": result.best_score,
            "best": snapshot(result.simulator) if result.simulator is not None else None,
        },
    }, indent=2))


if __name__ == "__main__":
    main()
