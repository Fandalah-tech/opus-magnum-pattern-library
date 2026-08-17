from packages.opus_analysis import build_engine_fragment_flow_graph
from packages.opus_analysis.engine_fragment_flow import _engine_trace_horizon


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
    assert prism["representativeGeometry"]["anchorPartType"] == "bonder-prisma"
    assert prism["summary"]["partCount"] >= 1
    assert {
        (edge["sourceAnchorPartId"], edge["targetAnchorPartId"], edge["relation"])
        for edge in graph["edges"]
    } == {
        ("in-a", "prisma", "triplex-bond-created:red+black+yellow"),
        ("in-b", "prisma", "triplex-bond-created:red+black+yellow"),
        ("in-c", "prisma", "triplex-bond-created:red+black+yellow"),
    }
    assert graph["summary"]["traceHorizonSource"] == "single-period-no-output-contract"


def test_metric_free_standard_output_replays_enough_periods_for_completion_contract():
    solution = {
        "metrics": {},
        "parts": [
            {
                "id": "clock",
                "type": "arm1",
                "position": [0, 0],
                "rotation": 0,
                "length": 1,
                "program": [
                    {"cycle": 0, "instruction": "grab"},
                    {"cycle": 7, "instruction": "reset"},
                ],
            },
            {
                "id": "output",
                "type": "out-std",
                "position": [4, 0],
                "rotation": 0,
                "length": 1,
                "program": [],
            },
        ],
    }

    horizon, source = _engine_trace_horizon(solution)

    assert source == "periodic-output-contract"
    assert horizon >= 56


def test_declared_solution_cycles_remain_authoritative_for_engine_flow_horizon():
    solution = {
        "metrics": {"cycles": 37, "cost": 0, "area": 0, "instructions": 0},
        "parts": [
            {
                "id": "clock",
                "type": "arm1",
                "position": [0, 0],
                "rotation": 0,
                "length": 1,
                "program": [{"cycle": 0, "instruction": "drop"}],
            },
            {
                "id": "output",
                "type": "out-std",
                "position": [4, 0],
                "rotation": 0,
                "length": 1,
                "program": [],
            },
        ],
    }

    assert _engine_trace_horizon(solution) == (37, "declared-metrics")
