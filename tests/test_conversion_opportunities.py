from __future__ import annotations

import unittest

from packages.opus_solver.conversion_opportunities import conversion_opportunities_from_replay


class ConversionOpportunityTests(unittest.TestCase):
    def test_adjacent_free_equal_metals_create_two_ready_triangle_poses(self) -> None:
        replay = {
            "frames": [{
                "cycle": 4,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "lead", "position": [0, 0], "heldBy": []},
                        {"id": "b", "element": "lead", "position": [1, 0], "heldBy": []},
                    ],
                    "bonds": [],
                },
            }]
        }

        result = conversion_opportunities_from_replay(replay)

        self.assertEqual(result["minFreeEqualPairDistance"], 1)
        self.assertEqual(result["freeEqualPairObservationCount"], 1)
        self.assertEqual(result["adjacentFreeEqualPairObservationCount"], 1)
        self.assertEqual(result["readyPurificationPoseObservationCount"], 2)
        self.assertEqual(result["framesWithReadyPurificationPose"], 1)
        self.assertEqual(result["readyPoseCountsByElement"], {"lead": 2})

    def test_held_or_bonded_atoms_do_not_count_as_free_pairs(self) -> None:
        held = {
            "frames": [{
                "cycle": 1,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "tin", "position": [0, 0], "heldBy": ["arm"]},
                        {"id": "b", "element": "tin", "position": [2, 0], "heldBy": []},
                    ],
                    "bonds": [],
                },
            }]
        }
        bonded = {
            "frames": [{
                "cycle": 1,
                "world": {
                    "atoms": [
                        {"id": "a", "element": "tin", "position": [0, 0], "heldBy": []},
                        {"id": "b", "element": "tin", "position": [1, 0], "heldBy": []},
                    ],
                    "bonds": [{"fromAtomId": "a", "toAtomId": "b", "type": "normal"}],
                },
            }]
        }

        self.assertEqual(conversion_opportunities_from_replay(held)["freeEqualPairObservationCount"], 0)
        self.assertEqual(conversion_opportunities_from_replay(bonded)["freeEqualPairObservationCount"], 0)

    def test_distance_gradient_exists_before_pair_is_adjacent(self) -> None:
        replay = {
            "frames": [
                {
                    "cycle": 2,
                    "world": {
                        "atoms": [
                            {"id": "a", "element": "iron", "position": [0, 0], "heldBy": []},
                            {"id": "b", "element": "iron", "position": [4, 0], "heldBy": []},
                        ],
                        "bonds": [],
                    },
                },
                {
                    "cycle": 3,
                    "world": {
                        "atoms": [
                            {"id": "a", "element": "iron", "position": [0, 0], "heldBy": []},
                            {"id": "b", "element": "iron", "position": [2, 0], "heldBy": []},
                        ],
                        "bonds": [],
                    },
                },
            ]
        }

        result = conversion_opportunities_from_replay(replay)

        self.assertEqual(result["minFreeEqualPairDistance"], 2)
        self.assertEqual(result["readyPurificationPoseObservationCount"], 0)
        self.assertTrue(any(sample["cycle"] == 3 for sample in result["nearestFreeEqualPairSamples"]))

    def test_gold_is_not_a_purifiable_pair(self) -> None:
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

        result = conversion_opportunities_from_replay(replay)
        self.assertEqual(result["freeEqualPairObservationCount"], 0)
        self.assertIsNone(result["minFreeEqualPairDistance"])


if __name__ == "__main__":
    unittest.main()
