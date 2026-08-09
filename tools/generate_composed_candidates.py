from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver import generate_composed_candidates


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
    parser.add_argument("--report", type=Path, default=Path("reports/composed-candidates.json"))
    parser.add_argument("--write-best", type=Path)
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
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.write_best:
        best = _best_writable(result)
        if best is not None:
            write_solution(best["solution"], args.write_best, version=7)

    print(json.dumps(result.get("summary", {}), sort_keys=True))
    return 0 if result.get("summary", {}).get("supported") else 2


if __name__ == "__main__":
    raise SystemExit(main())
