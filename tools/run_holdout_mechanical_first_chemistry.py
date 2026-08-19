from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.additive_purification_search import search_additive_purification_stations
from packages.opus_solver.product_delivery import search_singleton_product_delivery
from packages.opus_solver.purification_chain import purification_profile
from tools.run_holdout_oracle_base_repair import run_omsim
from tools.run_holdout_oracle_timing_chain import _reachable_counts


def _tier(counts: dict[str, int]) -> tuple[int, int, int, int, int, int]:
    gold = int(counts.get("gold", 0))
    silver = int(counts.get("silver", 0))
    copper = int(counts.get("copper", 0))
    iron = int(counts.get("iron", 0))
    if gold > 0:
        level = 5
    elif silver >= 2:
        level = 4
    elif silver >= 1:
        level = 3
    elif copper >= 2:
        level = 2
    elif copper >= 1:
        level = 1
    else:
        level = 0
    return level, gold, silver, copper, iron, sum(counts.values())


def _signature(solution: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            str(part.get("id") or ""), str(part.get("type") or ""),
            tuple(int(value) for value in (part.get("position") or (0, 0))),
            int(part.get("rotation") or 0) % 6,
        )
        for part in solution.get("parts", []) or []
    )


def _state_rank(state: dict[str, Any]) -> tuple[Any, ...]:
    oracle = state.get("omsim") or {}
    reachable = state.get("reachableCounts") or {}
    return (
        *_tier(reachable),
        int(oracle.get("exitCode") == 0),
        int(oracle.get("progressCycle") or 0),
        int((state.get("purificationProfile") or {}).get("count") or 0),
    )


def _compact_variant(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "solutionPath": state.get("solutionPath"),
        "omsim": state.get("omsim"),
        "purificationProfile": state.get("purificationProfile"),
        "reachableCounts": state.get("reachableCounts"),
        "reachableTier": list(_tier(state.get("reachableCounts") or {})),
        "repairMode": state.get("repairMode"),
        "frontierAdvance": state.get("frontierAdvance"),
        "frontierReplenishment": state.get("frontierReplenishment"),
        "parentIndex": state.get("parentIndex"),
    }


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    depth: int = 7,
    beam_width: int = 3,
    variants_per_state: int = 8,
    max_cycles: int = 1200,
) -> dict[str, Any]:
    """Rebuild the metal ladder on a mechanically long-lived blind machine.

    This intentionally flips the earlier repair order: first choose a topology
    that survives far under the official oracle, even if its inherited chemistry
    no longer fires, then synthesize new static reaction stations from that
    topology's own replay. A chemical advance only counts when its event occurs
    before the official OMSim collision, so local post-collision chemistry cannot
    masquerade as an authoritative precursor.
    """

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
    best_gold: dict[str, Any] | None = None

    for depth_index in range(1, max(1, int(depth)) + 1):
        expanded: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        for parent_index, parent in enumerate(beam):
            parent_tier = _tier(parent.get("reachableCounts") or {})
            result = search_additive_purification_stations(
                puzzle,
                parent["solution"],
                max_cycles=max_cycles,
                opportunity_limit=200,
                result_limit=max(variants_per_state, beam_width * 2),
            )
            for variant_index, variant in enumerate(result.get("variants", []) or []):
                candidate = variant["solution"]
                signature = _signature(candidate)
                if signature in visited:
                    continue
                path = output_dir / f"depth-{depth_index:02d}-parent-{parent_index:02d}-candidate-{variant_index:02d}.solution"
                write_solution(candidate, path)
                oracle = run_omsim(omsim, puzzle_path, path)
                profile = variant.get("purificationProfile") or purification_profile(
                    puzzle, candidate, max_cycles=max_cycles
                )
                reachable = _reachable_counts(profile, int(oracle.get("progressCycle") or 0))
                reachable_tier = _tier(reachable)
                state = {
                    "solution": candidate,
                    "solutionPath": str(path),
                    "omsim": oracle,
                    "purificationProfile": profile,
                    "reachableCounts": reachable,
                    "repairMode": variant.get("repairMode"),
                    "frontierAdvance": variant.get("frontierAdvance"),
                    "frontierReplenishment": variant.get("frontierReplenishment"),
                    "parentIndex": parent_index,
                    "steps": [
                        *parent.get("steps", []),
                        {
                            "depth": depth_index,
                            "repairMode": variant.get("repairMode"),
                            "reachableCounts": reachable,
                            "omsimProgressCycle": int(oracle.get("progressCycle") or 0),
                        },
                    ],
                }
                records.append(state)
                if reachable_tier > parent_tier:
                    expanded.append(state)
                if int(reachable.get("gold", 0)) > 0:
                    if best_gold is None or _state_rank(state) > _state_rank(best_gold):
                        best_gold = state

        deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for state in expanded:
            signature = _signature(state["solution"])
            previous = deduped.get(signature)
            if previous is None or _state_rank(state) > _state_rank(previous):
                deduped[signature] = state
        next_beam = sorted(deduped.values(), key=_state_rank, reverse=True)[:max(1, int(beam_width))]
        for state in next_beam:
            visited.add(_signature(state["solution"]))
        records.sort(key=_state_rank, reverse=True)
        generations.append({
            "depth": depth_index,
            "parentCount": len(beam),
            "candidateCount": len(records),
            "reachableAdvanceCount": len(expanded),
            "beamCount": len(next_beam),
            "bestReachableCounts": (next_beam[0].get("reachableCounts") or {}) if next_beam else {},
            "bestOMSimProgressCycle": int((next_beam[0].get("omsim") or {}).get("progressCycle") or 0) if next_beam else None,
            "topCandidates": [_compact_variant(state) for state in records[:20]],
        })
        if best_gold is not None or not next_beam:
            break
        beam = next_beam

    delivery_records: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None
    if best_gold is not None:
        delivery = search_singleton_product_delivery(
            puzzle,
            best_gold["solution"],
            max_cycles=max_cycles,
            opportunity_limit=100,
            result_limit=24,
        )
        for index, variant in enumerate(delivery.get("variants", []) or []):
            candidate = variant["solution"]
            path = output_dir / "delivery" / f"candidate-{index:02d}.solution"
            path.parent.mkdir(parents=True, exist_ok=True)
            write_solution(candidate, path)
            oracle = run_omsim(omsim, puzzle_path, path)
            profile = purification_profile(puzzle, candidate, max_cycles=max_cycles)
            reachable = _reachable_counts(profile, int(oracle.get("progressCycle") or 0))
            record = {
                "solutionPath": str(path),
                "omsim": oracle,
                "purificationProfile": profile,
                "reachableCounts": reachable,
                "localDeliverySummary": variant.get("summary"),
            }
            delivery_records.append(record)
            if int(oracle.get("exitCode") or 0) == 0:
                accepted = record
                break
        delivery_records.sort(
            key=lambda item: (
                int((item.get("omsim") or {}).get("exitCode") == 0),
                int((item.get("omsim") or {}).get("progressCycle") or 0),
                *_tier(item.get("reachableCounts") or {}),
            ),
            reverse=True,
        )

    best_state = best_gold or (beam[0] if beam else {
        "solution": seed,
        "solutionPath": str(seed_path),
        "omsim": seed_oracle,
        "purificationProfile": seed_profile,
        "reachableCounts": seed_reachable,
        "steps": [],
    })
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-mechanical-first-chemistry-rebuild",
        "targetSolutionBytesUsed": 0,
        "request": {
            "depth": int(depth), "beamWidth": int(beam_width),
            "variantsPerState": int(variants_per_state), "maxCycles": int(max_cycles),
        },
        "initial": {
            "solutionPath": str(seed_path), "omsim": seed_oracle,
            "purificationProfile": seed_profile, "reachableCounts": seed_reachable,
        },
        "generations": generations,
        "visitedStateCount": len(visited),
        "bestChemistry": _compact_variant(best_state),
        "goldReachedBeforeOracleFailure": best_gold is not None,
        "deliveryCandidateCount": len(delivery_records),
        "topDeliveryCandidates": delivery_records[:20],
        "acceptedProductOne": accepted is not None,
        "acceptedSolution": accepted.get("solutionPath") if accepted else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild blind metal chemistry on a long-lived official mechanical frontier.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=7)
    parser.add_argument("--beam-width", type=int, default=3)
    parser.add_argument("--variants-per-state", type=int, default=8)
    parser.add_argument("--max-cycles", type=int, default=1200)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim, puzzle_path=args.puzzle, baseline_path=args.baseline,
        output_dir=args.output_dir, depth=args.depth, beam_width=args.beam_width,
        variants_per_state=args.variants_per_state, max_cycles=args.max_cycles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "initialOMSim": report["initial"]["omsim"],
        "bestChemistry": report["bestChemistry"],
        "goldReachedBeforeOracleFailure": report["goldReachedBeforeOracleFailure"],
        "deliveryCandidateCount": report["deliveryCandidateCount"],
        "acceptedProductOne": report["acceptedProductOne"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
