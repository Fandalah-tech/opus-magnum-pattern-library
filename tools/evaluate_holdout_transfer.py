from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.assembly import rank_fragment_assemblies
from packages.opus_solver.autonomous import solve_puzzle_from_knowledge
from packages.opus_solver.chemistry_composition import (
    manufacturing_requirements,
    rank_chains_for_manufacturing_plan,
    required_flow_relations,
)
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan


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


def _molecule_profile(molecule: dict[str, Any]) -> dict[str, Any]:
    atoms = list(molecule.get("atoms") or [])
    bonds = list(molecule.get("bonds") or [])
    return {
        "atomCount": len(atoms),
        "elements": dict(sorted(Counter(str(atom.get("element") or "") for atom in atoms).items())),
        "bondCount": len(bonds),
        "bondTypes": dict(sorted(Counter(str(bond.get("type") or "normal") for bond in bonds).items())),
        "atoms": [
            {
                "element": str(atom.get("element") or ""),
                "position": list(atom.get("position") or (0, 0)),
            }
            for atom in atoms
        ],
        "bonds": [
            {
                "type": str(bond.get("type") or "normal"),
                "from": list(bond.get("from") or (0, 0)),
                "to": list(bond.get("to") or (0, 0)),
            }
            for bond in bonds
        ],
    }


def puzzle_transfer_profile(puzzle: dict[str, Any]) -> dict[str, Any]:
    plan = build_manufacturing_plan(puzzle)
    available = puzzle.get("availableParts") or {}
    return {
        "reagentCount": len(puzzle.get("reagents") or []),
        "productCount": len(puzzle.get("products") or []),
        "reagents": [_molecule_profile(item) for item in (puzzle.get("reagents") or [])],
        "products": [_molecule_profile(item) for item in (puzzle.get("products") or [])],
        "availableArms": list(available.get("arms") or []),
        "availableGlyphs": list(available.get("glyphs") or []),
        "planner": {
            "strategy": plan.strategy,
            "supported": plan.supported,
            "reason": plan.reason,
            "operationKinds": [operation.kind for operation in plan.operations],
            "requiredGlyphs": list(plan.required_glyphs),
        },
    }


def _composition_diagnostics(
    puzzle: dict[str, Any],
    knowledge: dict[str, Any],
    *,
    limit: int,
) -> dict[str, Any]:
    plan = build_manufacturing_plan(puzzle)
    requirements = manufacturing_requirements(plan)
    required = required_flow_relations(plan)
    motifs = list(knowledge.get("convergenceMotifs") or [])
    motif_input_counts = [len(item.get("inputs") or []) for item in motifs]
    relation_counts = dict((knowledge.get("summary") or {}).get("relationCounts") or {})
    assemblies = rank_fragment_assemblies(
        plan,
        knowledge,
        limit=max(1, int(limit)),
    ) if plan.supported else []
    # Evaluate linear functional coverage as a diagnostic even when the planner
    # correctly declares that a convergence is required.  This separates
    # "chemistry absent" from "DAG assembly unavailable".
    chains = rank_chains_for_manufacturing_plan(
        plan,
        knowledge,
        fragment_index=knowledge,
        limit=max(1, int(limit)),
        min_engine_validated_solutions=1,
    ) if plan.supported else []
    return {
        "manufacturingRequirements": requirements,
        "requiredRelations": dict(sorted(required.items())),
        "knowledgeRelationCounts": relation_counts,
        "convergenceMotifCount": len(motifs),
        "convergenceMotifInputCounts": dict(sorted(Counter(motif_input_counts).items())),
        "maxConvergenceInputs": max(motif_input_counts, default=0),
        "rankedAssemblyCount": len(assemblies),
        "rankedChainCount": len(chains),
        "bestAssemblies": [
            {
                "score": item.get("score"),
                "sourceCount": item.get("sourceCount"),
                "convergenceInputCount": item.get("convergenceInputCount"),
                "observedRelations": item.get("observedRelations"),
                "inferredRelations": item.get("inferredRelations"),
                "requiredRelations": item.get("requiredRelations"),
            }
            for item in assemblies[:3]
        ],
        "bestChains": [
            {
                "score": item.get("score"),
                "stepCount": item.get("stepCount"),
                "coverage": (item.get("manufacturing") or {}).get("coverage"),
                "assemblyComplete": (item.get("manufacturing") or {}).get("assemblyComplete"),
            }
            for item in chains[:3]
        ],
    }


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
    profile = puzzle_transfer_profile(puzzle)
    composition = _composition_diagnostics(
        puzzle,
        knowledge,
        limit=composition_limit,
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
        "knowledgeSourceSolutionCount": len(sources),
        "knowledgeSourceSolutions": sources[:50],
    }

    report: dict[str, Any] = {
        "schemaVersion": "0.3.0",
        "kind": "strict-heldout-knowledge-transfer",
        "target": {
            "id": target_puzzle_id,
            "name": puzzle.get("name"),
            "source": puzzle.get("source"),
            "profile": profile,
        },
        "protocol": protocol,
        "request": {
            "objective": objective,
            "compositionLimit": int(composition_limit),
            "directGeneratorAllowed": False,
            "learnedArchitectureBankAllowed": False,
            "fragmentKnowledgeAllowed": True,
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
        "compositionDiagnostics": report["compositionDiagnostics"],
        "result": report["result"],
    }, ensure_ascii=False))

    if args.strict_isolation and not report["protocol"]["targetExcludedFromKnowledge"]:
        return 2
    if args.require_complete and not report["result"]["complete"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
