from __future__ import annotations

import base64
import itertools
import json
from copy import deepcopy
from pathlib import Path

from packages.opus_analysis import build_program_timeline
from packages.opus_engine.final_simulator import Simulator
from packages.opus_engine.simulator import SimulationError
from packages.opus_engine.builder import rotate_hex
from packages.opus_parser.solution import parse_solution_bytes

PUZZLE = Path("fixtures/puzzles/van-berlos-rotor.parsed.json")
REFERENCE_B64 = Path("fixtures/solutions/van-berlos-rotor-area47-ideal-setup-9-almost-solved.solution.b64")
EDITABLE_CYCLES = (136, 144, 157)
CHOICES = (None, "rotate_cw", "rotate_ccw")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_reference() -> dict:
    raw = base64.b64decode(REFERENCE_B64.read_text(encoding="ascii"))
    return parse_solution_bytes(raw, source_name="van-berlos-rotor-area47-almost-solved.solution")


def canon_edge(a, b):
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


def score_state(simulator: Simulator, product: dict) -> dict:
    atoms = {aid: atom for aid, atom in simulator.world.atoms.items() if "-wheel-" not in aid}
    target_atoms = [(tuple(atom["position"]), atom["element"]) for atom in product["atoms"]]
    target_edges = {canon_edge(tuple(b["from"]), tuple(b["to"])) for b in product.get("bonds", [])}
    world_edges = {
        canon_edge(atoms[bond.a].position, atoms[bond.b].position)
        for bond in simulator.world.bonds.values()
        if bond.a in atoms and bond.b in atoms
    }
    by_pos = {}
    for atom in atoms.values():
        by_pos.setdefault(atom.position, []).append(atom)
    best = {"typedAtoms": 0, "occupiedPositions": 0, "correctBonds": 0, "wrongElements": 13, "rotation": 0, "translation": [0, 0]}
    for rotation in range(6):
        rotated_atoms = [(rotate_hex(pos, rotation), element) for pos, element in target_atoms]
        rotated_edges = {canon_edge(rotate_hex(a, rotation), rotate_hex(b, rotation)) for a, b in target_edges}
        translations = {
            (world.position[0] - target[0], world.position[1] - target[1])
            for world in atoms.values() for target, _ in rotated_atoms
        }
        for tq, tr in translations:
            typed = occupied = wrong = 0
            for (q, r), element in rotated_atoms:
                occupants = by_pos.get((q + tq, r + tr), [])
                if occupants:
                    occupied += 1
                    if any(atom.element == element for atom in occupants): typed += 1
                    else: wrong += 1
            shifted_edges = {
                canon_edge((a[0] + tq, a[1] + tr), (b[0] + tq, b[1] + tr))
                for a, b in rotated_edges
            }
            bonds = len(shifted_edges & world_edges)
            candidate = {"typedAtoms": typed, "occupiedPositions": occupied, "correctBonds": bonds, "wrongElements": wrong, "rotation": rotation, "translation": [tq, tr]}
            if (typed, bonds, occupied, -wrong) > (best["typedAtoms"], best["correctBonds"], best["occupiedPositions"], -best["wrongElements"]):
                best = candidate
    return best


def main() -> None:
    puzzle = load_json(PUZZLE)
    reference = load_reference()
    product = puzzle["products"][0]
    ranked = []
    for choices in itertools.product(CHOICES, repeat=len(EDITABLE_CYCLES)):
        solution = deepcopy(reference)
        set_baron_program(solution, choices)
        simulator = Simulator.from_models(puzzle, solution)
        error = None
        try:
            simulator.run_timeline(build_program_timeline(solution))
        except SimulationError as exc:
            error = str(exc)
        match = score_state(simulator, product)
        delivered = dict(getattr(simulator, "delivered_products", {}))
        record = {
            "choices": {str(c): i for c, i in zip(EDITABLE_CYCLES, choices, strict=True)},
            "completedCycles": simulator.world.cycle,
            "delivered": delivered,
            **match,
            "error": error,
        }
        record["score"] = sum(delivered.values()) * 10000000 + match["typedAtoms"] * 100000 + match["correctBonds"] * 10000 + match["occupiedPositions"] * 100 - match["wrongElements"] * 10 + simulator.world.cycle
        ranked.append(record)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    successes = [r for r in ranked if r["delivered"] or (r["typedAtoms"] == 13 and r["correctBonds"] == 6)]
    print(json.dumps({
        "reference": reference.get("name"),
        "referenceSha256": reference.get("source", {}).get("sha256"),
        "editableCycles": list(EDITABLE_CYCLES),
        "variants": len(ranked),
        "successes": successes,
        "top": ranked[:27],
    }, indent=2))


if __name__ == "__main__":
    main()
