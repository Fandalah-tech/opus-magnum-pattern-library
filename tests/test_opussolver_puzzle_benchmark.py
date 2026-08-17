from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.benchmark_opussolver_puzzles import BenchmarkContractError, benchmark_collection


class OpusSolverPuzzleBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.corpus = self.root / "opussolver"
        self.dev = self.corpus / "test" / "puzzles" / "24hour-1-sample"
        self.sealed = self.corpus / "test" / "puzzles" / "24hour-1-puzzles"
        self.dev.mkdir(parents=True)
        self.sealed.mkdir(parents=True)
        self.flow = self.root / "flow.json"
        self.flow.write_text(json.dumps({"fragments": [], "transitions": [], "convergenceMotifs": []}), encoding="utf-8")
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({
            "schemaVersion": "0.1.0",
            "id": "fixture",
            "repository": "https://example.invalid/opussolver",
            "pinnedCommit": "abc123",
            "policy": {"sealedTargetDetailsRedacted": True},
            "collections": [
                {
                    "id": "24hour-1-sample",
                    "path": "test/puzzles/24hour-1-sample",
                    "role": "development",
                    "expectedPuzzleCount": 6,
                    "sourceTreeSha": "devtree",
                },
                {
                    "id": "24hour-1-puzzles",
                    "path": "test/puzzles/24hour-1-puzzles",
                    "role": "sealed-heldout",
                    "expectedPuzzleCount": 1,
                    "sourceTreeSha": "sealedtree",
                },
            ],
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self._temporary.cleanup()

    @staticmethod
    def _puzzle(path: Path) -> dict:
        return {"name": path.stem.upper(), "source": {"name": path.name}, "availableParts": {}}

    def test_scans_only_puzzles_and_aggregates_failure_stages(self) -> None:
        names = ["good", "unsupported", "no-candidates", "incomplete", "leak", "invalid"]
        paths = {}
        for name in names:
            path = self.dev / f"{name}.puzzle"
            path.write_bytes(b"fixture")
            paths[name] = path
        (self.dev / "must-not-be-read.solution").write_bytes(b"target solution bytes")

        def fake_parse(path: Path) -> dict:
            path = Path(path)
            if path.stem == "invalid":
                raise ValueError("bad puzzle")
            return self._puzzle(path)

        def fake_mentions(_knowledge, target_id: str):
            return ["leaked"] if target_id == "leak" else []

        def fake_plan(puzzle: dict):
            target = Path(puzzle["source"]["name"]).stem
            return SimpleNamespace(
                supported=target != "unsupported",
                strategy=f"strategy-{target}",
                reason="unsupported fixture" if target == "unsupported" else None,
            )

        def fake_solve(puzzle: dict, *_args, **_kwargs):
            target = Path(puzzle["source"]["name"]).stem
            if target == "no-candidates":
                validation = {
                    "complete": False,
                    "compositionTestedCandidateCount": 0,
                    "compositionCompleteCandidateCount": 0,
                }
            elif target == "incomplete":
                validation = {
                    "complete": False,
                    "compositionTestedCandidateCount": 2,
                    "compositionCompleteCandidateCount": 0,
                }
            else:
                validation = {
                    "complete": True,
                    "compositionTestedCandidateCount": 3,
                    "compositionCompleteCandidateCount": 1,
                    "localCandidateMetrics": {"cycles": 12, "instructions": 4},
                }
            return SimpleNamespace(validation=validation, solution={"parts": []}, strategy="fixture")

        with patch("tools.benchmark_opussolver_puzzles.parse_puzzle", side_effect=fake_parse), patch(
            "tools.benchmark_opussolver_puzzles.puzzle_file_id",
            side_effect=lambda puzzle: Path(puzzle["source"]["name"]).stem,
        ), patch(
            "tools.benchmark_opussolver_puzzles.target_knowledge_mentions",
            side_effect=fake_mentions,
        ), patch(
            "tools.benchmark_opussolver_puzzles.build_manufacturing_plan",
            side_effect=fake_plan,
        ), patch(
            "tools.benchmark_opussolver_puzzles.solve_puzzle_from_knowledge",
            side_effect=fake_solve,
        ):
            report = benchmark_collection(
                self.corpus,
                self.manifest,
                self.flow,
                "24hour-1-sample",
                self.root / "report",
                verify_source=False,
            )

        summary = report["summary"]
        self.assertEqual(summary["collectionPuzzleCount"], 6)
        self.assertEqual(summary["selectedPuzzleCount"], 6)
        self.assertEqual(summary["parseSuccessCount"], 5)
        self.assertEqual(summary["parseFailureCount"], 1)
        self.assertEqual(summary["knowledgeLeakCount"], 1)
        self.assertEqual(summary["plannerSupportedCount"], 3)
        self.assertEqual(summary["candidateAvailableCount"], 2)
        self.assertEqual(summary["localCompleteCount"], 1)
        self.assertEqual(summary["targetSolutionBytesUsed"], 0)
        self.assertEqual(summary["failureStageCounts"], {
            "composition": 1,
            "knowledge-leak": 1,
            "local-solve": 1,
            "parse": 1,
            "planner": 1,
        })
        self.assertEqual(len(report["targets"]), 6)
        self.assertFalse(report["protocol"]["targetSolutionInputsAccepted"])
        self.assertFalse(report["protocol"]["targetSolutionFilesScanned"])

    def test_sealed_collection_requires_explicit_opt_in(self) -> None:
        (self.sealed / "GEN000.puzzle").write_bytes(b"fixture")
        with self.assertRaises(BenchmarkContractError):
            benchmark_collection(
                self.corpus,
                self.manifest,
                self.flow,
                "24hour-1-puzzles",
                self.root / "sealed-report",
                verify_source=False,
            )

    def test_sealed_collection_redacts_target_details(self) -> None:
        path = self.sealed / "GEN000.puzzle"
        path.write_bytes(b"fixture")
        puzzle = self._puzzle(path)
        solved = SimpleNamespace(
            validation={
                "complete": True,
                "compositionTestedCandidateCount": 1,
                "compositionCompleteCandidateCount": 1,
                "localCandidateMetrics": {"cycles": 10, "instructions": 4},
            },
            solution={"parts": []},
            strategy="fixture",
        )
        plan = SimpleNamespace(supported=True, strategy="fixture", reason=None)
        with patch("tools.benchmark_opussolver_puzzles.parse_puzzle", return_value=puzzle), patch(
            "tools.benchmark_opussolver_puzzles.puzzle_file_id", return_value="GEN000"
        ), patch(
            "tools.benchmark_opussolver_puzzles.target_knowledge_mentions", return_value=[]
        ), patch(
            "tools.benchmark_opussolver_puzzles.build_manufacturing_plan", return_value=plan
        ), patch(
            "tools.benchmark_opussolver_puzzles.solve_puzzle_from_knowledge", return_value=solved
        ):
            report = benchmark_collection(
                self.corpus,
                self.manifest,
                self.flow,
                "24hour-1-puzzles",
                self.root / "sealed-report",
                allow_sealed=True,
                verify_source=False,
            )

        self.assertTrue(report["collection"]["sealedDetailsRedacted"])
        self.assertEqual(report["targets"], [])
        self.assertEqual(report["summary"]["localCompleteCount"], 1)
        self.assertEqual(report["summary"]["targetSolutionBytesUsed"], 0)

    def test_sealed_collection_refuses_retained_generated_solutions(self) -> None:
        (self.sealed / "GEN000.puzzle").write_bytes(b"fixture")
        with self.assertRaises(BenchmarkContractError):
            benchmark_collection(
                self.corpus,
                self.manifest,
                self.flow,
                "24hour-1-puzzles",
                self.root / "sealed-report",
                allow_sealed=True,
                retain_solutions=True,
                verify_source=False,
            )


if __name__ == "__main__":
    unittest.main()
