from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.assembly import rank_fragment_assemblies
from packages.opus_solver.candidate_solution import build_candidate_solution, serialize_candidate_roundtrip
from packages.opus_solver.layout import materialize_candidate_layout
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan
from packages.opus_solver.scheduling import materialize_candidate_schedule, synchronize_layout_programs
from packages.opus_solver.solver import validate_generated_solution


def _compact_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(validation.get("complete")),
        "failureMode": validation.get("failureMode"),
        "totalDelivered": int(validation.get("totalDelivered") or 0),
        "totalDeficit": int(validation.get("totalDeficit") or 0),
        "requestedCycles": int(validation.get("requestedCycles") or 0),
        "completedCycles": int(validation.get("completedCycles") or 0),
        "terminatedWithError": bool(validation.get("terminatedWithError")),
        "firstError": validation.get("firstError"),
        "requiredChemistryEventKinds": list(validation.get("requiredChemistryEventKinds") or []),
        "observedRequiredChemistryEventKinds": list(validation.get("observedRequiredChemistryEventKinds") or []),
        "distinctRequiredChemistryEventCount": int(validation.get("distinctRequiredChemistryEventCount") or 0),
        "requiredChemistryEventCount": int(validation.get("requiredChemistryEventCount") or 0),
        "requiredChemistryEventTimeline": list(validation.get("requiredChemistryEventTimeline") or [])[:120],
        "chemistryEventKinds": list(validation.get("chemistryEventKinds") or []),
        "chemistryEventCount": int(validation.get("chemistryEventCount") or 0),
        "chemistryEventTimeline": list(validation.get("chemistryEventTimeline") or [])[:120],
        "manipulationEventCount": int(validation.get("manipulationEventCount") or 0),
        "eventCounts": dict(validation.get("eventCounts") or {}),
        "initialInputStatus": list(validation.get("initialInputStatus") or []),
    }


def followup(
    puzzle_path: Path,
    flow_index_path: Path,
    seed_path: Path,
    *,
    max_cycles: int,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    knowledge = json.loads(flow_index_path.read_text(encoding="utf-8"))
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    target_id = puzzle_path.stem
    if target_id.lower() in json.dumps(knowledge).lower():
        raise ValueError(f"Heldout target {target_id} appears in learned knowledge")
    if int(seed.get("targetSolutionBytesUsed") or 0) != 0:
        raise ValueError("Seed checkpoint is not target-solution-free")

    best = seed.get("bestVariant") or {}
    assembly_rank = max(1, int(best.get("assemblyRank") or 1))
    overrides = best.get("transformOverrides") or {}
    plan = build_manufacturing_plan(puzzle)
    assemblies = rank_fragment_assemblies(plan, knowledge, limit=assembly_rank) if plan.supported else []
    if len(assemblies) < assembly_rank:
        raise ValueError(f"Could not reconstruct assembly rank {assembly_rank}")
    assembly = assemblies[assembly_rank - 1]

    layout = materialize_candidate_layout(assembly, knowledge, transform_overrides=overrides)
    schedule = materialize_candidate_schedule(assembly)
    synchronized = synchronize_layout_programs(layout, schedule)
    solution = build_candidate_solution(puzzle, plan, assembly, synchronized)
    roundtrip = serialize_candidate_roundtrip(solution)
    validation = validate_generated_solution(puzzle, roundtrip["parsed"], max_cycles=max_cycles)

    if solution_output is not None:
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(solution, solution_output)

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-geometry-followup",
        "targetPuzzle": puzzle_path.name,
        "targetSolutionBytesUsed": 0,
        "seedRunId": seed.get("runId"),
        "seedSourceCommit": seed.get("sourceCommit"),
        "assemblyRank": assembly_rank,
        "assemblyScore": assembly.get("score"),
        "coherentSourceSolution": assembly.get("coherentSourceSolution"),
        "transformOverrides": overrides,
        "maxCycles": int(max_cycles),
        "layoutSummary": layout.get("summary"),
        "scheduleSummary": schedule.get("summary"),
        "synchronizedSummary": synchronized.get("summary"),
        "serialization": roundtrip.get("diagnostics"),
        "validation": _compact_validation(validation),
        "solutionOutput": str(solution_output) if solution_output is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a target-free geometry repair for a longer bounded horizon.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--flow-index", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=4096)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = followup(
        args.puzzle,
        args.flow_index,
        args.seed,
        max_cycles=max(1, int(args.max_cycles)),
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "seedRunId": report["seedRunId"],
        "validation": report["validation"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
