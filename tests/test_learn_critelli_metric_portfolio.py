from __future__ import annotations

import unittest

from tools.learn_critelli_metric_portfolio import select_representatives


class CritelliMetricPortfolioTests(unittest.TestCase):
    def test_cga_is_strictly_lexicographic(self) -> None:
        records = [
            {"sourceRank": 1, "submissionId": "a", "canonicalMechanismHash": "a", "cga": {"cycles": 15, "cost": 240, "area": 40}, "bca": {"boundingHexagon": 4, "cycles": 15, "area": 40}},
            {"sourceRank": 2, "submissionId": "b", "canonicalMechanismHash": "b", "cga": {"cycles": 15, "cost": 230, "area": 80}, "bca": {"boundingHexagon": 5, "cycles": 15, "area": 80}},
            {"sourceRank": 3, "submissionId": "c", "canonicalMechanismHash": "c", "cga": {"cycles": 16, "cost": 20, "area": 5}, "bca": {"boundingHexagon": 3, "cycles": 49, "area": 18}},
        ]
        selected = select_representatives(records, objective="cga", limit=3)
        self.assertEqual([item["submissionId"] for item in selected], ["b", "a", "c"])

    def test_bca_ignores_cost_and_deduplicates_mechanisms(self) -> None:
        records = [
            {"sourceRank": 1, "submissionId": "a", "canonicalMechanismHash": "same", "bca": {"boundingHexagon": 3, "cycles": 49, "area": 18}},
            {"sourceRank": 2, "submissionId": "b", "canonicalMechanismHash": "same", "bca": {"boundingHexagon": 3, "cycles": 49, "area": 17}},
            {"sourceRank": 3, "submissionId": "c", "canonicalMechanismHash": "other", "bca": {"boundingHexagon": 3, "cycles": 50, "area": 12}},
            {"sourceRank": 4, "submissionId": "d", "canonicalMechanismHash": "show", "showcase": True, "bca": {"boundingHexagon": 1, "cycles": 1, "area": 1}},
        ]
        selected = select_representatives(records, objective="bca", limit=3)
        self.assertEqual([item["submissionId"] for item in selected], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
