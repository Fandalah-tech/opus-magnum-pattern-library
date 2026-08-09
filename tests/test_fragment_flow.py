from packages.opus_analysis import build_fragment_flow_graph, functional_role


def _single_atom(element):
    return {"atoms": [{"id": "a0", "element": element, "position": [0, 0]}], "bonds": []}


def test_parser_glyph_names_map_to_expected_fragment_roles():
    assert functional_role("glyph-calcification") == "conversion"
    assert functional_role("glyph-disposal") == "disposal"
    assert functional_role("glyph-duplication") == "conversion"
    assert functional_role("glyph-projection") == "conversion"


def test_bonder_creates_two_feed_to_bonding_flow_edges():
    puzzle = {
        "reagents": [_single_atom("salt"), _single_atom("salt")],
        "products": [],
    }
    solution = {
        "puzzleFile": "flow-test.puzzle",
        "source": {"sha256": "abc"},
        "parts": [
            {"id": "in-a", "type": "input", "position": [0, 0], "rotation": 0, "which": 0, "program": [], "length": 1},
            {"id": "in-b", "type": "input", "position": [1, 0], "rotation": 0, "which": 1, "program": [], "length": 1},
            {"id": "bond", "type": "bonder", "position": [0, 0], "rotation": 0, "which": 0, "program": [], "length": 1},
            {"id": "clock", "type": "arm1", "position": [10, 10], "rotation": 0, "which": 0, "program": [{"cycle": 0, "instruction": "drop"}], "length": 1, "armNumber": 1},
        ],
    }

    graph = build_fragment_flow_graph(puzzle, solution)

    edges = {(edge["sourceAnchorPartId"], edge["targetAnchorPartId"], edge["relation"]) for edge in graph["edges"]}
    assert ("in-a", "bond", "bond-created") in edges
    assert ("in-b", "bond", "bond-created") in edges
    assert graph["summary"]["flowObservationCount"] == 2


def test_flow_nodes_preserve_fragment_mechanism_hashes():
    puzzle = {"reagents": [_single_atom("fire")], "products": []}
    solution = {
        "puzzleFile": "calc-test.puzzle",
        "source": {"sha256": "def"},
        "parts": [
            {"id": "input", "type": "input", "position": [0, 0], "rotation": 0, "which": 0, "program": [], "length": 1},
            {"id": "calc", "type": "glyph-calcification", "position": [0, 0], "rotation": 0, "which": 0, "program": [], "length": 1},
            {"id": "clock", "type": "arm1", "position": [10, 10], "rotation": 0, "which": 0, "program": [{"cycle": 0, "instruction": "drop"}], "length": 1, "armNumber": 1},
        ],
    }

    graph = build_fragment_flow_graph(puzzle, solution)
    calc = next(node for node in graph["nodes"] if node["anchorPartId"] == "calc")

    assert calc["role"] == "conversion"
    assert calc["canonicalMechanismHash"]
    assert calc["evidenceLevel"] == "dynamic-confirmed"
