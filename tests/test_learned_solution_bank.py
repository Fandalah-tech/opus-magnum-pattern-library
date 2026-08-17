from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.update_learned_solution_bank import entries_from_materialization, merge_bank, update_bank


class LearnedSolutionBankTests(unittest.TestCase):
    def test_materialization_report_becomes_portable_bank_entry(self) -> None:
        with TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            generated = root / "reports" / "winner.solution"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"learned-solution-bytes")
            report = {
                "puzzleFile": "weeklies2026_aqueous-dagger",
                "portfolio": "reports/portfolio.json",
                "results": [{
                    "objective": "cga",
                    "architectureId": "critelli-cga-abc123",
                    "referenceMetrics": {"cycles": 15, "cost": 230, "area": 76},
                    "canonicalStructuralHash": "structural",
                    "canonicalMechanismHash": "mechanism",
                    "provenance": {"source": "public-corpus"},
                    "complete": True,
                    "outputFile": str(generated),
                    "outputSha256": "sha",
                }],
            }

            entries = entries_from_materialization(
                report,
                persist_dir=root / "fixtures" / "learned",
                repository_root=root,
            )

            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry["puzzleFile"], "weeklies2026_aqueous-dagger")
            self.assertEqual(entry["focusObjectives"], ["cycles"])
            self.assertEqual(entry["referenceMetrics"]["cycles"], 15)
            self.assertEqual(entry["canonicalMechanismHash"], "mechanism")
            self.assertTrue((root / entry["solutionPath"]).exists())
            self.assertFalse(entry["provenance"]["originalSolutionBytesCommitted"])
            self.assertTrue(entry["provenance"]["materializedFromLearnedBlueprint"])

    def test_bank_merge_replaces_same_materialization_source_key(self) -> None:
        current = {
            "entries": [{
                "id": "old",
                "sourceKey": "puzzle:cga:arch",
                "puzzleFile": "puzzle",
                "focusObjectives": ["cycles"],
                "referenceMetrics": {"cycles": 16},
            }]
        }
        replacement = [{
            "id": "new",
            "sourceKey": "puzzle:cga:arch",
            "puzzleFile": "puzzle",
            "focusObjectives": ["cycles"],
            "referenceMetrics": {"cycles": 15},
        }]

        merged = merge_bank(current, replacement)

        self.assertEqual(merged["summary"]["entryCount"], 1)
        self.assertEqual(merged["entries"][0]["id"], "new")
        self.assertEqual(merged["entries"][0]["referenceMetrics"]["cycles"], 15)

    def test_update_bank_persists_solution_and_json(self) -> None:
        with TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            generated = root / "generated.solution"
            generated.write_bytes(b"candidate")
            report_path = root / "materialization.json"
            report_path.write_text(json.dumps({
                "puzzleFile": "P999",
                "portfolio": "portfolio.json",
                "results": [{
                    "objective": "bca",
                    "architectureId": "bca-arch",
                    "referenceMetrics": {"boundingHexagon": 3, "cycles": 49, "area": 18},
                    "complete": True,
                    "outputFile": str(generated),
                }],
            }), encoding="utf-8")
            bank_path = root / "database" / "learned-solution-bank.json"

            result = update_bank(
                report_path,
                bank_path,
                persist_dir=root / "fixtures" / "persistent",
                repository_root=root,
            )

            bank = json.loads(bank_path.read_text(encoding="utf-8"))
            self.assertEqual(result["addedOrUpdated"], 1)
            self.assertEqual(bank["summary"]["entryCount"], 1)
            self.assertEqual(bank["entries"][0]["focusObjectives"], ["bca"])
            self.assertTrue((root / bank["entries"][0]["solutionPath"]).exists())


if __name__ == "__main__":
    unittest.main()
