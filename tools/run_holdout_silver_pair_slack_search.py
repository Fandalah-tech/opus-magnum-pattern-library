from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.adjacent_intermediate_purification import search_adjacent_intermediate_purification
from packages.opus_solver.product_delivery import search_singleton_product_delivery
from packages.opus_solver.purification_chain import purification_profile
from tools.run_holdout_oracle_base_repair import run_omsim
from tools.run_holdout_oracle_timing_repair import timing_variants


def _second_silver_cycle(profile: dict[str, Any]) -> int | None:
    cycles = sorted(int(value) for value in ((profile.get("cyclesByElement") or {}).get("silver") or []))
    return cycles[1] if len(cycles) >= 2 else None


def _gold_cycle(profile: dict[str, Any]) -> int | None:
    cycles = sorted(int(value) for value in ((profile.get("cyclesByElement") or {}).get("gold") or []))
    return cycles[0] if cycles else None


def _official_horizon(oracle: dict[str, Any], fallback: int) -> int:
    collision = oracle.get("collisionCycle")
    return int(collision) if collision is not None else int(fallback)


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    max_cycles: int = 1600,
    window: int = 10,
    max_delay: int = 12,
    finish_limit: int = 12,
) -> dict[str, Any]:
    """Maximize chemistry lead rather than merely delaying the next collision.

    A first product needs the second silver early enough that same-cycle gold can
    exist for at least one complete later cycle before OMSim's motion collision.
    Mechanical progress alone can stretch both chemistry and collision together,
    preserving a useless one-cycle gap.  This search ranks timing mutations by
    `collisionCycle - secondSilverCycle`, then finishes the best slack states
    with an adjacent purifier and output placement.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    baseline = parse_solution(baseline_path)
    baseline_copy = output_dir / "baseline.solution"
    write_solution(baseline, baseline_copy)
    baseline_oracle = run_omsim(omsim, puzzle_path, baseline_copy)
    collision_cycle = baseline_oracle.get("collisionCycle")
    if collision_cycle is None:
        collision_cycle = max_cycles

    variants = timing_variants(
        baseline,
        collision_cycle=int(collision_cycle),
        window=window,
        max_delay=max_delay,
    )
    timing_records: list[dict[str, Any]] = []
    for index, variant in enumerate(variants):
        path = output_dir / "timing" / f"candidate-{index:03d}.solution"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_solution(variant["solution"], path)
        oracle = run_omsim(omsim, puzzle_path, path)
        horizon = min(max_cycles, max(1, _official_horizon(oracle, max_cycles) + 2))
        profile = purification_profile(puzzle, variant["solution"], max_cycles=horizon)
        second_silver = _second_silver_cycle(profile)
        official_limit = _official_horizon(oracle, max_cycles)
        official_pair = bool(second_silver is not None and int(second_silver) < int(official_limit))
        slack = int(official_limit) - int(second_silver) if official_pair and second_silver is not None else -1
        timing_records.append({
            **{key: value for key, value in variant.items() if key != "solution"},
            "solutionPath": str(path),
            "omsim": oracle,
            "purificationProfile": profile,
            "secondSilverCycle": second_silver,
            "officialSilverPair": official_pair,
            "silverPairSlackCycles": slack,
        })

    timing_records.sort(
        key=lambda item: (
            int(bool(item.get("officialSilverPair"))),
            int(item.get("silverPairSlackCycles") or -1),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
        ),
        reverse=True,
    )

    finish_records: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None
    eligible = [
        item for item in timing_records
        if bool(item.get("officialSilverPair")) and int(item.get("silverPairSlackCycles") or -1) >= 2
    ][:max(1, int(finish_limit))]

    for parent_index, parent in enumerate(eligible):
        parent_solution = parse_solution(parent["solutionPath"])
        oracle_limit = _official_horizon(parent.get("omsim") or {}, max_cycles)
        adjacent = search_adjacent_intermediate_purification(
            puzzle,
            parent_solution,
            element="silver",
            max_cycles=min(max_cycles, oracle_limit + 2),
            observation_limit=240,
            result_limit=12,
        )
        for adjacent_index, adjacent_variant in enumerate(adjacent.get("variants", []) or []):
            gold_cycle = _gold_cycle(adjacent_variant.get("purificationProfile") or {})
            if gold_cycle is None or int(oracle_limit) - int(gold_cycle) < 2:
                continue
            adjacent_path = output_dir / "adjacent" / f"parent-{parent_index:02d}-candidate-{adjacent_index:02d}.solution"
            adjacent_path.parent.mkdir(parents=True, exist_ok=True)
            write_solution(adjacent_variant["solution"], adjacent_path)
            adjacent_oracle = run_omsim(omsim, puzzle_path, adjacent_path)

            delivery = search_singleton_product_delivery(
                puzzle,
                adjacent_variant["solution"],
                max_cycles=min(max_cycles, oracle_limit + 2),
                opportunity_limit=160,
                result_limit=24,
            )
            for delivery_index, delivery_variant in enumerate(delivery.get("variants", []) or []):
                delivery_path = output_dir / "delivery" / f"parent-{parent_index:02d}-adjacent-{adjacent_index:02d}-candidate-{delivery_index:02d}.solution"
                delivery_path.parent.mkdir(parents=True, exist_ok=True)
                write_solution(delivery_variant["solution"], delivery_path)
                delivery_oracle = run_omsim(omsim, puzzle_path, delivery_path)
                record = {
                    "parentTimingIndex": parent_index,
                    "timingCandidate": {key: value for key, value in parent.items() if key != "purificationProfile"},
                    "adjacentIndex": adjacent_index,
                    "adjacentSolutionPath": str(adjacent_path),
                    "goldCycle": gold_cycle,
                    "adjacentOMSim": adjacent_oracle,
                    "deliveryIndex": delivery_index,
                    "deliverySolutionPath": str(delivery_path),
                    "localDeliverySummary": delivery_variant.get("summary"),
                    "omsim": delivery_oracle,
                }
                finish_records.append(record)
                if int(delivery_oracle.get("exitCode") or 0) == 0:
                    accepted = record
                    break
            if accepted is not None:
                break
        if accepted is not None:
            break

    finish_records.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int((item.get("localDeliverySummary") or {}).get("productDeliveredCount") or 0),
        ),
        reverse=True,
    )
    accepted_output = None
    if accepted is not None:
        accepted_output = output_dir / "GEN249-omsim-product1.solution"
        accepted_output.write_bytes(Path(accepted["deliverySolutionPath"]).read_bytes())

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-silver-pair-slack-search",
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": int(max_cycles), "window": int(window), "maxDelay": int(max_delay), "finishLimit": int(finish_limit),
        },
        "baselineOMSim": baseline_oracle,
        "timingVariantCount": len(timing_records),
        "officialSilverPairCount": sum(bool(item.get("officialSilverPair")) for item in timing_records),
        "silverPairSlackAtLeastTwoCount": sum(bool(item.get("officialSilverPair")) and int(item.get("silverPairSlackCycles") or -1) >= 2 for item in timing_records),
        "topTimingCandidates": timing_records[:40],
        "finishCandidateCount": len(finish_records),
        "finishCandidates": finish_records[:60],
        "acceptedProductOne": accepted is not None,
        "acceptedSolution": str(accepted_output) if accepted_output is not None else None,
        "acceptedOMSim": accepted.get("omsim") if accepted is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Find a blind timing variant with enough silver-pair slack to finish product one before collision.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=1600)
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument("--max-delay", type=int, default=12)
    parser.add_argument("--finish-limit", type=int, default=12)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim, puzzle_path=args.puzzle, baseline_path=args.baseline,
        output_dir=args.output_dir, max_cycles=args.max_cycles, window=args.window,
        max_delay=args.max_delay, finish_limit=args.finish_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "timingVariantCount": report["timingVariantCount"],
        "officialSilverPairCount": report["officialSilverPairCount"],
        "silverPairSlackAtLeastTwoCount": report["silverPairSlackAtLeastTwoCount"],
        "finishCandidateCount": report["finishCandidateCount"],
        "acceptedProductOne": report["acceptedProductOne"],
        "acceptedOMSim": report["acceptedOMSim"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
