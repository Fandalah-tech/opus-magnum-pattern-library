from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver import build_manufacturing_plan, puzzle_file_id, solve_puzzle_from_knowledge
from packages.opus_validator import build_command, classify_result
from tools.evaluate_holdout_transfer import target_knowledge_mentions


DEFAULT_MANIFEST = REPOSITORY_ROOT / "datasets" / "opussolver-puzzle-benchmark.json"
DEFAULT_FLOW_INDEX = REPOSITORY_ROOT / "database" / "engine-fragment-flow-index.json"


class BenchmarkContractError(RuntimeError):
    """Raised when the external benchmark isolation contract is violated."""


def _git_output(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _collection(manifest: dict[str, Any], collection_id: str) -> dict[str, Any]:
    for item in manifest.get("collections", []) or []:
        if item.get("id") == collection_id:
            return item
    raise BenchmarkContractError(f"Unknown benchmark collection: {collection_id}")


def verify_pinned_checkout(
    corpus_root: Path,
    manifest: dict[str, Any],
    collection: dict[str, Any],
) -> dict[str, Any]:
    expected_commit = str(manifest.get("pinnedCommit") or "")
    actual_commit = _git_output(corpus_root, "rev-parse", "HEAD")
    if actual_commit != expected_commit:
        raise BenchmarkContractError(
            f"OpusSolver checkout drift: expected {expected_commit}, got {actual_commit}"
        )

    path = str(collection.get("path") or "")
    expected_tree = str(collection.get("sourceTreeSha") or "")
    actual_tree = _git_output(corpus_root, "rev-parse", f"HEAD:{path}")
    if expected_tree and actual_tree != expected_tree:
        raise BenchmarkContractError(
            f"Collection tree drift for {collection['id']}: expected {expected_tree}, got {actual_tree}"
        )
    return {
        "verified": True,
        "expectedCommit": expected_commit,
        "actualCommit": actual_commit,
        "expectedCollectionTreeSha": expected_tree or None,
        "actualCollectionTreeSha": actual_tree,
    }


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.") or "target"


def _omsim_validate(
    omsim: Path,
    puzzle_path: Path,
    solution_path: Path,
    *,
    timeout: int,
) -> dict[str, Any]:
    command = build_command(str(omsim), puzzle_path, solution_path)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return classify_result(completed.returncode, output)


def _target_record(path: Path, corpus_root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(corpus_root).as_posix(),
        "targetPuzzleId": None,
        "targetName": None,
        "status": "pending",
        "failureStage": None,
        "plannerStrategy": None,
        "candidateCount": 0,
        "completeCandidateCount": 0,
        "localComplete": False,
        "localMetrics": None,
        "omsim": None,
        "errorType": None,
        "error": None,
    }


def benchmark_collection(
    corpus_root: Path,
    manifest_path: Path,
    flow_index_path: Path,
    collection_id: str,
    output_dir: Path,
    *,
    objective: str = "balanced",
    composition_limit: int = 30,
    offset: int = 0,
    limit: int = 0,
    omsim: Path | None = None,
    omsim_timeout: int = 60,
    allow_sealed: bool = False,
    retain_solutions: bool = False,
    verify_source: bool = True,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collection = _collection(manifest, collection_id)
    policy = manifest.get("policy") or {}
    sealed = collection.get("role") == "sealed-heldout"
    if sealed and not allow_sealed:
        raise BenchmarkContractError(
            f"Collection {collection_id!r} is sealed held-out; pass --allow-sealed explicitly to consume it"
        )
    if sealed and retain_solutions:
        raise BenchmarkContractError("Sealed held-out solutions may not be retained")

    source_verification = (
        verify_pinned_checkout(corpus_root, manifest, collection)
        if verify_source
        else {
            "verified": False,
            "reason": "verification-skipped",
            "expectedCommit": manifest.get("pinnedCommit"),
        }
    )

    collection_root = corpus_root / str(collection["path"])
    if not collection_root.is_dir():
        raise BenchmarkContractError(f"Collection directory is missing: {collection_root}")
    puzzle_paths = sorted(collection_root.rglob("*.puzzle"))
    expected_count = collection.get("expectedPuzzleCount")
    if expected_count is not None and len(puzzle_paths) != int(expected_count):
        raise BenchmarkContractError(
            f"Collection {collection_id} expected {expected_count} puzzle files, found {len(puzzle_paths)}"
        )

    start = max(0, int(offset))
    stop = None if int(limit) <= 0 else start + int(limit)
    selected_paths = puzzle_paths[start:stop]
    knowledge = json.loads(flow_index_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    failure_stages: Counter[str] = Counter()

    parse_success = 0
    leak_count = 0
    planner_supported = 0
    candidate_available = 0
    local_complete = 0
    solver_errors = 0
    omsim_tested = 0
    omsim_valid = 0

    output_dir.mkdir(parents=True, exist_ok=True)
    solution_root = output_dir / "solutions"
    if retain_solutions:
        solution_root.mkdir(parents=True, exist_ok=True)

    for puzzle_path in selected_paths:
        record = _target_record(puzzle_path, corpus_root)
        records.append(record)
        try:
            puzzle = parse_puzzle(puzzle_path)
            parse_success += 1
        except Exception as error:
            record.update({
                "status": "parse-failed",
                "failureStage": "parse",
                "errorType": type(error).__name__,
                "error": str(error),
            })
            failure_stages["parse"] += 1
            continue

        target_id = puzzle_file_id(puzzle)
        record["targetPuzzleId"] = target_id
        record["targetName"] = puzzle.get("name")
        mentions = target_knowledge_mentions(knowledge, target_id)
        if mentions:
            leak_count += 1
            record.update({
                "status": "knowledge-leak",
                "failureStage": "knowledge-leak",
                "errorType": "TargetKnowledgeLeakError",
                "error": f"{target_id!r} appears in reusable knowledge",
            })
            failure_stages["knowledge-leak"] += 1
            continue

        try:
            plan = build_manufacturing_plan(puzzle)
        except Exception as error:
            record.update({
                "status": "planner-error",
                "failureStage": "planner",
                "errorType": type(error).__name__,
                "error": str(error),
            })
            failure_stages["planner"] += 1
            continue
        record["plannerStrategy"] = plan.strategy
        if not plan.supported:
            record.update({
                "status": "planner-unsupported",
                "failureStage": "planner",
                "error": plan.reason,
            })
            failure_stages["planner"] += 1
            continue
        planner_supported += 1

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
        except Exception as error:
            solver_errors += 1
            record.update({
                "status": "solver-error",
                "failureStage": "local-solve",
                "errorType": type(error).__name__,
                "error": str(error),
            })
            failure_stages["local-solve"] += 1
            continue

        tested = int(validation.get("compositionTestedCandidateCount") or 0)
        completed = int(validation.get("compositionCompleteCandidateCount") or 0)
        record["candidateCount"] = tested
        record["completeCandidateCount"] = completed
        record["localMetrics"] = validation.get("localCandidateMetrics")
        if tested <= 0:
            record.update({"status": "no-candidates", "failureStage": "composition"})
            failure_stages["composition"] += 1
            continue
        candidate_available += 1

        complete = bool(validation.get("complete"))
        record["localComplete"] = complete
        if not complete:
            record.update({"status": "local-incomplete", "failureStage": "local-solve"})
            failure_stages["local-solve"] += 1
            continue
        local_complete += 1

        if omsim is None:
            record["status"] = "local-complete"
            continue

        omsim_tested += 1
        target_filename = f"{_safe_name(target_id)}.solution"
        if retain_solutions:
            solution_path = solution_root / target_filename
            write_solution(solved.solution, solution_path)
            try:
                oracle = _omsim_validate(omsim, puzzle_path, solution_path, timeout=omsim_timeout)
            except Exception as error:
                oracle = {
                    "status": "validator-error",
                    "valid": None,
                    "metrics": {},
                    "issues": [{"severity": "error", "code": type(error).__name__, "message": str(error)}],
                }
        else:
            with tempfile.TemporaryDirectory(prefix="om-benchmark-") as temporary:
                solution_path = Path(temporary) / target_filename
                write_solution(solved.solution, solution_path)
                try:
                    oracle = _omsim_validate(omsim, puzzle_path, solution_path, timeout=omsim_timeout)
                except Exception as error:
                    oracle = {
                        "status": "validator-error",
                        "valid": None,
                        "metrics": {},
                        "issues": [{"severity": "error", "code": type(error).__name__, "message": str(error)}],
                    }
        record["omsim"] = oracle
        if oracle.get("valid") is True:
            omsim_valid += 1
            record["status"] = "omsim-valid"
        else:
            record.update({"status": "omsim-invalid", "failureStage": "omsim"})
            failure_stages["omsim"] += 1

    selected_count = len(selected_paths)
    report_records = [] if sealed and policy.get("sealedTargetDetailsRedacted", True) else records
    summary = {
        "collectionPuzzleCount": len(puzzle_paths),
        "selectedPuzzleCount": selected_count,
        "parseSuccessCount": parse_success,
        "parseFailureCount": selected_count - parse_success,
        "knowledgeLeakCount": leak_count,
        "plannerSupportedCount": planner_supported,
        "plannerUnsupportedOrErrorCount": parse_success - leak_count - planner_supported,
        "candidateAvailableCount": candidate_available,
        "candidateUnavailableCount": max(0, planner_supported - candidate_available - solver_errors),
        "localCompleteCount": local_complete,
        "localIncompleteOrErrorCount": max(0, planner_supported - local_complete),
        "solverErrorCount": solver_errors,
        "omsimTestedCount": omsim_tested,
        "omsimValidCount": omsim_valid,
        "omsimInvalidOrErrorCount": omsim_tested - omsim_valid,
        "targetSolutionBytesUsed": 0,
        "failureStageCounts": dict(sorted(failure_stages.items())),
    }
    report = {
        "schemaVersion": "0.1.0",
        "kind": "external-puzzle-blind-benchmark",
        "datasetId": manifest.get("id"),
        "repository": manifest.get("repository"),
        "pinnedCommit": manifest.get("pinnedCommit"),
        "sourceVerification": source_verification,
        "collection": {
            "id": collection.get("id"),
            "path": collection.get("path"),
            "role": collection.get("role"),
            "expectedPuzzleCount": expected_count,
            "sourceTreeSha": collection.get("sourceTreeSha"),
            "sealed": sealed,
            "sealedDetailsRedacted": bool(sealed and policy.get("sealedTargetDetailsRedacted", True)),
        },
        "protocol": {
            "targetSolutionBytesUsed": 0,
            "targetSolutionInputsAccepted": False,
            "targetSolutionFilesScanned": False,
            "trainingAllowed": False,
            "directGeneratorAllowed": False,
            "learnedArchitectureBankAllowed": False,
            "fragmentKnowledgeAllowed": True,
            "knowledgePath": str(flow_index_path),
        },
        "request": {
            "objective": objective,
            "compositionLimit": int(composition_limit),
            "offset": start,
            "limit": int(limit),
            "omsimEnabled": omsim is not None,
            "retainSolutions": bool(retain_solutions),
        },
        "summary": summary,
        "targets": report_records,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {**report, "reportPath": str(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark strict knowledge-only solving against a pinned OpusSolver puzzle collection."
    )
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--flow-index", type=Path, default=DEFAULT_FLOW_INDEX)
    parser.add_argument("--collection", default="24hour-1-sample")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--objective", default="balanced", choices=("balanced", "cycles", "instructions"))
    parser.add_argument("--composition-limit", type=int, default=30)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="0 means all puzzles in the collection")
    parser.add_argument("--omsim", type=Path)
    parser.add_argument("--omsim-timeout", type=int, default=60)
    parser.add_argument("--allow-sealed", action="store_true")
    parser.add_argument("--retain-solutions", action="store_true")
    parser.add_argument("--skip-source-verification", action="store_true")
    args = parser.parse_args()

    try:
        report = benchmark_collection(
            args.corpus_root,
            args.manifest,
            args.flow_index,
            args.collection,
            args.output_dir,
            objective=args.objective,
            composition_limit=args.composition_limit,
            offset=args.offset,
            limit=args.limit,
            omsim=args.omsim,
            omsim_timeout=args.omsim_timeout,
            allow_sealed=args.allow_sealed,
            retain_solutions=args.retain_solutions,
            verify_source=not args.skip_source_verification,
        )
    except BenchmarkContractError as error:
        print(json.dumps({"status": "contract-error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({
        "status": "complete",
        "collection": report["collection"],
        "summary": report["summary"],
        "reportPath": report["reportPath"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
