from __future__ import annotations

import unittest

from packages.opus_solver.trajectory_glyph_repair import purification_poses_from_replay


class TrajectoryGlyphRepairTests(unittest.TestCase):
    def test_detects_equal_metal_endpoints_with_empty_center(self) -> None:
        replay = {
            "frames": [{
                "cycle": 7,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "lead", "position": [0, 0]},
                        {"id": "b", "element": "lead", "position": [2, 0]},
                    ]
                },
            }]
        }

        poses = purification_poses_from_replay(replay)

        self.assertEqual(len(poses), 1)
        self.assertEqual(poses[0]["position"], [0, 0])
        self.assertEqual(poses[0]["rotation"], 0)
        self.assertEqual(poses[0]["element"], "lead")
        self.assertEqual(poses[0]["producedElement"], "tin")
        self.assertEqual(poses[0]["observationCount"], 1)

    def test_center_atom_blocks_purification_pose(self) -> None:
        replay = {
            "frames": [{
                "cycle": 3,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "tin", "position": [0, 0]},
                        {"id": "middle", "element": "salt", "position": [1, 0]},
                        {"id": "b", "element": "tin", "position": [2, 0]},
                    ]
                },
            }]
        }

        self.assertEqual(purification_poses_from_replay(replay), [])

    def test_gold_pair_is_not_a_purification_input(self) -> None:
        replay = {
            "frames": [{
                "cycle": 1,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "gold", "position": [0, 0]},
                        {"id": "b", "element": "gold", "position": [0, 2]},
                    ]
                },
            }]
        }

        self.assertEqual(purification_poses_from_replay(replay), [])

    def test_repeated_observation_accumulates_evidence(self) -> None:
        replay = {
            "frames": [
                {
                    "cycle": cycle,
                    "world": {
                        "atoms": [
                            {"id": "a", "element": "iron", "position": [1, 1]},
                            {"id": "b", "element": "iron", "position": [1, 3]},
                        ]
                    },
                }
                for cycle in (5, 6, 7)
            ]
        }

        poses = purification_poses_from_replay(replay)

        self.assertEqual(len(poses), 1)
        self.assertEqual(poses[0]["observationCount"], 3)
        self.assertEqual(poses[0]["firstCycle"], 5)
        self.assertEqual(poses[0]["lastCycle"], 7)


if __name__ == "__main__":
    unittest.main()
