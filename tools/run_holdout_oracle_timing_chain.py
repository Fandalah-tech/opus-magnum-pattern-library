from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.purification_chain import purification_profile
from tools.run_holdout_oracle_base_repair import run_omsim
from tools.run_holdout_oracle_timing_repair import timing_variants


def _reachable_counts(profile: dict[str, Any], progress_cycle: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for element, cycles in (profile.get("cyclesByElement") or {}).items():
        counts[str(element)] = sum(int(cycle) < int(progress_cycle) for cycle in cycles or [])
    return {key: value for key, value in counts.items() if value > 0}


def _tier(counts: dict[str, int]) -> tuple[int, int, int, int, int]:
    gold = int(counts.get("gold", 0))
    silver = int(counts.get("silver", 0))
    copper = int(counts.get("copper", 0))
    if gold > 0:
        level = 4
    elif silver >= 2:
        level = 3
    elif silver >= 1:
        level = 2
    elif copper >= 1:
        level = 1
    else:
        level = 0
    return level, gold, silver, copper, sum(counts.values())


def _signature(solution: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            str(part.get("id") or ""),
            tuple(
                (int(item.get("cycle") or 0), str(item.get("instruction") or ""))
                for item in (part.get("program") or [])
            ),
        )
        for part in solution.get("parts", []) or []
        if (str(part.get("type") or "").startswith("arm") or str(part.get("type") or "") in {"piston", "baron"})
    )


def _rank(state: dict[str, Any]) -> tuple[Any, ...]:
    oracle = state.get("omsim") or {}
    return (
        int(oracle.get("exitCode") == 0),
        int(oracle.get("progressCycle") or 0),
        *_tier(state.get("reachableCounts") or {}),
        int((state.get("purificationProfile") or {}).get("count") or 0),
    )


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    depth: int = 4,
    beam_width: int = 3,
    window: int = 10,
    max_delay: int = 12,
    max_cycles: int = 600,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    seed = parse_solution(baseline_path)
    seed_path = output_dir / "depth-00-seed.solution"
    write_solution(seed, seed_path)
    seed_oracle = run_omsim(omsim, puzzle_path, seed_path)
    seed_profile = purification_profile(puzzle, seed, max_cycles=max_cycles)
    seed_reachable = _reachable_counts(seed_profile, int(seed_oracle.get("progressCycle") or 0))
    beam = [{
        "solution": seed,
        "solutionPath": str(seed_path),
        "omsim": seed_oracle,
        "purificationProfile": seed_profile,
        "reachableCounts": seed_reachable,
        "steps": [],
    }]
    visited = {_signature(seed)}
    generations: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = beam[0] if int(seed_oracle.get("exitCode") or 0) == 0 else None

    for depth_index in range(1, max(1, int(depth)) + 1):
        expanded: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        for parent_index, parent in enumerate(beam):
            parent_oracle = parent.get("omsim") or {}
            collision_cycle = parent_oracle.get("collisionCycle")
            if collision_cycle is None:
                continue
            parent_progress = int(parent_oracle.get("progressCycle") or 0)
            parent_tier = _tier(parent.get("reachableCounts") or {})
            variants = timing_variants(
                parent["solution"], collision_cycle=int(collision_cycle), window=window, max_delay=max_delay,
            )
            for variant_index, variant in enumerate(variants):
                sig = _signature(variant["solution"])
                if sig in visited:
                    continue
                path = output_dir / f"depth-{depth_index:02d}-parent-{parent_index:02d}-candidate-{variant_index:03d}.solution"
                write_solution(variant["solution"], path)
                oracle = run_omsim(omsim, puzzle_path, path)
                progress = int(oracle.get("progressCycle") or 0)
                if progress <= parent_progress and int(oracle.get("exitCode") or 0) != 0:
                    continue
                profile = purification_profile(puzzle, variant["solution"], max_cycles=max_cycles)
                reachable = _reachable_counts(profile, progress)
                reachable_tier = _tier(reachable)
                preserves_reachable_frontier = reachable_tier[0] >= parent_tier[0]
                record = {
                    "depth": depth_index,
                    "parentIndex": parent_index,
                    "variantIndex": variant_index,
                    **{key: value for key, value in variant.items() if key != "solution"},
                    "solutionPath": str(path),
                    "omsim": oracle,
                    "purificationProfile": profile,
                    "reachableCounts": reachable,
                    "reachableTier": list(reachable_tier),
                    "preservesReachableFrontier": preserves_reachable_frontier,
                    "oracleAdvance": progress > parent_progress,
                }
                records.append(record)
                if int(oracle.get("exitCode") or 0) == 0:
                    accepted = {**record, "solution": variant["solution"], "steps": [*parent.get("steps", []), record]}
                    break
                if preserves_reachable_frontier:
                    expanded.append({
                        **record,
                        "solution": variant["solution"],
                        "steps": [*parent.get("steps", []), record],
                    })
            if accepted is not None:
                break

        deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for state in expanded:
            sig = _signature(state["solution"])
            prior = deduped.get(sig)
            if prior is None or _rank(state) > _rank(prior):
                deduped[sig] = state
        next_beam = sorted(deduped.values(), key=_rank, reverse=True)[:max(1, int(beam_width))]
        for state in next_beam:
            visited.add(_signature(state["solution"]))
        records.sort(key=_rank, reverse=True)
        generations.append({
            "depth": depth_index,
            "parentCount": len(beam),
            "evaluatedAdvancingVariantCount": len(records),
            "frontierPreservingCount": sum(bool(item.get("preservesReachableFrontier")) for item in records),
            "beamCount": len(next_beam),
            "bestProgressCycle": int((next_beam[0].get("omsim") or {}).get("progressCycle") or 0) if next_beam else None,
            "bestReachableCounts": (next_beam[0].get("reachableCounts") or {}) if next_beam else {},
            "variants": records[:40],
        })
        if accepted is not None or not next_beam:
            break
        beam = next_beam

    finalists = [accepted] if accepted is not None else beam
    finalists = [state for state in finalists if state is not None]
    finalists.sort(key=_rank, reverse=True)
    best = finalists[0] if finalists else {
        "solution": seed,
        "omsim": seed_oracle,
        "purificationProfile": seed_profile,
        "reachableCounts": seed_reachable,
        "steps": [],
    }
    best_path = output_dir / "GEN249-best-oracle-timing-chain.solution"
    write_solution(best["solution"], best_path)
    best_oracle = run_omsim(omsim, puzzle_path, best_path)
    best_profile = purification_profile(puzzle, best["solution"], max_cycles=max_cycles)
    best_reachable = _reachable_counts(best_profile, int(best_oracle.get("progressCycle") or 0))
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-oracle-timing-chain-search",
        "targetSolutionBytesUsed": 0,
        "request": {
            "depth": int(depth), "beamWidth": int(beam_width), "window": int(window),
            "maxDelay": int(max_delay), "maxCycles": int(max_cycles),
        },
        "initial": {
            "omsim": seed_oracle, "purificationProfile": seed_profile, "reachableCounts": seed_reachable,
        },
        "generations": generations,
        "visitedStateCount": len(visited),
        "best": {
            "solutionPath": str(best_path), "omsim": best_oracle,
            "purificationProfile": best_profile, "reachableCounts": best_reachable,
            "reachableTier": list(_tier(best_reachable)), "steps": best.get("steps", []),
        },
        "reachableSilverPair": int(best_reachable.get("silver", 0)) >= 2,
        "acceptedProductOne": int(best_oracle.get("exitCode") or 0) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Iterate blind timing repairs while requiring chemistry reachable before each official collision.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--beam-width", type=int, default=3)
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument("--max-delay", type=int, default=12)
    parser.add_argument("--max-cycles", type=int, default=600)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim, puzzle_path=args.puzzle, baseline_path=args.baseline,
        output_dir=args.output_dir, depth=args.depth, beam_width=args.beam_width,
        window=args.window, max_delay=args.max_delay, max_cycles=args.max_cycles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "bestOMSim": report["best"]["omsim"],
        "bestReachableCounts": report["best"]["reachableCounts"],
        "reachableSilverPair": report["reachableSilverPair"],
        "acceptedProductOne": report["acceptedProductOne"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
