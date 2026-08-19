from __future__ import annotations

import unittest

from packages.opus_solver import candidate_solution as candidate_solution_module
from packages.opus_solver.feed_alignment import generic_input_alignment, preferred_reagent_anchor_atom


def bonded_feed_puzzle() -> dict:
    return {
        "reagents": [{
            "atoms": [
                {"id": "fire", "element": "fire", "position": [0, 0]},
                {"id": "earth", "element": "earth", "position": [1, 0]},
            ],
            "bonds": [{"type": "normal", "from": [0, 0], "to": [1, 0]}],
        }],
        "products": [{
            "atoms": [{"id": "p0", "element": "earth", "position": [0, 0]}],
            "bonds": [],
        }],
        "availableParts": {
            "arms": ["arm1"],
            "glyphs": ["unbonder"],
        },
    }


def learned_feed_parts() -> tuple[dict, list[dict]]:
    input_part = {
        "id": "input",
        "type": "input",
        "position": [9, 9],
        "rotation": 0,
        "sourceFragmentInstances": ["branch-0:feed"],
        "program": [],
    }
    arm = {
        "id": "arm",
        "type": "arm1",
        "position": [2, 0],
        "rotation": 0,
        "length": 1,
        "sourceFragmentInstances": ["branch-0:feed"],
        "program": [{"cycle": 0, "instruction": "grab"}],
    }
    return input_part, [input_part, arm]


def track_feed_parts() -> tuple[dict, dict, list[dict]]:
    provenance = ["branch-0:feed", "branch-1:feed"]
    first = {
        "id": "input-a",
        "type": "input",
        "position": [1, 0],
        "rotation": 0,
        "sourceFragmentInstances": ["branch-0:feed"],
        "program": [],
    }
    second = {
        "id": "input-b",
        "type": "input",
        "position": [5, 0],
        "rotation": 0,
        "sourceFragmentInstances": ["branch-1:feed"],
        "program": [],
    }
    arm = {
        "id": "arm",
        "type": "arm1",
        "position": [0, 0],
        "rotation": 0,
        "length": 1,
        "sourceFragmentInstances": provenance,
        "program": [
            {"cycle": 0, "instruction": "grab"},
            {"cycle": 1, "instruction": "track_plus"},
            {"cycle": 2, "instruction": "drop"},
        ],
    }
    track = {
        "id": "track",
        "type": "track",
        "position": [0, 0],
        "rotation": 0,
        "sourceFragmentInstances": provenance,
        "trackHexes": [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0]],
        "program": [],
    }
    return first, second, [first, second, arm, track]


class FeedAlignmentTests(unittest.TestCase):
    def test_planner_recipe_selects_bonded_atom_needed_by_product(self) -> None:
        self.assertEqual(preferred_reagent_anchor_atom(bonded_feed_puzzle(), 0), 1)

    def test_bonded_feed_is_translated_as_whole_molecule_to_first_grab(self) -> None:
        input_part, all_parts = learned_feed_parts()
        alignment = generic_input_alignment(input_part, 0, bonded_feed_puzzle(), all_parts)
        self.assertIsNotNone(alignment)
        assert alignment is not None
        self.assertEqual(alignment["targetAtomIndex"], 1)
        self.assertEqual(alignment["targetAtomElement"], "earth")
        self.assertEqual(alignment["grabPosition"], [3, 0])
        self.assertEqual(alignment["position"], [2, 0])
        self.assertTrue(alignment["bondedTargetReagent"])
        self.assertEqual(alignment["servingTrackIds"], [])

    def test_singleton_feed_keeps_direct_tip_alignment(self) -> None:
        puzzle = {
            "reagents": [{"atoms": [{"id": "a", "element": "water", "position": [0, 0]}], "bonds": []}],
            "products": [{"atoms": [{"id": "p", "element": "water", "position": [0, 0]}], "bonds": []}],
            "availableParts": {"arms": ["arm1"], "glyphs": []},
        }
        input_part, all_parts = learned_feed_parts()
        alignment = generic_input_alignment(input_part, 0, puzzle, all_parts)
        self.assertIsNotNone(alignment)
        assert alignment is not None
        self.assertEqual(alignment["targetAtomIndex"], 0)
        self.assertEqual(alignment["position"], [3, 0])
        self.assertFalse(alignment["bondedTargetReagent"])

    def test_track_served_inputs_preserve_distinct_inherited_lanes(self) -> None:
        first, second, all_parts = track_feed_parts()
        left = generic_input_alignment(first, 0, bonded_feed_puzzle(), all_parts)
        right = generic_input_alignment(second, 0, bonded_feed_puzzle(), all_parts)
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        assert left is not None and right is not None

        self.assertEqual(left["position"], [1, 0])
        self.assertEqual(right["position"], [5, 0])
        self.assertNotEqual(left["position"], right["position"])
        self.assertEqual(left["translationDistance"], 0)
        self.assertEqual(right["translationDistance"], 0)
        self.assertEqual(left["servingTrackIds"], ["track"])
        self.assertEqual(right["servingTrackIds"], ["track"])
        self.assertGreater(left["reachableGrabCandidateCount"], 1)
        self.assertEqual(
            left["alignmentEvidence"],
            "target-chemistry-source-atom-to-nearest-learned-track-grab",
        )

    def test_candidate_materializer_uses_generic_feed_alignment(self) -> None:
        self.assertIs(candidate_solution_module.singleton_input_alignment, generic_input_alignment)


if __name__ == "__main__":
    unittest.main()
