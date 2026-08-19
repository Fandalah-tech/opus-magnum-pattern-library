import unittest

from tools.omsim_adapter.validate import parse_omsim_output


class ParseOmsimOutputTests(unittest.TestCase):
    def test_parses_valid_summary(self):
        result = parse_omsim_output("120g/18i@0 42c/37a@V\n", 0)
        self.assertTrue(result["valid"])
        self.assertEqual(
            result["metrics"],
            {"cost": 120, "instructions": 18, "cycles": 42, "area": 37},
        )
        self.assertEqual(result["issues"], [])

    def test_preserves_simulation_error_context(self):
        result = parse_omsim_output("collision on cycle 14 at -2 5\n", 255)
        self.assertFalse(result["valid"])
        self.assertEqual(result["issues"][0]["cycle"], 14)
        self.assertEqual(
            result["issues"][0]["details"]["location"], {"u": -2, "v": 5}
        )

    def test_rejects_success_without_metrics(self):
        result = parse_omsim_output("unexpected output\n", 0)
        self.assertFalse(result["valid"])
        self.assertEqual(
            result["issues"][0]["code"], "OMSIM_VALIDATION_FAILED"
        )

    def test_parses_multiline_metrics_and_output_rate(self):
        result = parse_omsim_output(
            "cost: 310\ninstructions: 100\ncycles: 53\narea: 145\n"
            "output intervals: 23 [9 3 6]\n",
            0,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(
            result["metrics"],
            {"cost": 310, "instructions": 100, "cycles": 53, "area": 145},
        )
        self.assertEqual(result["rate"], 9)
        self.assertEqual(
            result["outputIntervals"],
            {"warmup": [23], "steadyState": [9, 3, 6]},
        )


if __name__ == "__main__":
    unittest.main()
