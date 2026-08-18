from __future__ import annotations

import unittest

from packages.opus_analysis import build_program_timeline, build_solution_graph
from packages.opus_analysis.validation_horizon import generated_track_validation_hint


def _long_track_solution(*, generated: bool = True, metric_cycles: int | None = None) -> dict:
    parts = [
        {
            "id": "track",
            "type": "track",
            "position": [10, -5],
            "rotation": 0,
            "trackHexes": [[-2 + index, -1] for index in range(58)],
            "program": [],
        },
        {
            "id": "arm",
            "type": "arm6",
            "position": [8, -6],
            "rotation": 0,
            "length": 1,
            "program": [
                {"cycle": 0, "instruction": "grab"},
                {"cycle": 1, "instruction": "track_plus"},
                {"cycle": 2, "instruction": "drop"},
            ],
        },
        {"id": "input", "type": "input", "position": [9, -6], "program": []},
        {"id": "output", "type": "out-std", "position": [65, -6], "program": []},
    ]
    solution = {
        "puzzleFile": "GENX",
        "source": {"generator": "opus_solver/autonomous-knowledge-composition-v1"} if generated else {},
        "metrics": {},
        "parts": parts,
    }
    if metric_cycles is not None:
        solution["metrics"]["cycles"] = metric_cycles
    return solution


class ValidationHorizonTests(unittest.TestCase):
    def test_generated_sparse_track_machine_gets_bounded_workload_horizon(self) -> None:
        solution = _long_track_solution()
        details = generated_track_validation_hint(solution)
        self.assertIsNotNone(details)
        assert details is not None
        self.assertEqual(details["globalPeriod"], 3)
        self.assertEqual(details["tracks"][0]["trackCellCount"], 58)
        self.assertEqual(details["longestTraversalCycles"], 171)
        self.assertEqual(details["workstationCount"], 2)
        self.assertEqual(details["workUnits"], 12)
        self.assertEqual(details["hint"], 2052)

        timeline = build_program_timeline(solution)
        self.assertEqual(timeline["summary"]["horizon"], 2052)
        self.assertEqual(timeline["summary"]["validationCycleHint"], 2052)
        self.assertEqual(solution["source"]["validationCycleHintSource"], "generated-track-workload-v1")

    def test_unscored_non_solver_solution_is_not_mutated(self) -> None:
        solution = _long_track_solution(generated=False)
        self.assertIsNone(generated_track_validation_hint(solution))
        timeline = build_program_timeline(solution)
        self.assertEqual(timeline["summary"]["horizon"], 3)
        self.assertNotIn("validationCycleHint", solution["source"])

    def test_declared_metric_remains_authoritative(self) -> None:
        solution = _long_track_solution(metric_cycles=123)
        self.assertIsNone(generated_track_validation_hint(solution))
        timeline = build_program_timeline(solution)
        self.assertEqual(timeline["summary"]["horizon"], 123)
        self.assertEqual(timeline["summary"]["metricDeclaredCycles"], 123)

    def test_track_anchor_is_not_an_implicit_rail_cell(self) -> None:
        solution = _long_track_solution(generated=False)
        graph = build_solution_graph(solution)
        track = next(node for node in graph["nodes"] if node["id"] == "track")
        footprint = {tuple(cell) for cell in track["footprint"]}
        self.assertNotIn((10, -5), footprint)
        self.assertIn((8, -6), footprint)
        self.assertEqual(len(footprint), 58)
        self.assertEqual(graph["summary"]["trackMobileArmCount"], 1)


if __name__ == "__main__":
    unittest.main()
