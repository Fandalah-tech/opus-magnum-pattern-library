from packages.opus_analysis.puzzle_features import (
    canonical_molecule_hash,
    puzzle_feature_fingerprint,
    puzzle_feature_payload,
)


def molecule(atoms, bonds):
    return {
        "atoms": [
            {"id": f"a{index}", "element": element, "position": [q, r]}
            for index, (q, r, element) in enumerate(atoms)
        ],
        "bonds": [
            {"type": bond_type, "from": list(start), "to": list(end)}
            for bond_type, start, end in bonds
        ],
    }


def rotate(position):
    q, r = position
    return -r, q + r


def test_molecule_hash_is_translation_and_rotation_invariant():
    original_atoms = [(0, 0, "salt"), (1, 0, "fire"), (1, -1, "water")]
    original_bonds = [
        ("normal", (0, 0), (1, 0)),
        ("normal", (1, 0), (1, -1)),
    ]
    original = molecule(original_atoms, original_bonds)

    shifted_rotated_atoms = []
    for q, r, element in original_atoms:
        rq, rr = rotate((q, r))
        shifted_rotated_atoms.append((rq + 7, rr - 4, element))
    shifted_rotated_bonds = []
    for bond_type, start, end in original_bonds:
        a = rotate(start)
        b = rotate(end)
        shifted_rotated_bonds.append((bond_type, (a[0] + 7, a[1] - 4), (b[0] + 7, b[1] - 4)))
    transformed = molecule(shifted_rotated_atoms, shifted_rotated_bonds)

    assert canonical_molecule_hash(original) == canonical_molecule_hash(transformed)


def test_puzzle_feature_payload_summarizes_solver_relevant_constraints():
    reagent = molecule([(0, 0, "salt"), (1, 0, "fire")], [("normal", (0, 0), (1, 0))])
    product = molecule([(0, 0, "salt")], [])
    puzzle = {
        "production": False,
        "outputScale": 1,
        "availableParts": {"arms": ["arm1", "piston"], "glyphs": ["bonder", "unbonder"]},
        "reagents": [reagent],
        "products": [product],
    }

    payload = puzzle_feature_payload(puzzle)

    assert payload["production"] is False
    assert payload["availableArms"] == ["arm1", "piston"]
    assert payload["reagents"]["elements"] == {"fire": 1, "salt": 1}
    assert payload["reagents"]["bondVariants"] == {"normal": 1}
    assert payload["products"]["atomCounts"] == [1]
    assert len(payload["reagents"]["moleculeSignatures"]) == 1
    assert len(puzzle_feature_fingerprint(puzzle)) == 64


def test_molecule_hash_preserves_exact_triplex_channels():
    atoms = [(0, 0, "fire"), (1, 0, "fire")]

    def triplex(channels, raw_code):
        value = molecule(atoms, [("triplex", (0, 0), (1, 0))])
        value["bonds"][0].update({
            "rawCode": raw_code,
            "triplexChannels": list(channels),
        })
        return value

    red = triplex(["red"], 2)
    yellow = triplex(["yellow"], 8)
    combined = triplex(["red", "black", "yellow"], 14)

    assert len({
        canonical_molecule_hash(red),
        canonical_molecule_hash(yellow),
        canonical_molecule_hash(combined),
    }) == 3

    payload = puzzle_feature_payload({
        "reagents": [red, yellow, combined],
        "products": [],
    })
    assert payload["reagents"]["bonds"] == {"triplex": 3}
    assert payload["reagents"]["bondVariants"] == {
        "triplex:red": 1,
        "triplex:red+black+yellow": 1,
        "triplex:yellow": 1,
    }
