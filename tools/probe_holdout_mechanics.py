from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle
from packages.opus_solver.assembly import rank_fragment_assemblies
from packages.opus_solver.chemistry_composition import required_flow_relations
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan
from tools.evaluate_holdout_transfer import _mechanical_candidate_diagnostics


def probe(puzzle_path: Path, flow_index_path: Path, *, limit: int = 1) -> dict:
    puzzle = parse_puzzle(puzzle_path)
    knowledge = json.loads(flow_index_path.read_text(encoding="utf-8"))
    plan = build_manufacturing_plan(puzzle)
    assemblies = rank_fragment_assemblies(plan, knowledge, limit=max(1, int(limit))) if plan.supported else []
    return {
        "schemaVersion": "0.1.0",
        "kind": "heldout-mechanical-probe",
        "targetPuzzle": puzzle_path.name,
        "targetSolutionBytesUsed": 0,
        "planner": {
            "strategy": plan.strategy,
            "supported": plan.supported,
            "requiredGlyphs": list(plan.required_glyphs),
            "requiredRelations": dict(sorted(required_flow_relations(plan).items())),
        },
        "rankedAssemblyCount": len(assemblies),
        "candidates": _mechanical_candidate_diagnostics(
            puzzle,
            knowledge,
            assemblies,
            limit=max(1, int(limit)),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect materialized fragment candidates without target solution data.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--flow-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    report = probe(args.puzzle, args.flow_index, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "planner": report["planner"],
        "rankedAssemblyCount": report["rankedAssemblyCount"],
        "candidateCount": len(report["candidates"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
