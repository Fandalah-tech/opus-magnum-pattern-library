import unittest

from packages.opus_analysis import build_solution_graph


class SolutionGraphTests(unittest.TestCase):
    def test_builds_nodes_edges_and_components(self):
        solution = {
            "name": "demo",
            "puzzleFile": "P001",
            "source": {"sha256": "abc"},
            "parts": [
                {"id": "part-0", "type": "arm1", "position": [0, 0], "length": 1, "rotation": 0, "armNumber": 0,
                 "program": [{"cycle": 0, "instruction": "grab"}, {"cycle": 2, "instruction": "rotate_cw"}]},
                {"id": "part-1", "type": "bonder", "position": [1, 0], "length": 1, "rotation": 0, "armNumber": 0, "program": []},
                {"id": "part-2", "type": "track", "position": [5, 5], "length": 1, "rotation": 0, "armNumber": 0,
                 "program": [], "trackHexes": [[0, 0], [1, 0]]},
            ],
        }
        graph = build_solution_graph(solution)
        self.assertEqual(graph["summary"]["nodeCount"], 3)
        self.assertEqual(graph["summary"]["armCount"], 1)
        self.assertEqual(graph["summary"]["trackCount"], 1)
        self.assertEqual(graph["summary"]["trackMobileArmCount"], 0)
        self.assertEqual(graph["summary"]["componentCount"], 2)
        relations = {(edge["source"], edge["target"], edge["relation"]) for edge in graph["edges"]}
        self.assertIn(("part-0", "part-1", "within-arm-reach"), relations)
        arm = next(node for node in graph["nodes"] if node["id"] == "part-0")
        self.assertEqual(arm["program"]["instructionCount"], 2)
        self.assertEqual(arm["program"]["firstInstructionCycle"], 0)
        self.assertEqual(arm["program"]["lastInstructionCycle"], 2)

    def test_detects_shared_track_hex(self):
        solution = {
            "parts": [
                {"id": "part-0", "type": "track", "position": [0, 0], "trackHexes": [[0, 0], [1, 0]], "program": []},
                {"id": "part-1", "type": "glyph-marker", "position": [1, 0], "program": []},
            ]
        }
        graph = build_solution_graph(solution)
        shared = [edge for edge in graph["edges"] if edge["relation"] == "shared-hex"]
        self.assertEqual(len(shared), 2)
        self.assertEqual(shared[0]["confidence"], "high")

    def test_track_motion_extends_arm_reach_to_remote_feed(self):
        solution = {
            "parts": [
                {
                    "id": "track",
                    "type": "track",
                    "position": [0, 0],
                    "trackHexes": [[0, 0], [1, 0], [2, 0], [3, 0]],
                    "program": [],
                },
                {
                    "id": "arm",
                    "type": "arm1",
                    "position": [0, 0],
                    "length": 1,
                    "rotation": 0,
                    "program": [
                        {"cycle": 0, "instruction": "grab"},
                        {"cycle": 1, "instruction": "track_plus"},
                    ],
                },
                {"id": "feed", "type": "input", "position": [4, 0], "program": []},
            ]
        }
        graph = build_solution_graph(solution)
        relations = {(edge["source"], edge["target"], edge["relation"]) for edge in graph["edges"]}
        self.assertNotIn(("arm", "feed", "within-arm-reach"), relations)
        self.assertIn(("arm", "feed", "within-track-arm-reach"), relations)
        self.assertEqual(graph["summary"]["trackMobileArmCount"], 1)
        edge = next(
            edge for edge in graph["edges"]
            if edge["source"] == "arm" and edge["target"] == "feed" and edge["relation"] == "within-track-arm-reach"
        )
        self.assertEqual(edge["evidence"]["minDistance"], 1)
        self.assertEqual(edge["evidence"]["trackIds"], ["track"])


if __name__ == "__main__":
    unittest.main()
