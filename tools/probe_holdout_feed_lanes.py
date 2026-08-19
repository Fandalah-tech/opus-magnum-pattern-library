from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.assembly import rank_fragment_assemblies
from packages.opus_solver.candidate_solution import build_candidate_solution
from packages.opus_solver.feed_lane_repair import search_input_feed_lanes
from packages.opus_solver.layout import materialize_candidate_layout
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan
from packages.opus_solver.scheduling import materialize_candidate_schedule, synchronize_layout_programs


def _compact_validation(validation: dict[str, Any]) -> dict[str, Any]:
    counts = validation.get("eventCounts") or {}
    return {
        "complete": bool(validation.get("complete")),
        "failureMode": validation.get("failureMode"),
        "totalDelivered": int(validation.get("totalDelivered") or 0),
        "totalDeficit": int(validation.get("totalDeficit") or 0),
        "completedCycles": int(validation.get("completedCycles") or 0),
        "terminatedWithError": bool(validation.get("terminatedWithError")),
        "firstError": validation.get("firstError"),
        "requiredChemistryEventKinds": list(validation.get("requiredChemistryEventKinds") or []),
        "observedRequiredChemistryEventKinds": list(validation.get("observedRequiredChemistryEventKinds") or []),
        "distinctRequiredChemistryEventCount": int(validation.get("distinctRequiredChemistryEventCount") or 0),
        "requiredChemistryEventCount": int(validation.get("requiredChemistryEventCount") or 0),
        "chemistryEventCount": int(validation.get("chemistryEventCount") or 0),
        "chemistryEventKinds": list(validation.get("chemistryEventKinds") or []),
        "atomPurifiedCount": int(counts.get("atom-purified") or 0),
        "eventCounts": dict(counts),
        "manipulationEventCount": int(validation.get("manipulationEventCount") or 0),
        "blockedInputsAtStart": list(validation.get("blockedInputsAtStart") or []),
        "initialInputStatus": list(validation.get("initialInputStatus") or []),
    }


def _compact_conversion(opportunity: dict[str, Any]) -> dict[str, Any]:
    return {
        "skipped": bool(opportunity.get("skipped")),
        "skipReason": opportunity.get("skipReason"),
        "freeEqualPairObservationCount": int(opportunity.get("freeEqualPairObservationCount") or 0),
        "adjacentFreeEqualPairObservationCount": int(opportunity.get("adjacentFreeEqualPairObservationCount") or 0),
        "readyPurificationPoseObservationCount": int(opportunity.get("readyPurificationPoseObservationCount") or 0),
        "framesWithReadyPurificationPose": int(opportunity.get("framesWithReadyPurificationPose") or 0),
        "maxReadyPurificationPosesInFrame": int(opportunity.get("maxReadyPurificationPosesInFrame") or 0),
        "minFreeEqualPairDistance": opportunity.get("minFreeEqualPairDistance"),
        "readyPoseCountsByElement": dict(opportunity.get("readyPoseCountsByElement") or {}),
        "nearestFreeEqualPairSamples": list(opportunity.get("nearestFreeEqualPairSamples") or [])[:8],
        "readyPurificationSamples": list(opportunity.get("readyPurificationSamples") or [])[:8],
    }


def probe(
    puzzle_path: Path,
    flow_index_path: Path,
    seed_path: Path,
    *,
    max_grab_cycles: int = 256,
    validation_cycles: int = 320,
    placement_limit_per_input: int = 72,
    result_limit: int = 20,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    knowledge = json.loads(flow_index_path.read_text(encoding="utf-8"))
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    target_id = puzzle_path.stem
    if target_id.lower() in json.dumps(knowledge).lower():
        raise ValueError(f"Heldout target {target_id} appears in learned knowledge")
    if int(seed.get("targetSolutionBytesUsed") or 0) != 0:
        raise ValueError("Geometry seed is not target-solution-free")

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
    base_solution = build_candidate_solution(puzzle, plan, assembly, synchronized)
    search = search_input_feed_lanes(
        puzzle,
        base_solution,
        max_grab_cycles=max_grab_cycles,
        validation_cycles=validation_cycles,
        placement_limit_per_input=placement_limit_per_input,
        result_limit=result_limit,
    )

    compact_variants = []
    best_solution = None
    for index, variant in enumerate(search.get("variants") or []):
        compact_variants.append({
            "rank": index + 1,
            "inputId": variant.get("inputId"),
            "reagentIndex": variant.get("reagentIndex"),
            "originalPosition": variant.get("originalPosition"),
            "originalRotation": variant.get("originalRotation"),
            "position": variant.get("position"),
            "rotation": variant.get("rotation"),
            "translationDistance": variant.get("translationDistance"),
            "grabEvidence": variant.get("grabEvidence"),
            "mechanicsPreserved": variant.get("mechanicsPreserved"),
            "serialization": variant.get("serialization"),
            "validation": _compact_validation(variant.get("validation") or {}),
            "conversionOpportunity": _compact_conversion(variant.get("conversionOpportunity") or {}),
            "errorType": variant.get("errorType"),
            "error": variant.get("error"),
        })
        if index == 0 and variant.get("solution") is not None:
            best_solution = variant["solution"]

    output_solution = None
    if best_solution is not None and solution_output is not None:
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_solution, solution_output)
        output_solution = str(solution_output)

    return {
        "schemaVersion": "0.2.0",
        "kind": "strict-heldout-feed-lane-probe",
        "targetPuzzle": puzzle_path.name,
        "targetSolutionBytesUsed": 0,
        "seedRunId": seed.get("runId"),
        "seedSourceCommit": seed.get("sourceCommit"),
        "assemblyRank": assembly_rank,
        "assemblyScore": assembly.get("score"),
        "coherentSourceSolution": assembly.get("coherentSourceSolution"),
        "transformOverrides": overrides,
        "request": {
            "maxGrabCycles": max_grab_cycles,
            "validationCycles": validation_cycles,
            "placementLimitPerInput": placement_limit_per_input,
            "resultLimit": result_limit,
        },
        "searchSummary": search.get("summary"),
        "variants": compact_variants,
        "bestSolutionOutput": output_solution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Search alternate learned grab lanes for a heldout target reagent.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--flow-index", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-grab-cycles", type=int, default=256)
    parser.add_argument("--validation-cycles", type=int, default=320)
    parser.add_argument("--placement-limit-per-input", type=int, default=72)
    parser.add_argument("--result-limit", type=int, default=20)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.flow_index,
        args.seed,
        max_grab_cycles=max(1, int(args.max_grab_cycles)),
        validation_cycles=max(1, int(args.validation_cycles)),
        placement_limit_per_input=max(0, int(args.placement_limit_per_input)),
        result_limit=max(0, int(args.result_limit)),
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "searchSummary": report["searchSummary"],
        "bestVariant": (report.get("variants") or [None])[0],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
