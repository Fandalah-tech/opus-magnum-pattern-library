from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.autonomous import solve_puzzle_from_knowledge


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_strings(item)


def target_knowledge_mentions(
    knowledge: dict[str, Any],
    target_puzzle_id: str,
) -> list[str]:
    """Return strings in reusable knowledge that mention the held-out target.

    A blind-transfer benchmark must not merely avoid opening target solution
    files at runtime; the learned index itself must also have been built
    without target-derived provenance.  This conservative check catches the
    target puzzle identifier anywhere in the serialized knowledge payload.
    """

    needle = target_puzzle_id.strip().lower()
    if not needle:
        raise ValueError("target_puzzle_id must not be empty")
    return sorted({value for value in _walk_strings(knowledge) if needle in value.lower()})


def knowledge_source_solutions(knowledge: dict[str, Any]) -> list[str]:
    paths: set[str] = set()
    for collection_name in ("fragments", "transitions", "convergenceMotifs"):
        for item in knowledge.get(collection_name, []) or []:
            for path in item.get("sourceSolutions", []) or []:
                if path:
                    paths.add(str(path))
    return sorted(paths)


def evaluate_holdout_transfer(
    puzzle_path: Path,
    flow_index_path: Path,
    *,
    target_puzzle_id: str,
    objective: str = "balanced",
    composition_limit: int = 20,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    knowledge = json.loads(flow_index_path.read_text(encoding="utf-8"))
    mentions = target_knowledge_mentions(knowledge, target_puzzle_id)
    sources = knowledge_source_solutions(knowledge)

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
        "knowledgeSourceSolutionCount": len(sources),
        "knowledgeSourceSolutions": sources[:50],
    }

    report: dict[str, Any] = {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-knowledge-transfer",
        "target": {
            "id": target_puzzle_id,
            "name": puzzle.get("name"),
            "source": puzzle.get("source"),
        },
        "protocol": protocol,
        "request": {
            "objective": objective,
            "compositionLimit": int(composition_limit),
            "directGeneratorAllowed": False,
            "learnedArchitectureBankAllowed": False,
            "fragmentKnowledgeAllowed": True,
        },
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
        report["result"]["error"] = (
            f"Held-out target {target_puzzle_id!r} appears in reusable knowledge"
        )
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate fragment-knowledge transfer on a held-out puzzle without "
            "allowing target solution bytes, direct generators or target-specific "
            "learned architectures."
        )
    )
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--flow-index", type=Path, required=True)
    parser.add_argument("--target-puzzle-id", required=True)
    parser.add_argument("--objective", default="balanced", choices=("balanced", "cycles", "instructions"))
    parser.add_argument("--composition-limit", type=int, default=20)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict-isolation", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    report = evaluate_holdout_transfer(
        args.puzzle,
        args.flow_index,
        target_puzzle_id=args.target_puzzle_id,
        objective=args.objective,
        composition_limit=args.composition_limit,
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "target": report["target"],
        "protocol": {
            "targetSolutionBytesUsed": report["protocol"]["targetSolutionBytesUsed"],
            "targetExcludedFromKnowledge": report["protocol"]["targetExcludedFromKnowledge"],
        },
        "result": report["result"],
    }, ensure_ascii=False))

    if args.strict_isolation and not report["protocol"]["targetExcludedFromKnowledge"]:
        return 2
    if args.require_complete and not report["result"]["complete"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
