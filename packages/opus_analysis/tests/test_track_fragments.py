from __future__ import annotations

import unittest

from packages.opus_analysis import extract_solution_fragments


def _part(part_id: str, part_type: str, position: tuple[int, int], *, program=None) -> dict:
    return {
        "id": part_id,
        "type": part_type,
        "enabled": True,
        "position": list(position),
        "length": 1,
        "rotation": 0,
        "which": 0,
        "armNumber": 0,
        "program": program or [],
    }


class TrackFragmentTests(unittest.TestCase):
    def test_remote_feed_keeps_track_transport_mechanism(self) -> None:
        track = _part("track", "track", (0, 0))
        track["trackHexes"] = [[0, 0], [1, 0], [2, 0], [3, 0]]
        solution = {
            "puzzleFile": "P001",
            "parts": [
                track,
                _part(
                    "arm",
                    "arm1",
                    (0, 0),
                    program=[
                        {"cycle": 0, "instruction": "grab"},
                        {"cycle": 1, "instruction": "track_plus"},
                    ],
                ),
                _part("feed", "input", (4, 0)),
            ],
        }

        fragments = extract_solution_fragments(solution)
        feed = next(item for item in fragments if item["role"] == "feed")

        self.assertEqual(feed["memberPartIds"], ["arm", "feed", "track"])
        self.assertEqual(feed["summary"]["armCount"], 1)
        self.assertEqual(feed["summary"]["trackCount"], 1)
        self.assertEqual(feed["summary"]["instructionCount"], 2)
        self.assertEqual(
            {part["sourcePartId"] for part in feed["geometry"]["parts"]},
            {"arm", "feed", "track"},
        )

    def test_static_arm_does_not_gain_remote_reach_from_unused_track(self) -> None:
        track = _part("track", "track", (0, 0))
        track["trackHexes"] = [[0, 0], [1, 0], [2, 0], [3, 0]]
        solution = {
            "puzzleFile": "P001",
            "parts": [
                track,
                _part("arm", "arm1", (0, 0), program=[{"cycle": 0, "instruction": "grab"}]),
                _part("feed", "input", (4, 0)),
            ],
        }

        fragments = extract_solution_fragments(solution)
        feed = next(item for item in fragments if item["role"] == "feed")
        self.assertEqual(feed["memberPartIds"], ["feed"])


if __name__ == "__main__":
    unittest.main()
