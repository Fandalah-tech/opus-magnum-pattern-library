from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver.assembly import rank_fragment_assemblies
from packages.opus_solver.geometry_search import search_geometric_candidates
from packages.opus_solver.manufacturing_extensions import build_manufacturing_plan


def _compact_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "complete": bool(validation.get("complete")),
        "failureMode": validation.get("failureMode"),
        "totalDelivered": int(validation.get("totalDelivered") or 0),
        "totalDeficit": int(validation.get("totalDeficit") or 0),
        "completedCycles": int(validation.get("completedCycles") or 0),
        "terminatedWithError": bool(validation.get("terminatedWithError")),
        "firstError": validation.get("firstError"),
        "distinctRequiredChemistryEventCount": int(validation.get("distinctRequiredChemistryEventCount") or 0),
        "requiredChemistryEventCount": int(validation.get("requiredChemistryEventCount") or 0),
        "distinctChemistryEventCount": int(validation.get("distinctChemistryEventCount") or 0),
        "chemistryEventCount": int(validation.get("chemistryEventCount") or 0),
        "chemistryEventKinds": list(validation.get("chemistryEventKinds") or []),
        "chemistryEventTimeline": list(validation.get("chemistryEventTimeline") or [])[:40],
        "manipulationEventCount": int(validation.get("manipulationEventCount") or 0),
        "eventCounts": dict(validation.get("eventCounts") or {}),
    }


def _variant_rank(variant: dict[str, Any]) -> tuple[Any, ...]:
    validation = variant.get("validation") or {}
    return (
        int(bool(validation.get("complete"))),
        int(validation.get("totalDelivered") or 0),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(validation.get("requiredChemistryEventCount") or 0),
        int(validation.get("distinctChemistryEventCount") or 0),
        int(validation.get("chemistryEventCount") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        int(validation.get("manipulationEventCount") or 0),
        -int(variant.get("staticConflictPenalty") or 0),
        -int(variant.get("displacement") or 0),
    )


def probe_geometry_search(
    puzzle_path: Path,
    flow_index_path: Path,
    *,
    assembly_limit: int = 2,
    per_slot_limit: int = 12,
    variant_limit: int = 324,
    result_limit: int = 16,
    translation_radius: int = 1,
    rotation_radius: int = 1,
    preflight_cycles: int = 128,
    promotion_limit: int = 0,
    solution_output: Path | None = None,
) -> dict[str, Any]:
    puzzle = parse_puzzle(puzzle_path)
    knowledge = json.loads(flow_index_path.read_text(encoding="utf-8"))
    target_id = puzzle_path.stem
    if target_id.lower() in json.dumps(knowledge).lower():
        raise ValueError(f"Heldout target {target_id} appears in learned knowledge")

    plan = build_manufacturing_plan(puzzle)
    assemblies = rank_fragment_assemblies(
        plan,
        knowledge,
        limit=max(1, int(assembly_limit)),
    ) if plan.supported else []

    searches: list[dict[str, Any]] = []
    best_variant: dict[str, Any] | None = None
    best_assembly_rank: int | None = None
    for assembly_rank, assembly in enumerate(assemblies, start=1):
        result = search_geometric_candidates(
            puzzle,
            plan,
            assembly,
            knowledge,
            per_slot_limit=per_slot_limit,
            variant_limit=variant_limit,
            result_limit=result_limit,
            synthetic_translation_radius=translation_radius,
            synthetic_rotation_radius=rotation_radius,
            preflight_cycles=preflight_cycles,
            promotion_limit=promotion_limit,
        )
        compact_variants = []
        for variant in result.get("variants", []):
            compact_variants.append({
                "variantIndex": variant.get("variantIndex"),
                "displacement": variant.get("displacement"),
                "supportScore": variant.get("supportScore"),
                "staticConflictPenalty": variant.get("staticConflictPenalty"),
                "selectionObjectives": variant.get("selectionObjectives"),
                "validationScope": variant.get("validationScope"),
                "transformOverrides": variant.get("transformOverrides"),
                "validation": _compact_validation(variant.get("validation") or {}),
            })
            if best_variant is None or _variant_rank(variant) > _variant_rank(best_variant):
                best_variant = variant
                best_assembly_rank = assembly_rank
        searches.append({
            "assemblyRank": assembly_rank,
            "assemblyScore": assembly.get("score"),
            "coherentSourceSolution": assembly.get("coherentSourceSolution"),
            "requiredRelations": assembly.get("requiredRelations"),
            "observedRelations": assembly.get("observedRelations"),
            "summary": result.get("summary"),
            "variants": compact_variants,
        })

    output_solution = None
    if best_variant is not None and solution_output is not None and best_variant.get("solution"):
        solution_output.parent.mkdir(parents=True, exist_ok=True)
        write_solution(best_variant["solution"], solution_output)
        output_solution = str(solution_output)

    best = None
    if best_variant is not None:
        best = {
            "assemblyRank": best_assembly_rank,
            "variantIndex": best_variant.get("variantIndex"),
            "displacement": best_variant.get("displacement"),
            "supportScore": best_variant.get("supportScore"),
            "staticConflictPenalty": best_variant.get("staticConflictPenalty"),
            "validationScope": best_variant.get("validationScope"),
            "transformOverrides": best_variant.get("transformOverrides"),
            "validation": _compact_validation(best_variant.get("validation") or {}),
            "solutionOutput": output_solution,
        }

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-geometry-repair-probe",
        "targetPuzzle": puzzle_path.name,
        "targetSolutionBytesUsed": 0,
        "knowledgeSourceSolutionCount": len({
            str(path)
            for collection in ("fragments", "transitions", "convergenceMotifs")
            for item in (knowledge.get(collection) or [])
            for path in (item.get("sourceSolutions") or [])
        }),
        "planner": {
            "strategy": plan.strategy,
            "supported": plan.supported,
            "requiredGlyphs": list(plan.required_glyphs),
        },
        "request": {
            "assemblyLimit": assembly_limit,
            "perSlotLimit": per_slot_limit,
            "variantLimit": variant_limit,
            "resultLimit": result_limit,
            "translationRadius": translation_radius,
            "rotationRadius": rotation_radius,
            "preflightCycles": preflight_cycles,
            "promotionLimit": promotion_limit,
        },
        "rankedAssemblyCount": len(assemblies),
        "searches": searches,
        "bestVariant": best,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded target-solution-free geometry repair search on a heldout puzzle.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--flow-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solution-output", type=Path)
    parser.add_argument("--assembly-limit", type=int, default=2)
    parser.add_argument("--per-slot-limit", type=int, default=12)
    parser.add_argument("--variant-limit", type=int, default=324)
    parser.add_argument("--result-limit", type=int, default=16)
    parser.add_argument("--translation-radius", type=int, default=1)
    parser.add_argument("--rotation-radius", type=int, default=1)
    parser.add_argument("--preflight-cycles", type=int, default=128)
    parser.add_argument("--promotion-limit", type=int, default=0)
    args = parser.parse_args()

    report = probe_geometry_search(
        args.puzzle,
        args.flow_index,
        assembly_limit=args.assembly_limit,
        per_slot_limit=args.per_slot_limit,
        variant_limit=args.variant_limit,
        result_limit=args.result_limit,
        translation_radius=args.translation_radius,
        rotation_radius=args.rotation_radius,
        preflight_cycles=args.preflight_cycles,
        promotion_limit=args.promotion_limit,
        solution_output=args.solution_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "rankedAssemblyCount": report["rankedAssemblyCount"],
        "bestVariant": report["bestVariant"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
