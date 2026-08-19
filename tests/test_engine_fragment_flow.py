from __future__ import annotations

import unittest

from packages.opus_analysis import build_engine_fragment_flow_graph
from packages.opus_analysis.engine_fragment_flow import _engine_trace_horizon


def _atom(element):
    return {"atoms": [{"id": "a0", "element": element, "position": [0, 0]}], "bonds": []}


class EngineFragmentFlowTests(unittest.TestCase):
    def test_combines_exact_prismatic_channels_into_one_capability(self) -> None:
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
        self.assertEqual(prism["role"], "bonding")
        self.assertEqual(
            prism["observedRelations"],
            {"triplex-bond-created:red+black+yellow": 1},
        )
        self.assertEqual(
            prism["representativeGeometry"]["anchorPartType"],
            "bonder-prisma",
        )
        self.assertGreaterEqual(prism["summary"]["partCount"], 1)
        self.assertEqual(
            {
                (edge["sourceAnchorPartId"], edge["targetAnchorPartId"], edge["relation"])
                for edge in graph["edges"]
            },
            {
                ("in-a", "prisma", "triplex-bond-created:red+black+yellow"),
                ("in-b", "prisma", "triplex-bond-created:red+black+yellow"),
                ("in-c", "prisma", "triplex-bond-created:red+black+yellow"),
            },
        )
        self.assertEqual(
            graph["summary"]["traceHorizonSource"],
            "single-period-no-output-contract",
        )

    def test_metric_free_standard_output_replays_enough_periods_for_completion_contract(self) -> None:
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

        self.assertEqual(source, "periodic-output-contract")
        self.assertGreaterEqual(horizon, 56)

    def test_declared_solution_cycles_remain_authoritative_for_engine_flow_horizon(self) -> None:
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

        self.assertEqual(
            _engine_trace_horizon(solution),
            (37, "declared-metrics"),
        )


if __name__ == "__main__":
    unittest.main()
