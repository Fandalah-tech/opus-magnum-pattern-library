from __future__ import annotations

import itertools
import json
from copy import deepcopy
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import FinalSimulator, SimulationError
from packages.opus_engine.builder import rotate_hex

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-near-complete.parsed.json")
EDITABLE_CYCLES = (11, 35, 51, 88, 89, 90, 145)
CHOICES = (None, "rotate_cw", "rotate_ccw")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canon_edge(a: tuple[int, int], b: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    return (a, b) if a <= b else (b, a)


def set_baron_program(solution: dict, choices: tuple[str | None, ...]) -> None:
    baron = next(part for part in solution["parts"] if part["type"] == "baron")
    preserved = [row for row in baron.get("program", []) if row["cycle"] not in EDITABLE_CYCLES]
    replacements = [
        {"cycle": cycle, "instruction": instruction}
        for cycle, instruction in zip(EDITABLE_CYCLES, choices, strict=True)
        if instruction is not None
    ]
    baron["program"] = sorted(preserved + replacements, key=lambda row: row["cycle"])


def score_state(simulator: FinalSimulator, product: dict) -> dict:
    world_atoms = {
        atom_id: atom
        for atom_id, atom in simulator.world.atoms.items()
        if "-wheel-" not in atom_id
    }
    target_atoms = [(tuple(atom["position"]), atom["element"]) for atom in product["atoms"]]
    target_edges = {
        canon_edge(tuple(bond["from"]), tuple(bond["to"]))
        for bond in product.get("bonds", [])
    }
    world_edges = {
        canon_edge(world_atoms[bond.a].position, world_atoms[bond.b].position)
        for bond in simulator.world.bonds.values()
        if bond.a in world_atoms and bond.b in world_atoms
    }

    best = {
        "typedAtoms": 0,
        "occupiedPositions": 0,
        "correctBonds": 0,
        "wrongElements": 0,
        "translation": [0, 0],
        "rotation": 0,
    }
    world_by_position: dict[tuple[int, int], list] = {}
    for atom in world_atoms.values():
        world_by_position.setdefault(atom.position, []).append(atom)

    for rotation in range(6):
        rotated_atoms = [(rotate_hex(position, rotation), element) for position, element in target_atoms]
        rotated_edges = {
            canon_edge(rotate_hex(a, rotation), rotate_hex(b, rotation))
            for a, b in target_edges
        }
        translations = {
            (world.position[0] - target[0], world.position[1] - target[1])
            for world in world_atoms.values()
            for target, _element in rotated_atoms
        }
        for tq, tr in translations:
            typed = 0
            occupied = 0
            wrong = 0
            shifted_positions = set()
            for (q, r), element in rotated_atoms:
                position = (q + tq, r + tr)
                shifted_positions.add(position)
                occupants = world_by_position.get(position, [])
                if occupants:
                    occupied += 1
                    if any(atom.element == element for atom in occupants):
                        typed += 1
                    else:
                        wrong += 1
            shifted_edges = {
                canon_edge((a[0] + tq, a[1] + tr), (b[0] + tq, b[1] + tr))
                for a, b in rotated_edges
            }
            bonds = len(shifted_edges & world_edges)
            candidate = {
                "typedAtoms": typed,
                "occupiedPositions": occupied,
                "correctBonds": bonds,
                "wrongElements": wrong,
                "translation": [tq, tr],
                "rotation": rotation,
            }
            key = (typed, bonds, occupied, -wrong)
            old = (best["typedAtoms"], best["correctBonds"], best["occupiedPositions"], -best["wrongElements"])
            if key > old:
                best = candidate
    return best


def main() -> None:
    puzzle = load(PUZZLE)
    reference = load(REFERENCE)
    product = puzzle["products"][0]
    ranked = []
    successes = []

    for choices in itertools.product(CHOICES, repeat=len(EDITABLE_CYCLES)):
        solution = deepcopy(reference)
        set_baron_program(solution, choices)
        simulator = FinalSimulator.from_models(puzzle, solution)
        timeline = build_program_timeline(solution)
        error = None
        try:
            simulator.run_timeline(timeline)
        except SimulationError as exc:
            error = str(exc)
        match = score_state(simulator, product)
        delivered = dict(getattr(simulator, "delivered_products", {}))
        record = {
            "choices": {str(cycle): instruction for cycle, instruction in zip(EDITABLE_CYCLES, choices, strict=True)},
            "completedCycles": simulator.world.cycle,
            "delivered": delivered,
            **match,
            "error": error,
        }
        record["score"] = (
            sum(delivered.values()) * 10_000_000
            + match["typedAtoms"] * 100_000
            + match["correctBonds"] * 10_000
            + match["occupiedPositions"] * 100
            - match["wrongElements"] * 10
            + simulator.world.cycle
        )
        ranked.append(record)
        if delivered or (match["typedAtoms"] == 13 and match["correctBonds"] == 6):
            successes.append(record)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    print(json.dumps({
        "reference": reference.get("name"),
        "referenceSha256": reference.get("source", {}).get("sha256"),
        "editableCycles": list(EDITABLE_CYCLES),
        "variants": len(ranked),
        "successes": successes[:20],
        "top": ranked[:30],
    }, indent=2))


if __name__ == "__main__":
    main()
