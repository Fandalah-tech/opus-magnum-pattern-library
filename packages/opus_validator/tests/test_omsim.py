from pathlib import Path
import unittest

from packages.opus_validator import build_command, classify_result, parse_metrics


class OmsimAdapterTests(unittest.TestCase):
    def test_build_command_uses_puzzle_file_option(self):
        command = build_command("omsim", Path("a.puzzle"), Path("b.solution"))
        self.assertEqual(command, ["omsim", "--puzzle-file", "a.puzzle", "b.solution"])

    def test_parse_metrics(self):
        self.assertEqual(
            parse_metrics("195g/77i@0 214c/56a@V\n"),
            {"cost": 195, "cycles": 214, "area": 56, "instructions": 77},
        )

    def test_success_is_valid(self):
        result = classify_result(0, "195g/77i@0 214c/56a@V\n")
        self.assertEqual(result["status"], "valid")
        self.assertTrue(result["valid"])
        self.assertEqual(result["metrics"]["cycles"], 214)

    def test_usage_failure_is_validator_error(self):
        result = classify_result(255, "must specify either -p|--puzzle-file or -f|--puzzle-folder\n")
        self.assertEqual(result["status"], "validator-error")
        self.assertIsNone(result["valid"])
        self.assertEqual(result["issues"][0]["code"], "OMSIM_INVOCATION_FAILED")

    def test_simulation_failure_is_invalid(self):
        result = classify_result(255, "collision on cycle 12 at 1 2\n")
        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["valid"])
        self.assertEqual(result["issues"][0]["code"], "OMSIM_VALIDATION_FAILED")


if __name__ == "__main__":
    unittest.main()
