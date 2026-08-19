from __future__ import annotations

import unittest

from packages.opus_solver.intermediate_convergence import (
    add_intermediate_convergence_station,
    intermediate_pair_observations,
)


class IntermediateConvergenceTests(unittest.TestCase):
    def test_observes_two_free_silver_atoms(self) -> None:
        replay = {
            "frames": [
                {
                    "cycle": 10,
                    "world": {
                        "atoms": [
                            {"id": "s0", "element": "silver", "position": [0, 0], "heldBy": []},
                            {"id": "s1", "element": "silver", "position": [3, 0], "heldBy": []},
                            {"id": "c0", "element": "copper", "position": [1, 1], "heldBy": []},
                        ],
                        "bonds": [],
                    },
                }
            ]
        }

        observations = intermediate_pair_observations(replay, element="silver")

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["cycle"], 10)
        self.assertFalse(observations[0]["firstHeld"])
        self.assertFalse(observations[0]["firstBonded"])
        self.assertFalse(observations[0]["alreadyAdjacent"])

    def test_marks_bonded_pair_as_not_free(self) -> None:
        replay = {
            "frames": [
                {
                    "cycle": 4,
                    "world": {
                        "atoms": [
                            {"id": "s0", "element": "silver", "position": [0, 0], "heldBy": []},
                            {"id": "s1", "element": "silver", "position": [1, 0], "heldBy": []},
                        ],
                        "bonds": [{"fromAtomId": "s0", "toAtomId": "x", "type": "normal"}],
                    },
                }
            ]
        }

        observations = intermediate_pair_observations(replay, element="silver")

        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0]["firstBonded"])

    def test_adds_arm_and_purifier_without_mutating_source(self) -> None:
        solution = {
            "source": {},
            "parts": [
                {
                    "id": "arm0",
                    "type": "arm1",
                    "position": [0, 0],
                    "rotation": 0,
                    "length": 1,
                    "armNumber": 1,
                    "program": [],
                }
            ],
        }
        observation = {"cycle": 20, "element": "silver"}
        move = {
            "basePosition": [2, 0],
            "baseRotation": 0,
            "instruction": "rotate_cw",
            "destination": [2, -1],
        }
        purifier = {"origin": [1, -1], "rotation": 0, "second": [2, -1], "output": [1, 0]}

        result = add_intermediate_convergence_station(
            solution,
            observation=observation,
            moving_atom="silver-b",
            move=move,
            purifier_pose=purifier,
            grab_cycle=20,
        )

        self.assertEqual(len(solution["parts"]), 1)
        self.assertEqual(len(result["parts"]), 3)
        arm = result["parts"][1]
        self.assertEqual(arm["type"], "arm1")
        self.assertEqual([item["cycle"] for item in arm["program"]], [20, 21, 22])
        self.assertEqual(result["parts"][2]["type"], "glyph-purification")
        self.assertEqual(result["source"]["generator"], "opus_solver/intermediate-convergence-v1")
        self.assertEqual(result["source"]["intermediateConvergenceRepairs"][0]["targetSolutionBytesUsed"], 0)


if __name__ == "__main__":
    unittest.main()
