from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.autonomous import solve_puzzle_from_knowledge
from tools.evaluate_holdout_transfer import (
    _composition_diagnostics,
    knowledge_source_solutions,
    puzzle_transfer_profile,
    target_knowledge_mentions,
)


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "external-heldout-puzzle-manifest":
        raise ValueError("Unsupported heldout manifest kind")
    targets = list(manifest.get("targets") or [])
    if not targets:
        raise ValueError("Heldout manifest has no targets")
    ids = [str(item.get("id") or "") for item in targets]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Heldout target ids must be non-empty and unique")
    for item in targets:
        rel = Path(str(item.get("path") or ""))
        digest = str(item.get("sha256") or "").lower()
        if rel.is_absolute() or rel.suffix != ".puzzle":
            raise ValueError(f"Invalid heldout puzzle path: {rel}")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"Invalid SHA-256 for {item.get('id')}")
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_transfer(report: dict[str, Any]) -> str:
    protocol = report.get("protocol") or {}
    profile = ((report.get("target") or {}).get("profile") or {})
    planner = profile.get("planner") or {}
    composition = report.get("compositionDiagnostics") or {}
    result = report.get("result") or {}
    if not protocol.get("targetExcludedFromKnowledge", False):
        return "isolation-failed"
    if not planner.get("supported", False):
        return "planner-unsupported"
    if int(composition.get("rankedAssemblyCount") or 0) <= 0:
        return "no-fragment-assembly"
    if result.get("complete"):
        return "local-complete"
    if result.get("errorType"):
        return "solve-error"
    return "candidate-incomplete"


def evaluate_loaded_transfer(
    puzzle_path: Path,
    flow_index_path: Path,
    knowledge: dict[str, Any],
    knowledge_sources: list[str],
    *,
    target_puzzle_id: str,
    objective: str,
    composition_limit: int,
    solution_output: Path | None,
) -> dict[str, Any]:
    """Evaluate one heldout target while reusing one immutable knowledge object."""
    puzzle = parse_puzzle(puzzle_path)
    mentions = target_knowledge_mentions(knowledge, target_puzzle_id)
    profile = puzzle_transfer_profile(puzzle)
    composition = _composition_diagnostics(
        puzzle,
        knowledge,
        limit=composition_limit,
        detailed=False,
    )
    protocol = {
        "targetPuzzleId": target_puzzle_id,
        "targetPuzzlePath": str(puzzle_path),
        "targetSolutionBytesUsed": 0,
        "targetSolutionInputsAccepted": False,
        "targetKnowledgeMentionCount": len(mentions),
        "targetKnowledgeMentions": mentions[:20],
        "targetExcludedFromKnowledge": len(mentions) == 0,
        "knowledgePath": str(flow_index_path),
        "knowledgeFragmentCount": len(knowledge.get("fragments", []) or []),
        "knowledgeTransitionCount": len(knowledge.get("transitions", []) or []),
        "knowledgeConvergenceCount": len(knowledge.get("convergenceMotifs", []) or []),
        "knowledgeSourceSolutionCount": len(knowledge_sources),
        "knowledgeSourceSolutions": knowledge_sources[:50],
    }
    report: dict[str, Any] = {
        "schemaVersion": "0.4.0",
        "kind": "strict-heldout-knowledge-transfer",
        "target": {"id": target_puzzle_id, "name": puzzle.get("name"), "source": puzzle.get("source"), "profile": profile},
        "protocol": protocol,
        "request": {
            "objective": objective,
            "compositionLimit": int(composition_limit),
            "directGeneratorAllowed": False,
            "learnedArchitectureBankAllowed": False,
            "fragmentKnowledgeAllowed": True,
            "knowledgeLoadedOnceForMatrix": True,
            "diagnosticMode": "matrix-compact",
        },
        "compositionDiagnostics": composition,
        "result": {
            "complete": False,
            "route": None,
            "strategy": None,
            "candidate": None,
            "localMetrics": None,
            "errorType": None,
            "error": None,
            "solutionOutput": None,
        },
    }
    if mentions:
        report["result"]["errorType"] = "TargetKnowledgeLeakError"
        report["result"]["error"] = f"Held-out target {target_puzzle_id!r} appears in reusable knowledge"
        return report

    try:
        solved = solve_puzzle_from_knowledge(
            puzzle,
            knowledge,
            knowledge,
            limit=max(1, int(composition_limit)),
            objective=objective,
            architecture_candidates=(),
        )
        validation = solved.validation
        complete = bool(validation.get("complete"))
        report["result"].update({
            "complete": complete,
            "route": validation.get("solverRoute"),
            "strategy": solved.strategy,
            "candidate": validation.get("selectedCandidateId"),
            "localMetrics": validation.get("localCandidateMetrics"),
            "compositionTestedCandidateCount": validation.get("compositionTestedCandidateCount"),
            "compositionCompleteCandidateCount": validation.get("compositionCompleteCandidateCount"),
            "knowledgeFragmentCount": validation.get("knowledgeFragmentCount"),
            "knowledgeTransitionCount": validation.get("knowledgeTransitionCount"),
            "knowledgeConvergenceCount": validation.get("knowledgeConvergenceCount"),
        })
        if solution_output is not None and complete:
            solution_output.parent.mkdir(parents=True, exist_ok=True)
            write_solution(solved.solution, solution_output)
            report["result"]["solutionOutput"] = str(solution_output)
    except Exception as error:
        report["result"]["errorType"] = type(error).__name__
        report["result"]["error"] = str(error)
    return report


def evaluate_matrix(manifest_path: Path, puzzle_root: Path, flow_index_path: Path, output_dir: Path, *, objective: str = "balanced", composition_limit: int = 30) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    knowledge = json.loads(flow_index_path.read_text(encoding="utf-8"))
    knowledge_sources = knowledge_source_solutions(knowledge)
    output_dir.mkdir(parents=True, exist_ok=True)
    solution_dir = output_dir / "solutions"
    solution_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    stage_counts: Counter[str] = Counter()
    planner_counts: Counter[str] = Counter()
    integrity_failures = 0

    for target in manifest["targets"]:
        target_id = str(target["id"])
        puzzle_path = puzzle_root / str(target["path"])
        actual_sha256 = sha256_file(puzzle_path) if puzzle_path.is_file() else None
        expected_sha256 = str(target["sha256"]).lower()
        if actual_sha256 != expected_sha256:
            integrity_failures += 1
            entry = {"id": target_id, "path": str(puzzle_path), "expectedSha256": expected_sha256, "actualSha256": actual_sha256, "integrityOk": False, "stage": "integrity-failed", "report": None}
            stage_counts[entry["stage"]] += 1
            results.append(entry)
            continue

        solution_output = solution_dir / f"{target_id}.solution"
        report = evaluate_loaded_transfer(
            puzzle_path,
            flow_index_path,
            knowledge,
            knowledge_sources,
            target_puzzle_id=target_id,
            objective=objective,
            composition_limit=composition_limit,
            solution_output=solution_output,
        )
        stage = classify_transfer(report)
        stage_counts[stage] += 1
        planner = (((report.get("target") or {}).get("profile") or {}).get("planner") or {})
        planner_counts[str(planner.get("strategy") or "unknown")] += 1
        entry = {
            "id": target_id,
            "path": str(puzzle_path),
            "expectedSha256": expected_sha256,
            "actualSha256": actual_sha256,
            "integrityOk": True,
            "stage": stage,
            "plannerStrategy": planner.get("strategy"),
            "plannerSupported": bool(planner.get("supported")),
            "rankedAssemblyCount": int((report.get("compositionDiagnostics") or {}).get("rankedAssemblyCount") or 0),
            "complete": bool((report.get("result") or {}).get("complete")),
            "solutionOutput": (report.get("result") or {}).get("solutionOutput"),
            "report": report,
        }
        results.append(entry)
        (output_dir / f"{target_id}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({
            "target": target_id,
            "stage": stage,
            "planner": entry["plannerStrategy"],
            "assemblies": entry["rankedAssemblyCount"],
            "complete": entry["complete"],
        }, ensure_ascii=False), flush=True)

    target_count = len(results)
    local_complete = stage_counts.get("local-complete", 0)
    return {
        "schemaVersion": "0.2.0",
        "kind": "strict-heldout-transfer-matrix",
        "manifest": str(manifest_path),
        "source": manifest.get("source"),
        "request": {"objective": objective, "compositionLimit": int(composition_limit), "targetSolutionBytesUsed": 0, "targetSolutionInputsAccepted": False, "directGeneratorAllowed": False, "learnedArchitectureBankAllowed": False, "fragmentKnowledgeAllowed": True, "knowledgeLoadedOnce": True, "diagnosticMode": "matrix-compact"},
        "summary": {
            "targetCount": target_count,
            "integrityFailureCount": integrity_failures,
            "plannerSupportedCount": sum(1 for item in results if item.get("plannerSupported")),
            "assemblyReachedCount": sum(1 for item in results if int(item.get("rankedAssemblyCount") or 0) > 0),
            "localCompleteCount": local_complete,
            "localCompleteRate": (local_complete / target_count) if target_count else 0.0,
            "stageCounts": dict(sorted(stage_counts.items())),
            "plannerStrategyCounts": dict(sorted(planner_counts.items())),
        },
        "targets": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a frozen puzzle-only heldout matrix using fragment knowledge only.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--puzzle-root", type=Path, required=True)
    parser.add_argument("--flow-index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--objective", default="balanced", choices=("balanced", "cycles", "instructions"))
    parser.add_argument("--composition-limit", type=int, default=30)
    parser.add_argument("--strict-isolation", action="store_true")
    args = parser.parse_args()
    matrix = evaluate_matrix(args.manifest, args.puzzle_root, args.flow_index, args.output_dir, objective=args.objective, composition_limit=args.composition_limit)
    output = args.output_dir / "matrix.json"
    output.write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(matrix["summary"], ensure_ascii=False))
    if args.strict_isolation and (matrix["summary"]["integrityFailureCount"] or any(item["stage"] == "isolation-failed" for item in matrix["targets"])):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
