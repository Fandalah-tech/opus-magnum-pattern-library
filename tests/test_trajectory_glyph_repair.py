from __future__ import annotations

import unittest

from packages.opus_solver.trajectory_glyph_repair import purification_poses_from_replay


class TrajectoryGlyphRepairTests(unittest.TestCase):
    def test_detects_adjacent_free_equal_metals_and_both_output_sides(self) -> None:
        replay = {
            "frames": [{
                "cycle": 7,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "lead", "position": [0, 0], "heldBy": []},
                        {"id": "b", "element": "lead", "position": [1, 0], "heldBy": []},
                    ],
                    "bonds": [],
                },
            }]
        }

        poses = purification_poses_from_replay(replay)

        self.assertEqual(len(poses), 2)
        forward = next(item for item in poses if item["position"] == [0, 0] and item["rotation"] == 0)
        self.assertEqual(forward["inputPositions"], [[0, 0], [1, 0]])
        self.assertEqual(forward["outputPosition"], [0, 1])
        self.assertEqual(forward["element"], "lead")
        self.assertEqual(forward["producedElement"], "tin")
        self.assertEqual(forward["observationCount"], 1)

    def test_occupied_outputs_block_both_triangle_orientations(self) -> None:
        replay = {
            "frames": [{
                "cycle": 3,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "tin", "position": [0, 0], "heldBy": []},
                        {"id": "b", "element": "tin", "position": [1, 0], "heldBy": []},
                        {"id": "upper", "element": "salt", "position": [0, 1], "heldBy": []},
                        {"id": "lower", "element": "salt", "position": [1, -1], "heldBy": []},
                    ],
                    "bonds": [],
                },
            }]
        }

        self.assertEqual(purification_poses_from_replay(replay), [])

    def test_held_or_bonded_metals_are_not_conversion_inputs(self) -> None:
        held_replay = {
            "frames": [{
                "cycle": 1,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "iron", "position": [0, 0], "heldBy": ["arm"]},
                        {"id": "b", "element": "iron", "position": [1, 0], "heldBy": []},
                    ],
                    "bonds": [],
                },
            }]
        }
        bonded_replay = {
            "frames": [{
                "cycle": 1,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "iron", "position": [0, 0], "heldBy": []},
                        {"id": "b", "element": "iron", "position": [1, 0], "heldBy": []},
                    ],
                    "bonds": [{"fromAtomId": "a", "toAtomId": "b", "type": "normal"}],
                },
            }]
        }

        self.assertEqual(purification_poses_from_replay(held_replay), [])
        self.assertEqual(purification_poses_from_replay(bonded_replay), [])

    def test_gold_pair_is_not_a_purification_input(self) -> None:
        replay = {
            "frames": [{
                "cycle": 1,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "gold", "position": [0, 0], "heldBy": []},
                        {"id": "b", "element": "gold", "position": [1, 0], "heldBy": []},
                    ],
                    "bonds": [],
                },
            }]
        }

        self.assertEqual(purification_poses_from_replay(replay), [])

    def test_repeated_observation_accumulates_evidence_per_orientation(self) -> None:
        replay = {
            "frames": [
                {
                    "cycle": cycle,
                    "world": {
                        "atoms": [
                            {"id": "a", "element": "copper", "position": [1, 1], "heldBy": []},
                            {"id": "b", "element": "copper", "position": [1, 2], "heldBy": []},
                        ],
                        "bonds": [],
                    },
                }
                for cycle in (5, 6, 7)
            ]
        }

        poses = purification_poses_from_replay(replay)

        self.assertEqual(len(poses), 2)
        for pose in poses:
            self.assertEqual(pose["observationCount"], 3)
            self.assertEqual(pose["firstCycle"], 5)
            self.assertEqual(pose["lastCycle"], 7)


if __name__ == "__main__":
    unittest.main()
