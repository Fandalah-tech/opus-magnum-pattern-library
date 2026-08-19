from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.evaluate_holdout_matrix import classify_transfer, load_manifest, sha256_file


class HoldoutMatrixTests(unittest.TestCase):
    def test_manifest_requires_unique_targets_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({
                "kind": "external-heldout-puzzle-manifest",
                "targets": [
                    {"id": "A", "path": "A.puzzle", "sha256": "0" * 64},
                    {"id": "B", "path": "B.puzzle", "sha256": "1" * 64},
                ],
            }), encoding="utf-8")
            manifest = load_manifest(path)
            self.assertEqual([item["id"] for item in manifest["targets"]], ["A", "B"])

    def test_sha256_file_is_binary_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.puzzle"
            path.write_bytes(b"\x00\xffopus\x10")
            self.assertEqual(
                sha256_file(path),
                "f376dc1d613a5bcb9ee84a6da53571545010e6667886f548591e51992b81d360",
            )

    def test_stage_classification_is_ordered_by_failure_boundary(self) -> None:
        base = {
            "protocol": {"targetExcludedFromKnowledge": True},
            "target": {"profile": {"planner": {"supported": True}}},
            "compositionDiagnostics": {"rankedAssemblyCount": 1},
            "result": {"complete": True},
        }
        self.assertEqual(classify_transfer(base), "local-complete")

        report = dict(base)
        report["protocol"] = {"targetExcludedFromKnowledge": False}
        self.assertEqual(classify_transfer(report), "isolation-failed")

        report = dict(base)
        report["target"] = {"profile": {"planner": {"supported": False}}}
        self.assertEqual(classify_transfer(report), "planner-unsupported")

        report = dict(base)
        report["compositionDiagnostics"] = {"rankedAssemblyCount": 0}
        self.assertEqual(classify_transfer(report), "no-fragment-assembly")

        report = dict(base)
        report["result"] = {"complete": False, "errorType": "ValueError"}
        self.assertEqual(classify_transfer(report), "solve-error")

        report = dict(base)
        report["result"] = {"complete": False}
        self.assertEqual(classify_transfer(report), "candidate-incomplete")


if __name__ == "__main__":
    unittest.main()
