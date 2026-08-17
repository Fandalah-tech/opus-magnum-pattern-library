from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_parser import parse_puzzle
from packages.opus_solver import puzzle_file_id


def _molecule_profile(molecule: dict[str, Any]) -> dict[str, Any]:
    atoms = molecule.get("atoms") or []
    bonds = molecule.get("bonds") or []
    elements = Counter(str(atom.get("element") or "unknown") for atom in atoms)
    bond_types = Counter(str(bond.get("type") or "normal") for bond in bonds)

    positions = {tuple(atom.get("position") or ()) for atom in atoms}
    adjacency = {position: set() for position in positions}
    for bond in bonds:
        start = tuple(bond.get("from") or ())
        end = tuple(bond.get("to") or ())
        if start in adjacency and end in adjacency:
            adjacency[start].add(end)
            adjacency[end].add(start)

    components = 0
    unseen = set(positions)
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, ()):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)

    return {
        "atomCount": len(atoms),
        "bondCount": len(bonds),
        "elements": dict(sorted(elements.items())),
        "bondTypes": dict(sorted(bond_types.items())),
        "connectedComponents": components,
    }


def _shape_key(target: dict[str, Any]) -> str:
    reagent_shapes = sorted(
        (item["atomCount"], item["bondCount"], item["connectedComponents"])
        for item in target["reagents"]
    )
    product_shapes = sorted(
        (item["atomCount"], item["bondCount"], item["connectedComponents"])
        for item in target["products"]
    )
    return json.dumps(
        {
            "reagents": reagent_shapes,
            "products": product_shapes,
            "production": target["production"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def profile_collection(collection_root: Path) -> dict[str, Any]:
    puzzle_paths = sorted(collection_root.rglob("*.puzzle"))
    targets: list[dict[str, Any]] = []
    reagent_counts: Counter[str] = Counter()
    product_counts: Counter[str] = Counter()
    reagent_atom_vectors: Counter[str] = Counter()
    product_atom_vectors: Counter[str] = Counter()
    shape_counts: Counter[str] = Counter()
    glyph_sets: Counter[str] = Counter()
    arm_sets: Counter[str] = Counter()
    production_counts: Counter[str] = Counter()

    for path in puzzle_paths:
        puzzle = parse_puzzle(path)
        reagents = [_molecule_profile(item) for item in (puzzle.get("reagents") or [])]
        products = [_molecule_profile(item) for item in (puzzle.get("products") or [])]
        parts = puzzle.get("availableParts") or {}
        glyphs = sorted(str(value) for value in (parts.get("glyphs") or []))
        arms = sorted(str(value) for value in (parts.get("arms") or []))
        target = {
            "source": path.name,
            "targetPuzzleId": puzzle_file_id(puzzle),
            "name": puzzle.get("name"),
            "production": bool(puzzle.get("production")),
            "reagentCount": len(reagents),
            "productCount": len(products),
            "reagents": reagents,
            "products": products,
            "availableGlyphs": glyphs,
            "availableArms": arms,
        }
        targets.append(target)

        reagent_counts[str(len(reagents))] += 1
        product_counts[str(len(products))] += 1
        reagent_atom_vectors[json.dumps(sorted(item["atomCount"] for item in reagents))] += 1
        product_atom_vectors[json.dumps(sorted(item["atomCount"] for item in products))] += 1
        shape_counts[_shape_key(target)] += 1
        glyph_sets[",".join(glyphs)] += 1
        arm_sets[",".join(arms)] += 1
        production_counts[str(bool(puzzle.get("production"))).lower()] += 1

    return {
        "schemaVersion": "0.1.0",
        "kind": "external-puzzle-chemistry-profile",
        "collectionRoot": str(collection_root),
        "targetSolutionBytesUsed": 0,
        "summary": {
            "puzzleCount": len(targets),
            "reagentCountCounts": dict(sorted(reagent_counts.items())),
            "productCountCounts": dict(sorted(product_counts.items())),
            "reagentAtomVectorCounts": dict(reagent_atom_vectors.most_common()),
            "productAtomVectorCounts": dict(product_atom_vectors.most_common()),
            "shapeCounts": dict(shape_counts.most_common()),
            "glyphSetCounts": dict(glyph_sets.most_common()),
            "armSetCounts": dict(arm_sets.most_common()),
            "productionCounts": dict(sorted(production_counts.items())),
        },
        "targets": targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile chemistry of an external puzzle-only collection.")
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = profile_collection(args.collection_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
