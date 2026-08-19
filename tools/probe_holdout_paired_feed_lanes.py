from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.assembly import rank_fragment_assemblies
from packages.opus_solver.candidate_solution import build_candidate_solution
from packages.opus_solver.layout import materialize_candidate_layout
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan
from packages.opus_solver.paired_feed_lane_repair import search_paired_input_feed_lanes
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
        "blockedInputsAtStart": list(validation.get("blockedInputsAtStart") or []),
        "missingProductOutputIndices": list(validation.get("missingProductOutputIndices") or []),
        "observedRequiredChemistryEventKinds": list(validation.get("observedRequiredChemistryEventKinds") or []),
        "distinctRequiredChemistryEventCount": int(validation.get("distinctRequiredChemistryEventCount") or 0),
        "requiredChemistryEventCount": int(validation.get("requiredChemistryEventCount") or 0),
        "atomPurifiedCount": int(counts.get("atom-purified") or 0),
        "chemistryEventCount": int(validation.get("chemistryEventCount") or 0),
        "chemistryEventKinds": list(validation.get("chemistryEventKinds") or []),
        "eventCounts": dict(counts),
        "manipulationEventCount": int(validation.get("manipulationEventCount") or 0),
    }


def _compact_conversion(opportunity: dict[str, Any]) -> dict[str, Any]:
    return {
        "skipped": bool(opportunity.get("skipped")),
        "skipReason": opportunity.get("skipReason"),
        "freeEqualPairObservationCount": int(opportunity.get("freeEqualPairObservationCount") or 0),
        "adjacentFreeEqualPairObservationCount": int(opportunity.get("adjacentFreeEqualPairObservationCount") or 0),
        "readyPurificationPoseObservationCount": int(opportunity.get("readyPurificationPoseObservationCount") or 0),
        "framesWithReadyPurificationPose": int(opportunity.get("framesWithReadyPurificationPose") or 0),
        "minFreeEqualPairDistance": opportunity.get("minFreeEqualPairDistance"),
        "readyPoseCountsByElement": dict(opportunity.get("readyPoseCountsByElement") or {}),
        "nearestFreeEqualPairSamples": list(opportunity.get("nearestFreeEqualPairSamples") or [])[:10],
        "readyPurificationSamples": list(opportunity.get("readyPurificationSamples") or [])[:10],
    }


def probe(
    puzzle_path: Path,
    flow_index_path: Path,
    seed_path: Path,
    *,
    max_grab_cycles: int = 256,
    validation_cycles: int = 256,
    first_stage_placement_limit: int = 72,
    first_stage_result_limit: int = 6,
    second_stage_placement_limit: int = 48,
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
    search = search_paired_input_feed_lanes(
        puzzle,
        base_solution,
        max_grab_cycles=max_grab_cycles,
        validation_cycles=validation_cycles,
        first_stage_placement_limit=first_stage_placement_limit,
        first_stage_result_limit=first_stage_result_limit,
        second_stage_placement_limit=second_stage_placement_limit,
        result_limit=result_limit,
    )

    compact_variants = []
    best_solution = None
    for index, variant in enumerate(search.get("variants") or []):
        compact_variants.append({
            "rank": index + 1,
            "seedRank": variant.get("seedRank"),
            "firstChangedInputId": variant.get("firstChangedInputId"),
            "firstPosition": variant.get("firstPosition"),
            "firstRotation": variant.get("firstRotation"),
            "secondChangedInputId": variant.get("secondChangedInputId"),
            "secondPosition": variant.get("secondPosition"),
            "secondRotation": variant.get("secondRotation"),
            "secondTranslationDistance": variant.get("secondTranslationDistance"),
            "secondGrabEvidence": variant.get("secondGrabEvidence"),
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
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-paired-feed-lane-probe",
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
            "firstStagePlacementLimit": first_stage_placement_limit,
            "firstStageResultLimit": first_stage_result_limit,
            "secondStagePlacementLimit": second_stage_placement_limit,
            "resultLimit": result_limit,
        },
        "searchSummary": search.get("summary"),
        "firstStage": search.get("firstStage"),
        "variants": compact_variants,
        "bestSolutionOutput": output_solution,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Search paired target-free input lanes toward purification-ready replay states.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--flow-index", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--max-grab-cycles", type=int, default=256)
    parser.add_argument("--validation-cycles", type=int, default=256)
    parser.add_argument("--first-stage-placement-limit", type=int, default=72)
    parser.add_argument("--first-stage-result-limit", type=int, default=6)
    parser.add_argument("--second-stage-placement-limit", type=int, default=48)
    parser.add_argument("--result-limit", type=int, default=20)
    args = parser.parse_args()

    report = probe(
        args.puzzle,
        args.flow_index,
        args.seed,
        max_grab_cycles=max(1, int(args.max_grab_cycles)),
        validation_cycles=max(1, int(args.validation_cycles)),
        first_stage_placement_limit=max(0, int(args.first_stage_placement_limit)),
        first_stage_result_limit=max(0, int(args.first_stage_result_limit)),
        second_stage_placement_limit=max(0, int(args.second_stage_placement_limit)),
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
