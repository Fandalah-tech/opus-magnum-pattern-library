from packages.opus_analysis.replay_glyphs import process_basic_glyphs


def _atom(molecule_id, atom_id, element, position):
    return {
        "id": molecule_id,
        "heldBy": [],
        "atoms": [{"id": atom_id, "element": element, "position": list(position)}],
        "bonds": [],
    }


def test_bonder_merges_two_molecules_and_creates_bond():
    molecules = [
        _atom("left", "a", "salt", [0, 0]),
        _atom("right", "b", "salt", [1, 0]),
    ]
    solution = {"parts": [{"id": "g", "type": "bonder", "position": [0, 0], "rotation": 0}]}

    events = process_basic_glyphs(solution, molecules, {})

    assert len(molecules) == 1
    assert len(molecules[0]["atoms"]) == 2
    assert len(molecules[0]["bonds"]) == 1
    assert events[0]["effect"] == "bond-created"


def test_unbonder_removes_bond_and_splits_molecule():
    molecules = [{
        "id": "joined",
        "heldBy": [],
        "atoms": [
            {"id": "a", "element": "salt", "position": [0, 0]},
            {"id": "b", "element": "salt", "position": [1, 0]},
        ],
        "bonds": [{"id": "bond", "type": "normal", "from": [0, 0], "to": [1, 0]}],
    }]
    solution = {"parts": [{"id": "u", "type": "unbonder", "position": [0, 0], "rotation": 0}]}

    events = process_basic_glyphs(solution, molecules, {})

    assert len(molecules) == 2
    assert all(not molecule["bonds"] for molecule in molecules)
    assert events[0]["effect"] == "bond-removed"


def test_calcification_changes_classical_element_to_salt():
    molecules = [_atom("m", "a", "fire", [4, -2])]
    solution = {"parts": [{"id": "c", "type": "glyph-calcification", "position": [4, -2], "rotation": 3}]}

    events = process_basic_glyphs(solution, molecules, {})

    assert molecules[0]["atoms"][0]["element"] == "salt"
    assert events == [{
        "kind": "glyph-effect",
        "glyphType": "glyph-calcification",
        "glyphPartId": "c",
        "effect": "calcify",
        "moleculeId": "m",
        "position": [4, -2],
        "fromElement": "fire",
        "toElement": "salt",
    }]


def test_calcification_ignores_nonclassical_elements():
    molecules = [_atom("m", "a", "gold", [0, 0])]
    solution = {"parts": [{"id": "c", "type": "glyph-calcification", "position": [0, 0], "rotation": 0}]}

    events = process_basic_glyphs(solution, molecules, {})

    assert molecules[0]["atoms"][0]["element"] == "gold"
    assert events == []


def test_bonder_respects_glyph_rotation():
    molecules = [
        _atom("left", "a", "salt", [2, 2]),
        _atom("right", "b", "salt", [2, 3]),
    ]
    solution = {"parts": [{"id": "g", "type": "bonder", "position": [2, 2], "rotation": 1}]}

    events = process_basic_glyphs(solution, molecules, {})

    assert len(molecules) == 1
    assert events[0]["positions"] == [[2, 2], [2, 3]]
