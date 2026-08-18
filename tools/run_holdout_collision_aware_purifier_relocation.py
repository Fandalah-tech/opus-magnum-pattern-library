from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import rotate_hex
from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.purification_chain import purification_profile
from packages.opus_solver.reaction_placement import (
    apply_purification_placement,
    purification_opportunities,
)

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _purifier_output(part: dict[str, Any]) -> tuple[int, int]:
    origin = _position(part.get("position"))
    delta = rotate_hex((0, 1), int(part.get("rotation") or 0) % 6)
    return origin[0] + delta[0], origin[1] + delta[1]


def _run_omsim(omsim: Path, puzzle: Path, solution: Path) -> dict[str, Any]:
    process = subprocess.run(
        [str(omsim), "--puzzle-file", str(puzzle), "--metric", "product 1 cycles", str(solution)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = ((process.stdout or "") + (process.stderr or "")).strip()
    match = _COLLISION_RE.search(text)
    if process.returncode == 0:
        progress = 1_000_000_000
    elif match:
        progress = int(match.group(1))
    elif "cycle limit" in text.lower():
        progress = 999_999_999
    else:
        progress = 0
    return {
        "exitCode": int(process.returncode),
        "output": text,
        "progressCycle": progress,
        "collisionCycle": int(match.group(1)) if match else None,
        "collisionLocation": [int(match.group(2)), int(match.group(3))] if match else None,
    }


def search(
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    max_cycles: int = 500,
    opportunity_limit: int = 160,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_path)
    baseline_oracle = _run_omsim(omsim, puzzle_path, baseline_path)
    collision_raw = baseline_oracle.get("collisionLocation")
    baseline_profile = purification_profile(puzzle, solution, max_cycles=max_cycles)
    if not collision_raw:
        return {
            "schemaVersion": "0.1.0",
            "kind": "strict-heldout-collision-aware-purifier-relocation-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "baselinePurificationProfile": baseline_profile,
            "offendingPurifierCount": 0,
            "variantCount": 0,
            "best": None,
        }
    collision = tuple(int(value) for value in collision_raw)

    purifiers = [
        part for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "glyph-purification"
    ]
    offending_indices = [
        index for index, part in enumerate(purifiers)
        if _purifier_output(part) == collision
    ]

    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=max_cycles))
    opportunities = purification_opportunities(replay, include_blocked=True)

    required_frontier = str(baseline_profile.get("frontierElement") or "")
    required_frontier_count = int((baseline_profile.get("countsByElement") or {}).get(required_frontier, 0))
    candidates = [
        item for item in opportunities
        if str(item.get("producedElement") or "") == required_frontier
        and tuple(int(value) for value in item.get("output") or (0, 0)) != collision
    ]
    candidates.sort(key=lambda item: (
        int(item.get("minimumBlockerCount") or 0),
        -int(item.get("readyObservationCount") or 0),
        -int(item.get("observationCount") or 0),
        int(item.get("firstCycle") or 0),
    ))
    candidates = candidates[:max(0, int(opportunity_limit))]

    evaluated: list[dict[str, Any]] = []
    local_preserving_count = 0
    for purifier_index in offending_indices:
        for opportunity in candidates:
            candidate = apply_purification_placement(
                solution,
                purifier_index=purifier_index,
                opportunity=opportunity,
            )
            profile = purification_profile(puzzle, candidate, max_cycles=max_cycles)
            frontier_count = int((profile.get("countsByElement") or {}).get(required_frontier, 0))
            if frontier_count < required_frontier_count:
                continue
            local_preserving_count += 1
            path = output_dir / f"candidate-{len(evaluated):03d}.solution"
            write_solution(candidate, path)
            oracle = _run_omsim(omsim, puzzle_path, path)
            evaluated.append({
                "purifierIndex": purifier_index,
                "purifierPartId": str(purifiers[purifier_index].get("id") or ""),
                "oldOutput": list(collision),
                "opportunity": opportunity,
                "purificationProfile": profile,
                "solutionPath": str(path),
                "omsim": oracle,
            })

    evaluated.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int((item.get("purificationProfile") or {}).get("count") or 0),
        ),
        reverse=True,
    )
    best = evaluated[0] if evaluated else None
    if best:
        best_solution = parse_solution(best["solutionPath"])
        final_path = output_dir / "GEN249-best-collision-aware-purifier.solution"
        write_solution(best_solution, final_path)
        best["finalSolutionPath"] = str(final_path)

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-collision-aware-purifier-relocation-search",
        "targetSolutionBytesUsed": 0,
        "baselineOMSim": baseline_oracle,
        "baselinePurificationProfile": baseline_profile,
        "collisionLocation": list(collision),
        "offendingPurifierCount": len(offending_indices),
        "offendingPurifierIndices": offending_indices,
        "requiredFrontierElement": required_frontier,
        "requiredFrontierCount": required_frontier_count,
        "opportunityCount": len(candidates),
        "localPreservingVariantCount": local_preserving_count,
        "variantCount": len(evaluated),
        "best": best,
        "topVariants": evaluated[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Move a replay-proven purification output away from an OMSim collision hex.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--opportunity-limit", type=int, default=160)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        max_cycles=args.max_cycles,
        opportunity_limit=args.opportunity_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "collisionLocation": report.get("collisionLocation"),
        "offendingPurifierCount": report["offendingPurifierCount"],
        "opportunityCount": report.get("opportunityCount", 0),
        "variantCount": report["variantCount"],
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
