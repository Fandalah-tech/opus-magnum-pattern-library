from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.purification_chain import purification_profile
from tools.run_holdout_oracle_base_repair import run_omsim, variants_for_collision


def _counts(profile: dict[str, Any]) -> dict[str, int]:
    return {str(k): int(v) for k, v in (profile.get("countsByElement") or {}).items()}


def _rebuildable_tier(profile: dict[str, Any]) -> tuple[int, int, int, int]:
    counts = _counts(profile)
    gold = int(counts.get("gold", 0))
    silver = int(counts.get("silver", 0))
    copper = int(counts.get("copper", 0))
    # Gold is the strongest frontier. Two free-produced silvers are deliberately
    # retained as a rebuildable precursor state because the blind convergence
    # stage can synthesize gold again after a mechanical topology change.
    tier = 3 if gold > 0 else 2 if silver >= 2 else 1 if silver > 0 else 0
    return tier, gold, silver, copper


def _acceptable_child(parent_profile: dict[str, Any], child_profile: dict[str, Any]) -> bool:
    parent_counts = _counts(parent_profile)
    child_counts = _counts(child_profile)
    parent_gold = int(parent_counts.get("gold", 0))
    parent_silver = int(parent_counts.get("silver", 0))
    if parent_gold > 0:
        return int(child_counts.get("gold", 0)) >= parent_gold or int(child_counts.get("silver", 0)) >= 2
    if parent_silver >= 2:
        return int(child_counts.get("silver", 0)) >= 2
    parent_frontier = int(parent_profile.get("frontierIndex") if parent_profile.get("frontierIndex") is not None else -1)
    child_frontier = int(child_profile.get("frontierIndex") if child_profile.get("frontierIndex") is not None else -1)
    return child_frontier >= parent_frontier


def _signature(solution: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            str(part.get("id") or ""), str(part.get("type") or ""),
            tuple(int(x) for x in (part.get("position") or (0, 0))),
            int(part.get("rotation") or 0) % 6, int(part.get("length") or 1),
        )
        for part in solution.get("parts", []) or []
    )


def _rank(state: dict[str, Any]) -> tuple[Any, ...]:
    oracle = state.get("omsim") or {}
    profile = state.get("purificationProfile") or {}
    tier = _rebuildable_tier(profile)
    return (
        int(oracle.get("exitCode") == 0),
        int(oracle.get("progressCycle") or 0),
        *tier,
        int(profile.get("count") or 0),
    )


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    depth: int = 3,
    beam_width: int = 3,
    max_arm_length: int = 3,
    max_cycles: int = 500,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    baseline_solution = parse_solution(baseline_path)
    baseline_file = output_dir / "depth-00-seed.solution"
    write_solution(baseline_solution, baseline_file)
    initial = {
        "solution": baseline_solution,
        "solutionPath": str(baseline_file),
        "omsim": run_omsim(omsim, puzzle_path, baseline_file),
        "purificationProfile": purification_profile(puzzle, baseline_solution, max_cycles=max_cycles),
        "steps": [],
    }
    beam = [initial]
    visited = {_signature(baseline_solution)}
    generations: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = initial if int(initial["omsim"].get("exitCode") or 0) == 0 else None

    for depth_index in range(1, max(1, int(depth)) + 1):
        expanded: list[dict[str, Any]] = []
        generation_records: list[dict[str, Any]] = []
        for parent_index, parent in enumerate(beam):
            parent_oracle = parent.get("omsim") or {}
            location = parent_oracle.get("collisionLocation")
            if not location:
                continue
            variants = variants_for_collision(
                parent["solution"], tuple(int(x) for x in location), max_arm_length=max_arm_length,
            )
            for variant_index, variant in enumerate(variants):
                sig = _signature(variant["solution"])
                if sig in visited:
                    continue
                path = output_dir / f"depth-{depth_index:02d}-parent-{parent_index:02d}-candidate-{variant_index:02d}.solution"
                write_solution(variant["solution"], path)
                oracle = run_omsim(omsim, puzzle_path, path)
                profile = purification_profile(puzzle, variant["solution"], max_cycles=max_cycles)
                oracle_advance = int(oracle.get("progressCycle") or 0) > int(parent_oracle.get("progressCycle") or 0)
                chemistry_rebuildable = _acceptable_child(parent.get("purificationProfile") or {}, profile)
                record = {
                    "depth": depth_index,
                    "parentIndex": parent_index,
                    "variantIndex": variant_index,
                    "mode": variant.get("mode"),
                    "armPartId": variant.get("armPartId"),
                    "newBase": variant.get("newBase"),
                    "newRotation": variant.get("newRotation"),
                    "newLength": variant.get("newLength"),
                    "solutionPath": str(path),
                    "omsim": oracle,
                    "purificationProfile": profile,
                    "oracleAdvance": oracle_advance,
                    "chemistryRebuildable": chemistry_rebuildable,
                }
                generation_records.append(record)
                if int(oracle.get("exitCode") or 0) == 0:
                    accepted = {**record, "solution": variant["solution"], "steps": [*parent.get("steps", []), record]}
                    break
                if oracle_advance and chemistry_rebuildable:
                    expanded.append({
                        **record,
                        "solution": variant["solution"],
                        "steps": [*parent.get("steps", []), record],
                    })
            if accepted is not None:
                break
        generation_records.sort(key=_rank, reverse=True)
        deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for state in expanded:
            sig = _signature(state["solution"])
            prior = deduped.get(sig)
            if prior is None or _rank(state) > _rank(prior):
                deduped[sig] = state
        next_beam = sorted(deduped.values(), key=_rank, reverse=True)[:max(1, int(beam_width))]
        for state in next_beam:
            visited.add(_signature(state["solution"]))
        generations.append({
            "depth": depth_index,
            "parentCount": len(beam),
            "evaluatedVariantCount": len(generation_records),
            "advancingRebuildableCount": len(expanded),
            "beamCount": len(next_beam),
            "bestProgressCycle": int((next_beam[0].get("omsim") or {}).get("progressCycle") or 0) if next_beam else None,
            "bestChemistryTier": list(_rebuildable_tier(next_beam[0].get("purificationProfile") or {})) if next_beam else None,
            "variants": generation_records,
        })
        if accepted is not None or not next_beam:
            break
        beam = next_beam

    final_candidates = [accepted] if accepted is not None else beam
    final_candidates = [item for item in final_candidates if item is not None]
    final_candidates.sort(key=_rank, reverse=True)
    best = final_candidates[0] if final_candidates else initial
    final_path = output_dir / "GEN249-best-oracle-beam.solution"
    write_solution(best["solution"], final_path)
    final_oracle = run_omsim(omsim, puzzle_path, final_path)
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-oracle-mechanical-beam-search",
        "targetSolutionBytesUsed": 0,
        "request": {
            "depth": int(depth), "beamWidth": int(beam_width), "maxArmLength": int(max_arm_length), "maxCycles": int(max_cycles),
        },
        "initial": {
            "solutionPath": str(baseline_file), "omsim": initial["omsim"], "purificationProfile": initial["purificationProfile"],
        },
        "generations": generations,
        "visitedStateCount": len(visited),
        "best": {
            "solutionPath": str(final_path), "omsim": final_oracle,
            "purificationProfile": best.get("purificationProfile"), "steps": best.get("steps", []),
        },
        "acceptedProductOne": int(final_oracle.get("exitCode") or 0) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Beam-search OMSim collision-base repairs while retaining rebuildable chemistry precursors.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--beam-width", type=int, default=3)
    parser.add_argument("--max-arm-length", type=int, default=3)
    parser.add_argument("--max-cycles", type=int, default=500)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim, puzzle_path=args.puzzle, baseline_path=args.baseline,
        output_dir=args.output_dir, depth=args.depth, beam_width=args.beam_width,
        max_arm_length=args.max_arm_length, max_cycles=args.max_cycles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "acceptedProductOne": report["acceptedProductOne"],
        "bestOMSim": report["best"]["omsim"],
        "bestPurificationProfile": report["best"]["purificationProfile"],
        "visitedStateCount": report["visitedStateCount"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
