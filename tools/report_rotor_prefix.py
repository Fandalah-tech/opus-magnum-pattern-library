from __future__ import annotations

import json
from pathlib import Path

from packages.opus_solver.rotor_prefix import build_locked_prefix_simulator


PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
PREFIX = Path("fixtures/solutions/van-berlos-rotor-area42-corrected-prefix.parsed.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    simulator = build_locked_prefix_simulator(_load(PUZZLE), _load(PREFIX))
    print(f"cycle={simulator.world.cycle}")
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
        print(atom.id, atom.element, atom.position, f"held={sorted(atom.held_by)}")
    print("bonds:")
    for bond in sorted(simulator.world.bonds.values(), key=lambda item: (item.a, item.b, item.kind)):
        print(bond.a, bond.b, bond.kind)
    print("molecules:")
    for molecule in simulator.world.molecules():
        print(sorted(molecule.atom_ids))


if __name__ == "__main__":
    main()
