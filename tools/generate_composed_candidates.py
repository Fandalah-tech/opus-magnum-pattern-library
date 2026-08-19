from __future__ import annotations

import argparse
from itertools import count
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver import build_outcome_index, generate_composed_candidates
from tools.omsim_adapter.validate import run_omsim, run_omsim_product


def _best_writable(result: dict) -> dict | None:
    complete = []
    fallback = []
    for item in result.get("candidates", []):
        if item.get("serialization", {}).get("roundTripClean") and item.get("solution"):
            fallback.append(item)
            if item.get("engineValidation", {}).get("complete"):
                complete.append(item)
        for search_name in ("temporalSearch", "geometricSearch", "componentTimingSearch"):
            for variant in item.get(search_name, {}).get("variants", []):
                if variant.get("serialization", {}).get("roundTripClean") and variant.get("solution"):
                    fallback.append(variant)
                    if (
                        variant.get("validation", {}).get("complete")
                        or variant.get("oracleValidation", {}).get("valid")
                    ):
                        complete.append(variant)
    for variant in (result.get("componentTimingOraclePortfolio") or {}).get("variants", []):
        if variant.get("serialization", {}).get("roundTripClean") and variant.get("solution"):
            fallback.append(variant)
            if (
                variant.get("validation", {}).get("complete")
                or variant.get("oracleValidation", {}).get("valid")
            ):
                complete.append(variant)
    for variant in (result.get("chemistryTransplantSearch") or {}).get("variants", []):
        if variant.get("serialization", {}).get("roundTripClean") and variant.get("solution"):
            fallback.append(variant)
            if (
                variant.get("validation", {}).get("complete")
                or variant.get("oracleValidation", {}).get("valid")
            ):
                complete.append(variant)
    for variant in (result.get("orderedChemistrySearch") or {}).get("variants", []):
        if variant.get("serialization", {}).get("roundTripClean") and variant.get("solution"):
            fallback.append(variant)
            if variant.get("oracleValidation", {}).get("valid"):
                complete.append(variant)
    for variant in (result.get("productCompletionSearch") or {}).get("variants", []):
        if variant.get("serialization", {}).get("roundTripClean") and variant.get("solution"):
            fallback.append(variant)
            if variant.get("productOracleValidation", {}).get("valid"):
                complete.append(variant)
    for variant in (result.get("repeatingProductSearch") or {}).get("variants", []):
        if variant.get("serialization", {}).get("roundTripClean") and variant.get("solution"):
            fallback.append(variant)
            if variant.get("fullProductOracleValidation", {}).get("valid"):
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
    parser.add_argument("--transform-synthetic-radius", type=int, default=0, help="Add unobserved local hex translations within this radius to geometric repair.")
    parser.add_argument("--transform-synthetic-rotations", type=int, default=0, help="Add +/- this many local rotation steps to geometric repair.")
    parser.add_argument("--transform-preflight-cycles", type=int, default=0, help="Replay each geometric variant only this long before promoting the best variants to full validation.")
    parser.add_argument("--transform-promotions", type=int, default=25, help="Maximum preflight survivors promoted to full validation per assembly.")
    parser.add_argument("--component-timing-variants", type=int, default=0, help="Maximum physical-arm tempo edits tested for each retained source geometry.")
    parser.add_argument("--component-timing-sources", type=int, default=6, help="Maximum progress/survival source geometries repaired per assembly.")
    parser.add_argument("--component-timing-radius", type=int, default=2, help="Maximum cycles inserted or removed at one arm-program boundary.")
    parser.add_argument("--component-timing-cutpoints", type=int, default=16, help="Maximum chemistry/error-sensitive instruction boundaries tested per arm.")
    parser.add_argument("--component-timing-results", type=int, default=20, help="Best component-timing variants retained in the JSON report.")
    parser.add_argument("--component-timing-global-results", type=int, default=0, help="Reallocate this many oracle-ranked tempo variants globally across all assembly families.")
    parser.add_argument("--component-timing-preflight-cycles", type=int, default=0, help="Replay tempo edits only this long before full-validation promotion.")
    parser.add_argument("--component-timing-promotions", type=int, default=40, help="Maximum component-timing preflight variants promoted to full validation.")
    parser.add_argument("--chemistry-transplant-variants", type=int, default=0, help="Maximum input/glyph placements tested on globally oracle-stable mechanical parents.")
    parser.add_argument("--chemistry-transplant-sources", type=int, default=4, help="Maximum distinct oracle-stable mechanism families used as transplant parents.")
    parser.add_argument("--chemistry-transplant-results", type=int, default=20, help="Best chemistry transplants retained in the JSON report.")
    parser.add_argument("--chemistry-transplant-grab-cycles", type=int, default=256, help="Mechanism replay horizon used to discover distinct arm grab cells.")
    parser.add_argument("--chemistry-transplant-local-cycles", type=int, default=160, help="Bounded local validation horizon for each chemistry transplant.")
    parser.add_argument("--chemistry-transplant-promotions", type=int, default=120, help="Maximum locally ranked chemistry transplants promoted to OMSim.")
    parser.add_argument("--ordered-chemistry-variants", type=int, default=0, help="Maximum trajectory-derived second-prism placements tested after stable chemistry transplant.")
    parser.add_argument("--ordered-chemistry-sources", type=int, default=8, help="Maximum OMSim-stable chemistry transplants advanced into ordered chemistry.")
    parser.add_argument("--ordered-chemistry-calcification-variants", type=int, default=256, help="Maximum post-triplex calcification placements tested.")
    parser.add_argument("--ordered-chemistry-results", type=int, default=20, help="Best persistent ordered-chemistry variants retained in the report.")
    parser.add_argument("--ordered-chemistry-local-cycles", type=int, default=160, help="Local trajectory horizon for persistent chemistry states.")
    parser.add_argument("--ordered-chemistry-persistence-frames", type=int, default=2, help="Consecutive snapshots required before a chemistry state counts as persistent.")
    parser.add_argument("--ordered-chemistry-prism-promotions", type=int, default=32, help="Maximum persistent complete-triplex candidates promoted to OMSim.")
    parser.add_argument("--ordered-chemistry-calcification-promotions", type=int, default=40, help="Maximum persistent calcified-triplex candidates promoted to OMSim.")
    parser.add_argument("--single-product-sources", type=int, default=0, help="Maximum ordered-chemistry cores extended with the bounded product finisher.")
    parser.add_argument("--single-product-results", type=int, default=20, help="Best single-product completion variants retained in the report.")
    parser.add_argument("--single-product-local-cycles", type=int, default=100, help="Local replay horizon for each product-finisher candidate.")
    parser.add_argument("--single-product-promotions", type=int, default=20, help="Maximum local product completions promoted to OMSim's product metric.")
    parser.add_argument("--repeating-product-sources", type=int, default=0, help="Maximum one-product candidates upgraded into six-output periodic machines.")
    parser.add_argument("--repeating-product-results", type=int, default=20, help="Best repeating completion variants retained in the report.")
    parser.add_argument("--repeating-product-local-cycles", type=int, default=400, help="Local replay horizon for six product deliveries.")
    parser.add_argument("--repeating-product-promotions", type=int, default=20, help="Maximum local six-product completions promoted to OMSim.")
    parser.add_argument("--omsim", type=Path, help="Authoritatively validate generated candidates with this OMSim binary.")
    parser.add_argument("--omsim-workers", type=int, default=10, help="Concurrent OMSim validations, capped at 10.")
    parser.add_argument("--omsim-timeout", type=int, default=30, help="Timeout in seconds for each OMSim validation.")
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
    with TemporaryDirectory(prefix="opus-component-timing-") as oracle_temp_name:
        oracle_counter = count()

        def oracle_validator(solution: dict) -> dict:
            path = Path(oracle_temp_name) / f"candidate-{next(oracle_counter):06d}.solution"
            write_solution(solution, path, version=7)
            return run_omsim(
                args.omsim,
                args.puzzle,
                path,
                max(1, int(args.omsim_timeout)),
            )

        def product_oracle_validator(solution: dict) -> dict:
            path = Path(oracle_temp_name) / f"product-{next(oracle_counter):06d}.solution"
            write_solution(solution, path, version=7)
            return run_omsim_product(
                args.omsim,
                args.puzzle,
                path,
                max(1, int(args.omsim_timeout)),
                product_count=1,
                metric="cycles",
            )

        def full_product_oracle_validator(solution: dict) -> dict:
            path = Path(oracle_temp_name) / f"full-product-{next(oracle_counter):06d}.solution"
            write_solution(solution, path, version=7)
            return run_omsim_product(
                args.omsim,
                args.puzzle,
                path,
                max(1, int(args.omsim_timeout)),
                product_count=6,
                metric="cycles",
            )

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
            transform_synthetic_translation_radius=args.transform_synthetic_radius,
            transform_synthetic_rotation_radius=args.transform_synthetic_rotations,
            transform_preflight_cycles=args.transform_preflight_cycles,
            transform_promotion_limit=args.transform_promotions,
            component_timing_search_limit=args.component_timing_variants,
            component_timing_source_limit=args.component_timing_sources,
            component_timing_radius=args.component_timing_radius,
            component_timing_cutpoint_limit=args.component_timing_cutpoints,
            component_timing_result_limit=args.component_timing_results,
            component_timing_preflight_cycles=args.component_timing_preflight_cycles,
            component_timing_promotion_limit=args.component_timing_promotions,
            component_timing_oracle_validator=oracle_validator if args.omsim else None,
            component_timing_oracle_workers=max(1, min(10, int(args.omsim_workers))),
            component_timing_global_result_limit=args.component_timing_global_results,
            chemistry_transplant_variant_limit=args.chemistry_transplant_variants,
            chemistry_transplant_source_limit=args.chemistry_transplant_sources,
            chemistry_transplant_result_limit=args.chemistry_transplant_results,
            chemistry_transplant_max_grab_cycles=args.chemistry_transplant_grab_cycles,
            chemistry_transplant_local_cycles=args.chemistry_transplant_local_cycles,
            chemistry_transplant_oracle_promotion_limit=args.chemistry_transplant_promotions,
            ordered_chemistry_variant_limit=args.ordered_chemistry_variants,
            ordered_chemistry_source_limit=args.ordered_chemistry_sources,
            ordered_chemistry_calcification_variant_limit=(
                args.ordered_chemistry_calcification_variants
            ),
            ordered_chemistry_result_limit=args.ordered_chemistry_results,
            ordered_chemistry_local_cycles=args.ordered_chemistry_local_cycles,
            ordered_chemistry_persistence_frames=(
                args.ordered_chemistry_persistence_frames
            ),
            ordered_chemistry_prism_oracle_promotion_limit=(
                args.ordered_chemistry_prism_promotions
            ),
            ordered_chemistry_calcification_oracle_promotion_limit=(
                args.ordered_chemistry_calcification_promotions
            ),
            single_product_source_limit=args.single_product_sources,
            single_product_result_limit=args.single_product_results,
            single_product_local_cycles=args.single_product_local_cycles,
            single_product_oracle_promotion_limit=args.single_product_promotions,
            single_product_oracle_validator=(
                product_oracle_validator if args.omsim else None
            ),
            repeating_product_source_limit=args.repeating_product_sources,
            repeating_product_result_limit=args.repeating_product_results,
            repeating_product_local_cycles=args.repeating_product_local_cycles,
            repeating_product_oracle_promotion_limit=(
                args.repeating_product_promotions
            ),
            full_product_oracle_validator=(
                full_product_oracle_validator if args.omsim else None
            ),
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
            for search_name in ("temporalSearch", "geometricSearch", "componentTimingSearch"):
                for variant in item.get(search_name, {}).get("variants", []):
                    if not variant.get("solution") or not (
                        variant.get("validation", {}).get("complete")
                        or variant.get("oracleValidation", {}).get("valid")
                    ):
                        continue
                    variant_index = int(variant.get("variantIndex") or 0)
                    label = {
                        "temporalSearch": "timing",
                        "geometricSearch": "geometry",
                        "componentTimingSearch": "component-timing",
                    }[search_name]
                    write_solution(
                        variant["solution"],
                        args.write_complete_dir / f"rank-{rank:02d}-{label}-{variant_index:03d}.solution",
                        version=7,
                    )
                    written_complete += 1
        for variant_index, variant in enumerate(
            (result.get("orderedChemistrySearch") or {}).get("variants", [])
        ):
            if not variant.get("solution") or not variant.get("oracleValidation", {}).get("valid"):
                continue
            write_solution(
                variant["solution"],
                args.write_complete_dir / f"ordered-chemistry-{variant_index:03d}.solution",
                version=7,
            )
            written_complete += 1
        for variant_index, variant in enumerate(
            (result.get("productCompletionSearch") or {}).get("variants", [])
        ):
            if not variant.get("solution") or not variant.get(
                "productOracleValidation", {}
            ).get("valid"):
                continue
            write_solution(
                variant["solution"],
                args.write_complete_dir / f"single-product-{variant_index:03d}.solution",
                version=7,
            )
            written_complete += 1
        for variant_index, variant in enumerate(
            (result.get("repeatingProductSearch") or {}).get("variants", [])
        ):
            if not variant.get("solution") or not variant.get(
                "fullProductOracleValidation", {}
            ).get("valid"):
                continue
            write_solution(
                variant["solution"],
                args.write_complete_dir / f"full-product-{variant_index:03d}.solution",
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
