from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.additive_purification_search import search_additive_purification_stations
from packages.opus_solver.purification_chain import purification_profile

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")


def _run_omsim(omsim: Path, puzzle: Path, solution: Path) -> dict[str, Any]:
    process = subprocess.run(
        [str(omsim), "--puzzle-file", str(puzzle), "--metric", "product 1 cycles", str(solution)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = ((process.stdout or "") + (process.stderr or "")).strip()
    match = _COLLISION_RE.search(text)
    progress = 1_000_000_000 if process.returncode == 0 else (
        int(match.group(1)) if match else (999_999_999 if "cycle limit" in text.lower() else 0)
    )
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
    result_limit: int = 30,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_path)
    baseline_profile = purification_profile(puzzle, solution, max_cycles=max_cycles)
    baseline_oracle = _run_omsim(omsim, puzzle_path, baseline_path)

    additive = search_additive_purification_stations(
        puzzle,
        solution,
        max_cycles=max_cycles,
        opportunity_limit=opportunity_limit,
        result_limit=max(result_limit, 40),
    )

    evaluated: list[dict[str, Any]] = []
    for index, variant in enumerate(additive.get("variants", []) or []):
        candidate = variant.get("solution")
        if not candidate:
            continue
        path = output_dir / f"candidate-{index:03d}.solution"
        write_solution(candidate, path)
        oracle = _run_omsim(omsim, puzzle_path, path)
        evaluated.append({
            "repairMode": variant.get("repairMode"),
            "opportunity": variant.get("opportunity"),
            "addedUnbonderCount": variant.get("addedUnbonderCount"),
            "purificationProfile": variant.get("purificationProfile"),
            "solutionPath": str(path),
            "omsim": oracle,
        })

    baseline_frontier = int(baseline_profile.get("frontierIndex") if baseline_profile.get("frontierIndex") is not None else -1)
    baseline_progress = int(baseline_oracle.get("progressCycle") or 0)
    evaluated.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("purificationProfile") or {}).get("frontierIndex") if (item.get("purificationProfile") or {}).get("frontierIndex") is not None else -1),
            int((item.get("omsim") or {}).get("progressCycle") or 0) >= baseline_progress,
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int((item.get("purificationProfile") or {}).get("count") or 0),
        ),
        reverse=True,
    )
    best = evaluated[0] if evaluated else None
    if best:
        final = parse_solution(best["solutionPath"])
        final_path = output_dir / "GEN249-best-oracle-additive-frontier.solution"
        write_solution(final, final_path)
        best["finalSolutionPath"] = str(final_path)

    advancing_and_surviving = [
        item for item in evaluated
        if int((item.get("purificationProfile") or {}).get("frontierIndex") if (item.get("purificationProfile") or {}).get("frontierIndex") is not None else -1) > baseline_frontier
        and int((item.get("omsim") or {}).get("progressCycle") or 0) >= baseline_progress
    ]
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-oracle-additive-frontier-search",
        "targetSolutionBytesUsed": 0,
        "baselinePurificationProfile": baseline_profile,
        "baselineOMSim": baseline_oracle,
        "additiveSummary": additive.get("summary"),
        "additiveOpportunityCount": len(additive.get("opportunities", []) or []),
        "variantCount": len(evaluated),
        "advancingAndOracleNonregressingCount": len(advancing_and_surviving),
        "best": best,
        "topVariants": evaluated[:30],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the next chemistry frontier on an OMSim-safer generated mechanism.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--opportunity-limit", type=int, default=240)
    parser.add_argument("--result-limit", type=int, default=30)
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
        "baselinePurificationProfile": report["baselinePurificationProfile"],
        "baselineOMSim": report["baselineOMSim"],
        "additiveSummary": report["additiveSummary"],
        "variantCount": report["variantCount"],
        "advancingAndOracleNonregressingCount": report["advancingAndOracleNonregressingCount"],
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
