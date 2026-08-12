from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver import build_outcome_index, generate_composed_candidates


def _best_writable(result: dict) -> dict | None:
    complete = []
    fallback = []
    for item in result.get("candidates", []):
        if item.get("serialization", {}).get("roundTripClean") and item.get("solution"):
            fallback.append(item)
            if item.get("engineValidation", {}).get("complete"):
                complete.append(item)
        for search_name in ("temporalSearch", "geometricSearch"):
            for variant in item.get(search_name, {}).get("variants", []):
                if variant.get("serialization", {}).get("roundTripClean") and variant.get("solution"):
                    fallback.append(variant)
                    if variant.get("validation", {}).get("complete"):
                        complete.append(variant)
    return complete[0] if complete else (fallback[0] if fallback else None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate database-driven Opus Magnum candidate solutions from fragment assembly priors.")
    parser.add_argument("puzzle", type=Path)
    parser.add_argument("--flow-index", type=Path, default=Path("database/fragment-flow-index.json"))
    parser.add_argument("--fragment-index", type=Path, default=Path("database/fragment-index.json"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--no-engine-validation", action="store_true")
    parser.add_argument("--temporal-radius", type=int, default=0, help="Search +/- N cycles of relative branch/tail timing around failed candidates.")
    parser.add_argument("--temporal-variants", type=int, default=81, help="Maximum timing variants tested per assembly candidate.")
    parser.add_argument("--temporal-results", type=int, default=10, help="Best timing variants retained in the JSON report.")
    parser.add_argument("--transform-variants", type=int, default=0, help="Maximum observed relative-transform combinations tested after timing repair fails.")
    parser.add_argument("--transform-per-slot", type=int, default=3, help="Maximum observed transform choices retained for each fragment join.")
    parser.add_argument("--transform-results", type=int, default=10, help="Best geometric variants retained in the JSON report.")
    parser.add_argument("--chain-max-depth", type=int, default=8, help="Maximum engine-observed transitions in a linear materialized chain.")
    parser.add_argument("--min-engine-validated-solutions", type=int, default=0, help="Require every selected transition to have at least this many engine-complete source solutions.")
    parser.add_argument("--report", type=Path, default=Path("reports/composed-candidates.json"))
    parser.add_argument("--write-best", type=Path)
    parser.add_argument("--write-complete-dir", type=Path, help="Write every engine-complete base/search candidate as a .solution file.")
    parser.add_argument("--outcome-index", type=Path, help="Merge compact learning outcomes into this persistent JSON index.")
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    flow_index = json.loads(args.flow_index.read_text(encoding="utf-8"))
    fragment_index = json.loads(args.fragment_index.read_text(encoding="utf-8"))
    result = generate_composed_candidates(
        puzzle,
        flow_index,
        fragment_index,
        limit=args.limit,
        validate_engine=not args.no_engine_validation,
        temporal_search_radius=args.temporal_radius,
        temporal_variant_limit=args.temporal_variants,
        temporal_result_limit=args.temporal_results,
        transform_search_limit=args.transform_variants,
        transform_per_slot_limit=args.transform_per_slot,
        transform_result_limit=args.transform_results,
        chain_max_depth=args.chain_max_depth,
        min_engine_validated_solutions=args.min_engine_validated_solutions,
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.write_best:
        best = _best_writable(result)
        if best is not None:
            write_solution(best["solution"], args.write_best, version=7)

    written_complete = 0
    if args.write_complete_dir:
        args.write_complete_dir.mkdir(parents=True, exist_ok=True)
        for item in result.get("candidates", []):
            rank = int(item.get("rank") or 0)
            if item.get("engineValidation", {}).get("complete") and item.get("solution"):
                write_solution(item["solution"], args.write_complete_dir / f"rank-{rank:02d}-base.solution", version=7)
                written_complete += 1
            for search_name in ("temporalSearch", "geometricSearch"):
                for variant in item.get(search_name, {}).get("variants", []):
                    if not variant.get("validation", {}).get("complete") or not variant.get("solution"):
                        continue
                    variant_index = int(variant.get("variantIndex") or 0)
                    label = "timing" if search_name == "temporalSearch" else "geometry"
                    write_solution(
                        variant["solution"],
                        args.write_complete_dir / f"rank-{rank:02d}-{label}-{variant_index:03d}.solution",
                        version=7,
                    )
                    written_complete += 1

    outcome_summary = None
    if args.outcome_index:
        existing = json.loads(args.outcome_index.read_text(encoding="utf-8")) if args.outcome_index.exists() else None
        outcome_index = build_outcome_index(puzzle, result, existing_index=existing)
        args.outcome_index.parent.mkdir(parents=True, exist_ok=True)
        args.outcome_index.write_text(json.dumps(outcome_index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        outcome_summary = outcome_index.get("summary", {})

    summary = dict(result.get("summary", {}))
    if args.write_complete_dir:
        summary["writtenCompleteSolutionCount"] = written_complete
    if outcome_summary is not None:
        summary["outcomeLearning"] = outcome_summary
    print(json.dumps(summary, sort_keys=True))
    return 0 if result.get("summary", {}).get("supported") else 2


if __name__ == "__main__":
    raise SystemExit(main())
