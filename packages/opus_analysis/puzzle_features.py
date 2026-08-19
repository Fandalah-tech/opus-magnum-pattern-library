from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from packages.opus_parser import canonical_bond_identity


def _rotate(position: tuple[int, int], steps: int) -> tuple[int, int]:
    q, r = position
    for _ in range(steps % 6):
        q, r = -r, q + r
    return q, r


def _canonical_molecule_payload(molecule: dict[str, Any]) -> dict[str, Any]:
    atoms = [
        (int(atom["position"][0]), int(atom["position"][1]), str(atom["element"]))
        for atom in molecule.get("atoms", [])
    ]
    bonds = [
        (
            canonical_bond_identity(bond),
            (int(bond["from"][0]), int(bond["from"][1])),
            (int(bond["to"][0]), int(bond["to"][1])),
        )
        for bond in molecule.get("bonds", [])
    ]

    variants = []
    for steps in range(6):
        rotated_atoms = [(*_rotate((q, r), steps), element) for q, r, element in atoms]
        if rotated_atoms:
            anchor = min((q, r) for q, r, _ in rotated_atoms)
        else:
            anchor = (0, 0)
        aq, ar = anchor
        normalized_atoms = sorted((q - aq, r - ar, element) for q, r, element in rotated_atoms)

        normalized_bonds = []
        for bond_type, start, end in bonds:
            sq, sr = _rotate(start, steps)
            eq, er = _rotate(end, steps)
            a = (sq - aq, sr - ar)
            b = (eq - aq, er - ar)
            if b < a:
                a, b = b, a
            normalized_bonds.append((bond_type, a[0], a[1], b[0], b[1]))
        normalized_bonds.sort()
        variants.append({"atoms": normalized_atoms, "bonds": normalized_bonds})

    return min(variants, key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")))


def canonical_molecule_hash(molecule: dict[str, Any]) -> str:
    payload = _canonical_molecule_payload(molecule)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _molecule_summary(molecules: list[dict[str, Any]]) -> dict[str, Any]:
    elements: Counter[str] = Counter()
    bonds: Counter[str] = Counter()
    bond_variants: Counter[str] = Counter()
    atom_counts = []
    bond_counts = []
    signatures = []

    for molecule in molecules:
        atom_counts.append(len(molecule.get("atoms", [])))
        bond_counts.append(len(molecule.get("bonds", [])))
        signatures.append(canonical_molecule_hash(molecule))
        for atom in molecule.get("atoms", []):
            elements[str(atom.get("element") or "unknown")] += 1
        for bond in molecule.get("bonds", []):
            bonds[str(bond.get("type") or "normal")] += 1
            bond_variants[canonical_bond_identity(bond)] += 1

    return {
        "count": len(molecules),
        "atomCounts": sorted(atom_counts),
        "bondCounts": sorted(bond_counts),
        "elements": dict(sorted(elements.items())),
        "bonds": dict(sorted(bonds.items())),
        "bondVariants": dict(sorted(bond_variants.items())),
        "moleculeSignatures": sorted(signatures),
    }


def puzzle_feature_payload(puzzle: dict[str, Any]) -> dict[str, Any]:
    available = puzzle.get("availableParts", {})
    return {
        "production": bool(puzzle.get("production")),
        "outputScale": puzzle.get("outputScale"),
        "availableArms": sorted(str(value) for value in available.get("arms", [])),
        "availableGlyphs": sorted(str(value) for value in available.get("glyphs", [])),
        "reagents": _molecule_summary(list(puzzle.get("reagents", []))),
        "products": _molecule_summary(list(puzzle.get("products", []))),
    }


def puzzle_feature_fingerprint(puzzle: dict[str, Any]) -> str:
    payload = puzzle_feature_payload(puzzle)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
