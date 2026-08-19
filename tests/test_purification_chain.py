from __future__ import annotations

import unittest

from packages.opus_solver.purification_chain import (
    _opportunity_key,
    _purification_profile_from_replay,
    _record_rank,
)


class PurificationChainTests(unittest.TestCase):
    def test_profiles_actual_purified_elements_from_replay(self) -> None:
        replay = {
            "frames": [
                {"cycle": 10, "events": [
                    {"kind": "atom-purified", "cycle": 10, "element": "copper"},
                ]},
                {"cycle": 20, "events": [
                    {"kind": "atom-purified", "cycle": 20, "element": "copper"},
                    {"kind": "atom-purified", "cycle": 20, "element": "silver"},
                ]},
            ],
        }

        profile = _purification_profile_from_replay(replay)

        self.assertEqual(profile["count"], 3)
        self.assertEqual(profile["countsByElement"], {"copper": 2, "silver": 1})
        self.assertEqual(profile["frontierElement"], "silver")
        self.assertFalse(profile["goldReached"])

    def test_opportunity_order_prefers_frontier_advance(self) -> None:
        copper = {
            "producedElement": "copper",
            "minimumBlockerCount": 0,
            "observationCount": 20,
            "origin": [0, 0],
            "rotation": 0,
        }
        silver = {
            "producedElement": "silver",
            "minimumBlockerCount": 1,
            "unbondCandidates": [{"origin": [1, 0]}],
            "observationCount": 1,
            "origin": [2, 0],
            "rotation": 0,
        }

        ordered = sorted(
            [copper, silver],
            key=lambda item: _opportunity_key(item, frontier_index=3),
        )

        self.assertIs(ordered[0], silver)

    def test_record_rank_prefers_higher_actual_metal_frontier(self) -> None:
        base = {
            "validation": {
                "complete": False,
                "totalDelivered": 0,
                "distinctRequiredChemistryEventCount": 2,
                "terminatedWithError": False,
                "completedCycles": 200,
                "requiredChemistryEventCount": 4,
                "chemistryEventCount": 8,
            },
            "opportunity": {"minimumBlockerCount": 0, "observationCount": 10},
        }
        copper = {
            **base,
            "purificationProfile": {
                "frontierIndex": 3,
                "count": 4,
                "countsByElement": {"copper": 4},
            },
        }
        silver = {
            **base,
            "purificationProfile": {
                "frontierIndex": 4,
                "count": 3,
                "countsByElement": {"copper": 2, "silver": 1},
            },
        }

        self.assertGreater(_record_rank(silver), _record_rank(copper))


if __name__ == "__main__":
    unittest.main()
