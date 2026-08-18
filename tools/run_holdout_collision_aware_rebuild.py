from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_engine.builder import rotate_hex
from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.additive_purification_search import search_additive_purification_stations
from packages.opus_solver.purification_chain import purification_profile

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
    opportunity_limit: int = 240,
    result_limit: int = 24,
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
            "kind": "strict-heldout-collision-aware-reaction-rebuild-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "variantCount": 0,
            "best": None,
        }
    collision = tuple(int(value) for value in collision_raw)

    offending_ids = {
        str(part.get("id") or "")
        for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "glyph-purification"
        and _purifier_output(part) == collision
    }
    stripped = deepcopy(solution)
    stripped["parts"] = [
        part for part in stripped.get("parts", []) or []
        if str(part.get("id") or "") not in offending_ids
    ]
    stripped.setdefault("source", {})["generator"] = "opus_solver/collision-aware-reaction-rebuild-v1"
    stripped["source"]["collisionAwareReactionRebuild"] = {
        "removedPurifierPartIds": sorted(offending_ids),
        "collisionLocation": list(collision),
        "targetSolutionBytesUsed": 0,
    }
    stripped_profile = purification_profile(puzzle, stripped, max_cycles=max_cycles)

    additive = search_additive_purification_stations(
        puzzle,
        stripped,
        max_cycles=max_cycles,
        opportunity_limit=opportunity_limit,
        result_limit=max(result_limit * 2, 40),
    )

    evaluated: list[dict[str, Any]] = []
    skipped_same_output = 0
    for index, variant in enumerate(additive.get("variants", []) or []):
        opportunity = variant.get("opportunity") or {}
        if tuple(int(value) for value in opportunity.get("output") or (0, 0)) == collision:
            skipped_same_output += 1
            continue
        candidate = variant.get("solution")
        if not candidate:
            continue
        path = output_dir / f"candidate-{index:03d}.solution"
        write_solution(candidate, path)
        oracle = _run_omsim(omsim, puzzle_path, path)
        evaluated.append({
            "repairMode": variant.get("repairMode"),
            "opportunity": opportunity,
            "addedUnbonderCount": int(variant.get("addedUnbonderCount") or 0),
            "purificationProfile": variant.get("purificationProfile"),
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
        final = parse_solution(best["solutionPath"])
        final_path = output_dir / "GEN249-best-collision-aware-rebuild.solution"
        write_solution(final, final_path)
        best["finalSolutionPath"] = str(final_path)

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-collision-aware-reaction-rebuild-search",
        "targetSolutionBytesUsed": 0,
        "baselineOMSim": baseline_oracle,
        "baselinePurificationProfile": baseline_profile,
        "collisionLocation": list(collision),
        "removedPurifierPartIds": sorted(offending_ids),
        "strippedPurificationProfile": stripped_profile,
        "additiveSummary": additive.get("summary"),
        "additiveOpportunityCount": len(additive.get("opportunities", []) or []),
        "additiveVariantCount": len(additive.get("variants", []) or []),
        "skippedSameOutputCount": skipped_same_output,
        "variantCount": len(evaluated),
        "best": best,
        "topVariants": evaluated[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild a purification station away from an OMSim produced-atom collision.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--opportunity-limit", type=int, default=240)
    parser.add_argument("--result-limit", type=int, default=24)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        max_cycles=args.max_cycles,
        opportunity_limit=args.opportunity_limit,
        result_limit=args.result_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "removedPurifierPartIds": report.get("removedPurifierPartIds", []),
        "strippedPurificationProfile": report.get("strippedPurificationProfile"),
        "additiveSummary": report.get("additiveSummary"),
        "variantCount": report["variantCount"],
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
