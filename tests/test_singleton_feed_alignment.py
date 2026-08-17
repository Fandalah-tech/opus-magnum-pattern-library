from __future__ import annotations

import unittest

from packages.opus_solver.candidate_solution import singleton_input_alignment


def _puzzle(reagent_atoms):
    return {
        "availableParts": {
            "arms": ["arm1", "arm2", "arm3", "arm6", "piston"],
            "glyphs": ["bonder", "calcification"],
        },
        "reagents": [{"atoms": reagent_atoms, "bonds": []}],
    }


class SingletonFeedAlignmentTests(unittest.TestCase):
    def test_singleton_input_is_recentered_on_first_stationary_grab(self) -> None:
        puzzle = _puzzle([{"id": "a0", "element": "earth", "position": [0, 0]}])
        input_part = {
            "id": "input", "type": "input", "position": [3, -2], "rotation": 0,
            "sourceFragmentInstances": ["branch-0-upstream-1", "branch-1-input"],
        }
        arm = {
            "id": "arm", "type": "arm1", "position": [3, -1], "rotation": 3, "length": 1,
            "sourceFragmentInstances": ["branch-0-upstream-1", "branch-1-input"],
            "program": [{"cycle": 0, "instruction": "grab"}, {"cycle": 1, "instruction": "rotate_cw"}],
        }
        aligned = singleton_input_alignment(input_part, 0, puzzle, [input_part, arm])
        self.assertIsNotNone(aligned)
        self.assertEqual(aligned["originalPosition"], [3, -2])
        self.assertEqual(aligned["grabPosition"], [2, -1])
        self.assertEqual(aligned["position"], [2, -1])
        self.assertEqual(aligned["servingArmId"], "arm")
        self.assertTrue(aligned["exactFragmentInstanceMatch"])

    def test_local_singleton_atom_offset_is_respected_under_input_rotation(self) -> None:
        puzzle = _puzzle([{"id": "a0", "element": "earth", "position": [1, 0]}])
        input_part = {
            "id": "input", "type": "input", "position": [5, 5], "rotation": 1,
            "sourceFragmentInstances": ["branch-0-feed"],
        }
        arm = {
            "id": "arm", "type": "arm1", "position": [0, 0], "rotation": 0, "length": 1,
            "sourceFragmentInstances": ["branch-0-feed"],
            "program": [{"cycle": 3, "instruction": "grab"}],
        }
        aligned = singleton_input_alignment(input_part, 0, puzzle, [input_part, arm])
        self.assertIsNotNone(aligned)
        self.assertEqual(aligned["grabPosition"], [1, 0])
        self.assertEqual(aligned["position"], [1, -1])
        self.assertEqual(aligned["firstGrabCycle"], 3)

    def test_multi_atom_reagent_is_never_recentered(self) -> None:
        puzzle = _puzzle([
            {"id": "a0", "element": "earth", "position": [0, 0]},
            {"id": "a1", "element": "earth", "position": [1, 0]},
        ])
        input_part = {"id": "input", "type": "input", "position": [3, -2], "sourceFragmentInstances": ["branch-0-feed"]}
        arm = {
            "id": "arm", "type": "arm1", "position": [3, -1], "rotation": 3, "length": 1,
            "sourceFragmentInstances": ["branch-0-feed"], "program": [{"cycle": 0, "instruction": "grab"}],
        }
        self.assertIsNone(singleton_input_alignment(input_part, 0, puzzle, [input_part, arm]))

    def test_unrelated_arm_cannot_attract_singleton_input(self) -> None:
        puzzle = _puzzle([{"id": "a0", "element": "earth", "position": [0, 0]}])
        input_part = {"id": "input", "type": "input", "position": [3, -2], "sourceFragmentInstances": ["branch-0-feed"]}
        arm = {
            "id": "arm", "type": "arm1", "position": [3, -1], "rotation": 3, "length": 1,
            "sourceFragmentInstances": ["branch-9-other"], "program": [{"cycle": 0, "instruction": "grab"}],
        }
        self.assertIsNone(singleton_input_alignment(input_part, 0, puzzle, [input_part, arm]))

    def test_arm_with_strongest_shared_fragment_provenance_wins(self) -> None:
        puzzle = _puzzle([{"id": "a0", "element": "earth", "position": [0, 0]}])
        input_part = {
            "id": "input", "type": "input", "position": [-3, -1],
            "sourceFragmentInstances": ["branch-0-upstream-2", "branch-1-input"],
        }
        partial_arm = {
            "id": "partial", "type": "arm1", "position": [-2, 2], "rotation": 4, "length": 2,
            "sourceFragmentInstances": ["branch-0-upstream-1", "branch-1-input"],
            "program": [{"cycle": 0, "instruction": "grab"}],
        }
        exact_arm = {
            "id": "exact", "type": "arm1", "position": [-2, -2], "rotation": 2, "length": 1,
            "sourceFragmentInstances": ["branch-0-upstream-2", "branch-1-input"],
            "program": [{"cycle": 0, "instruction": "grab"}],
        }
        aligned = singleton_input_alignment(input_part, 0, puzzle, [input_part, partial_arm, exact_arm])
        self.assertIsNotNone(aligned)
        self.assertEqual(aligned["servingArmId"], "exact")
        self.assertEqual(aligned["sharedFragmentInstanceCount"], 2)
        self.assertTrue(aligned["exactFragmentInstanceMatch"])


if __name__ == "__main__":
    unittest.main()
