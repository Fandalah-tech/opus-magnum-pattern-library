from __future__ import annotations

import unittest

from packages.opus_analysis.patterns import detect_patterns


class PatternDetectorTests(unittest.TestCase):
    def test_detects_explainable_static_patterns(self) -> None:
        solution = {
            "parts": [
                {"id": "part-0", "type": "track", "program": []},
                {"id": "part-1", "type": "piston", "program": [
                    {"cycle": 0, "instruction": "track_plus"},
                    {"cycle": 1, "instruction": "rotate_cw"},
                    {"cycle": 2, "instruction": "rotate_ccw"},
                    {"cycle": 3, "instruction": "repeat"},
                ]},
            ]
        }
        graph = {"summary": {"componentCount": 2, "nodeCount": 4}}
        timeline = {
            "summary": {"peakParallelArms": 2, "averageParallelArms": 1.2},
            "arms": [{"partId": "part-1", "actionCount": 2, "utilization": 0.1, "idleCycles": 18}],
        }

        result = detect_patterns(solution, graph, timeline)
        ids = {finding["id"] for finding in result["findings"]}

        self.assertIn("track-transport", ids)
        self.assertIn("variable-reach-arm", ids)
        self.assertIn("bidirectional-oscillation", ids)
        self.assertIn("explicit-periodic-program", ids)
        self.assertIn("independent-structural-components", ids)
        self.assertIn("parallel-arm-scheduling", ids)
        self.assertIn("sparse-arm-program", ids)
        self.assertEqual(result["summary"]["findingCount"], len(ids))

    def test_empty_solution_has_no_findings(self) -> None:
        result = detect_patterns(
            {"parts": []},
            {"summary": {"componentCount": 0, "nodeCount": 0}},
            {"summary": {"peakParallelArms": 0}, "arms": []},
        )
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["summary"]["findingCount"], 0)


if __name__ == "__main__":
    unittest.main()
