from packages.opus_analysis import build_engine_fragment_flow_graph


def _atom(element):
    return {"atoms": [{"id": "a0", "element": element, "position": [0, 0]}], "bonds": []}


def test_engine_flow_combines_exact_prismatic_channels_into_one_capability():
    puzzle = {"reagents": [_atom("fire"), _atom("fire"), _atom("fire")], "products": []}
    solution = {
        "puzzleFile": "triplex-flow",
        "parts": [
            {"id": "in-a", "type": "input", "position": [0, 0], "rotation": 0, "which": 0, "program": [], "length": 1},
            {"id": "in-b", "type": "input", "position": [1, 0], "rotation": 0, "which": 1, "program": [], "length": 1},
            {"id": "in-c", "type": "input", "position": [0, 1], "rotation": 0, "which": 2, "program": [], "length": 1},
            {"id": "prisma", "type": "bonder-prisma", "position": [0, 0], "rotation": 0, "which": 0, "program": [], "length": 1},
            {"id": "clock", "type": "arm1", "position": [10, 10], "rotation": 0, "which": 0, "program": [{"cycle": 0, "instruction": "drop"}], "length": 1, "armNumber": 1},
        ],
    }

    graph = build_engine_fragment_flow_graph(puzzle, solution)

    prism = next(node for node in graph["nodes"] if node["anchorPartId"] == "prisma")
    assert prism["role"] == "bonding"
    assert prism["observedRelations"] == {"triplex-bond-created:red+black+yellow": 1}
    assert {
        (edge["sourceAnchorPartId"], edge["targetAnchorPartId"], edge["relation"])
        for edge in graph["edges"]
    } == {
        ("in-a", "prisma", "triplex-bond-created:red+black+yellow"),
        ("in-b", "prisma", "triplex-bond-created:red+black+yellow"),
        ("in-c", "prisma", "triplex-bond-created:red+black+yellow"),
    }
