from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver import StructureGoal
from packages.opus_solver.rotor_prefix import build_locked_prefix_simulator


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
PREFIX = Path("fixtures/solutions/van-berlos-rotor-area43-half-complete.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    puzzle = _load(PUZZLE)
    simulator = build_locked_prefix_simulator(puzzle, _load(PREFIX))
    goal = StructureGoal.from_product(puzzle["products"][0])
    match = goal.best_match(simulator)
    eligible = goal._eligible_atom_ids(simulator)

    print(f"cycle={simulator.world.cycle}")
    print(
        "structure:",
        f"eligibleAtoms={len(eligible)}",
        f"targetAtoms={goal.atom_count}",
        f"matchedPositions={match.occupied_positions}",
        f"matchedEdges={match.matched_edges}",
        f"targetEdges={goal.bond_count}",
        f"rotation={match.rotation}",
        f"translation={match.translation}",
    )
    print("arms:")
    for arm in sorted(simulator.arms.values(), key=lambda item: item.id):
        print(
            arm.id,
            f"origin={arm.origin}",
            f"rotation={arm.rotation}",
            f"length={arm.length}",
            f"track={arm.track_index}",
            f"grabbing={arm.grabbing}",
            f"held={dict(sorted(arm.held_atoms.items()))}",
        )
    print("atoms:")
    for atom in sorted(simulator.world.atoms.values(), key=lambda item: (item.position, item.id)):
        print(
            atom.id,
            atom.element,
            atom.position,
            f"eligible={atom.id in eligible}",
            f"held={sorted(atom.held_by)}",
        )
    print("bonds:")
    for bond in sorted(simulator.world.bonds.values(), key=lambda item: (item.a, item.b, item.kind)):
        print(bond.a, bond.b, bond.kind)
    print("molecules:")
    for molecule in simulator.world.molecules():
        print(sorted(molecule.atom_ids))


if __name__ == "__main__":
    main()
