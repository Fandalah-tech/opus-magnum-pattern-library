from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import SimulationError, Simulator
from packages.opus_engine.builder import rotate_hex
from packages.opus_solver import StructureGoal

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9.parsed.json")
ROTATION_CYCLES = (11, 19, 35, 72, 73, 74)
CHOICES = (None, "rotate_cw", "rotate_ccw")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def typed_match(simulator: Simulator, product: dict) -> tuple[int, int, int, tuple[int, int]]:
    target_atoms = [(tuple(atom["position"]), atom["element"]) for atom in product["atoms"]]
    target_bonds = {
        tuple(sorted((tuple(bond["from"]), tuple(bond["to"]))))
        for bond in product.get("bonds", [])
    }
    live_atoms = [(atom.position, atom.element) for atom in simulator.world.atoms.values() if "-wheel-" not in atom.id]
    live_bonds = {
        tuple(sorted((simulator.world.atoms[bond.a].position, simulator.world.atoms[bond.b].position)))
        for bond in simulator.world.bonds.values()
        if "-wheel-" not in bond.a and "-wheel-" not in bond.b
    }
    best = (0, 0, 0, (0, 0))
    if not live_atoms:
        return best
    for rotation in range(6):
        rotated = [(rotate_hex(pos, rotation), element) for pos, element in target_atoms]
        rotated_bonds = {
            tuple(sorted((rotate_hex(a, rotation), rotate_hex(b, rotation))))
            for a, b in target_bonds
        }
        for live_pos, _ in live_atoms:
            for target_pos, _ in rotated:
                translation = (live_pos[0] - target_pos[0], live_pos[1] - target_pos[1])
                shifted_atoms = {((pos[0] + translation[0], pos[1] + translation[1]), element) for pos, element in rotated}
                atom_score = len(shifted_atoms.intersection(set(live_atoms)))
                shifted_bonds = {
                    tuple(sorted(((a[0] + translation[0], a[1] + translation[1]), (b[0] + translation[0], b[1] + translation[1]))))
                    for a, b in rotated_bonds
                }
                bond_score = len(shifted_bonds.intersection(live_bonds))
                candidate = (atom_score, bond_score, rotation, translation)
                if candidate[:2] > best[:2]:
                    best = candidate
    return best


def variant_solution(reference: dict, choices: tuple[str | None, ...]) -> dict:
    solution = copy.deepcopy(reference)
    baron = next(part for part in solution["parts"] if part["type"] == "baron")
    fixed = [row for row in baron.get("program", []) if row["cycle"] not in ROTATION_CYCLES]
    selected = [
        {"cycle": cycle, "instruction": instruction}
        for cycle, instruction in zip(ROTATION_CYCLES, choices, strict=True)
        if instruction is not None
    ]
    baron["program"] = sorted(fixed + selected, key=lambda row: row["cycle"])
    return solution


def main() -> None:
    puzzle = load(PUZZLE)
    reference = load(REFERENCE)
    product = puzzle["products"][0]
    geometry_goal = StructureGoal.from_product(product, include_baron_held=False)
    ranked = []
    successes = []

    for choices in itertools.product(CHOICES, repeat=len(ROTATION_CYCLES)):
        solution = variant_solution(reference, choices)
        simulator = Simulator.from_models(puzzle, solution)
        timeline = build_program_timeline(solution)
        error = None
        try:
            simulator.run_timeline(timeline)
        except SimulationError as exc:
            error = str(exc)
        match = geometry_goal.best_match(simulator)
        atoms, typed_bonds, rotation, translation = typed_match(simulator, product)
        delivered = dict(getattr(simulator, "delivered", {}))
        score = (
            sum(delivered.values()) * 1_000_000
            + atoms * 10_000
            + typed_bonds * 1_000
            + match.occupied_positions * 100
            + match.matched_edges * 20
            + simulator.world.cycle
        )
        row = {
            "choices": dict(zip(ROTATION_CYCLES, choices, strict=True)),
            "completedCycles": simulator.world.cycle,
            "delivered": delivered,
            "typedAtoms": atoms,
            "typedBonds": typed_bonds,
            "geometryPositions": match.occupied_positions,
            "geometryBonds": match.matched_edges,
            "rotation": rotation,
            "translation": list(translation),
            "error": error,
            "score": score,
        }
        ranked.append(row)
        if delivered or (atoms == 13 and typed_bonds == 6):
            successes.append(row)

    ranked.sort(key=lambda row: row["score"], reverse=True)
    print(json.dumps({
        "reference": reference.get("name"),
        "variants": len(ranked),
        "successes": successes[:20],
        "top": ranked[:30],
    }, indent=2))


if __name__ == "__main__":
    main()
