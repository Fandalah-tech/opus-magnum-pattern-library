from __future__ import annotations

import unittest

from packages.opus_solver.bca import (
    BCA_RESTRICTION_METRICS,
    bca_default_restrictions,
    bca_key,
    bca_metrics_from_omsim,
    bca_proxy_validation,
    normalize_bca_selection,
)


def _validation(*, overlap: int = 0, duplicate_reagents: int = 0) -> dict:
    extras = {name: 0 for name in BCA_RESTRICTION_METRICS}
    extras.update({
        "minimum hexagon": 3,
        "overlap": overlap,
        "duplicate reagents": duplicate_reagents,
        "maximum track gap^2": 1,
    })
    return {
        "valid": True,
        "metrics": {
            "cost": 80,
            "instructions": 14,
            "cycles": 49,
            "area": 18,
        },
        "extraMetrics": extras,
        "rate": 8,
        "issues": [],
    }


class BcaTests(unittest.TestCase):
    def test_reconstructs_published_default_restrictions_expression(self) -> None:
        valid = _validation()
        self.assertEqual(bca_default_restrictions(valid), 0)

        restricted = _validation(overlap=2, duplicate_reagents=1)
        restricted["extraMetrics"]["parts of type baron"] = 3
        restricted["extraMetrics"]["maximum track gap^2"] = 4
        self.assertEqual(bca_default_restrictions(restricted), 8)

    def test_extracts_bca_metrics_and_order(self) -> None:
        metrics = bca_metrics_from_omsim(_validation())
        self.assertEqual(
            metrics,
            {
                "minimumHexagon": 3,
                "cost": 80,
                "cycles": 49,
                "area": 18,
                "instructions": 14,
                "defaultRestrictions": 0,
                "rate": 8,
            },
        )
        self.assertEqual(bca_key(metrics), (3, 49, 18, 80, 14))

    def test_rejects_restricted_candidate(self) -> None:
        validation = _validation(overlap=1)
        self.assertIsNone(bca_metrics_from_omsim(validation))
        proxy = bca_proxy_validation(validation)
        self.assertFalse(proxy["valid"])
        self.assertEqual(proxy["issues"][-1]["code"], "BCA_METRICS_UNAVAILABLE")

    def test_proxy_preserves_exact_bca_lexicographic_order(self) -> None:
        proxy = bca_proxy_validation(_validation())
        self.assertTrue(proxy["valid"])
        self.assertEqual(proxy["metrics"], {
            "cycles": 3,
            "cost": 18,
            "area": 80,
            "instructions": 14,
        })
        self.assertEqual(proxy["rate"], 49)
        self.assertEqual(proxy["bcaObjectiveKey"], [3, 49, 18, 80, 14])

        selected = normalize_bca_selection({
            "objectiveKey": [3, 49, 18, 80, 14],
            "oracleValidation": proxy,
        })
        self.assertEqual(selected["optimizationObjective"], "bca")
        self.assertEqual(selected["optimizationMetricSource"], "omsim-minimum-hexagon")
        self.assertEqual(selected["objectiveKey"], [3, 49, 18, 80, 14])
        self.assertEqual(selected["bcaMetrics"]["minimumHexagon"], 3)
        self.assertEqual(selected["defaultRestrictions"], 0)


if __name__ == "__main__":
    unittest.main()
