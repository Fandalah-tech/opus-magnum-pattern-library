from packages.opus_analysis import extract_solution_fragments, functional_role


def _part(part_id, part_type, position, *, length=1, program=None, rotation=0):
    return {
        "id": part_id,
        "type": part_type,
        "enabled": True,
        "position": list(position),
        "length": length,
        "rotation": rotation,
        "which": 0,
        "armNumber": 0,
        "program": program or [],
    }


def test_functional_role_classification():
    assert functional_role("input") == "feed"
    assert functional_role("out-std") == "output"
    assert functional_role("bonder") == "bonding"
    assert functional_role("bonder-prisma") == "bonding"
    assert functional_role("purification") == "conversion"
    assert functional_role("disposal") == "disposal"
    assert functional_role("pipe") == "conduit"
    assert functional_role("glyph-unification") == "conversion"
    assert functional_role("arm1") is None
    assert functional_role("track") is None


def test_fragment_collects_reaching_arm():
    solution = {
        "puzzleFile": "P001",
        "parts": [
            _part("arm", "arm1", (0, 0), program=[{"cycle": 1, "instruction": "grab"}]),
            _part("bond", "bonder", (1, 0)),
            _part("far-output", "out-std", (8, 0)),
        ],
    }

    fragments = extract_solution_fragments(solution)
    bonding = next(fragment for fragment in fragments if fragment["role"] == "bonding")
    output = next(fragment for fragment in fragments if fragment["role"] == "output")

    assert bonding["memberPartIds"] == ["arm", "bond"]
    assert bonding["summary"]["armCount"] == 1
    assert bonding["summary"]["instructionCount"] == 1
    assert bonding["geometry"]["sourceAnchorPartId"] == "bond"
    assert {
        part["sourcePartId"] for part in bonding["geometry"]["parts"]
    } == {"arm", "bond"}
    assert output["memberPartIds"] == ["far-output"]


def test_fragment_mechanism_hash_is_translation_invariant_and_cross_puzzle():
    left = {
        "puzzleFile": "P001",
        "parts": [
            _part("a", "arm1", (0, 0), program=[{"cycle": 5, "instruction": "grab"}]),
            _part("b", "bonder", (1, 0)),
        ],
    }
    right = {
        "puzzleFile": "P999",
        "parts": [
            _part("x", "arm1", (10, -4), program=[{"cycle": 17, "instruction": "grab"}]),
            _part("y", "bonder", (11, -4)),
        ],
    }

    left_fragment = next(fragment for fragment in extract_solution_fragments(left) if fragment["role"] == "bonding")
    right_fragment = next(fragment for fragment in extract_solution_fragments(right) if fragment["role"] == "bonding")

    assert left_fragment["canonicalMechanismHash"] == right_fragment["canonicalMechanismHash"]
    assert left_fragment["canonicalStructuralHash"] != right_fragment["canonicalStructuralHash"]


def test_unknown_non_transfer_part_is_kept_as_process_anchor():
    solution = {"puzzleFile": "P001", "parts": [_part("mystery", "future-glyph", (0, 0))]}

    fragments = extract_solution_fragments(solution)

    assert len(fragments) == 1
    assert fragments[0]["role"] == "process"
