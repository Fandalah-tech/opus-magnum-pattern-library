from __future__ import annotations

import unittest

from packages.opus_engine.campaign_simulator import _segment_point_distance, _to_xy


class ContinuousCollisionGeometryTests(unittest.TestCase):
    def test_hex_translation_passes_near_intermediate_hex(self) -> None:
        start = _to_xy((7, -1))
        end = _to_xy((8, -2))
        self.assertAlmostEqual(_segment_point_distance(start, end, _to_xy((8, -2))), 0.0)

    def test_segment_distance_detects_nearby_nonendpoint_collider(self) -> None:
        start = (0.0, 0.0)
        end = (100.0, 0.0)
        self.assertAlmostEqual(_segment_point_distance(start, end, (50.0, 20.0)), 20.0)

    def test_segment_distance_clamps_beyond_endpoint(self) -> None:
        start = (0.0, 0.0)
        end = (10.0, 0.0)
        self.assertAlmostEqual(_segment_point_distance(start, end, (15.0, 0.0)), 5.0)


if __name__ == "__main__":
    unittest.main()
