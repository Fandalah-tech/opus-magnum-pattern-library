from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_solution, write_solution
from tools.run_holdout_track_neighborhood_detour_search import search as search_one_detour


def _counts(profile: dict[str, Any]) -> tuple[int, int, int, int]:
    values = profile.get("countsByElement") or {}
    return (
        int(values.get("gold", 0)),
        int(values.get("silver", 0)),
        int(values.get("copper", 0)),
        int(profile.get("count") or 0),
    )


def search(
    omsim: Path,
    puzzle: Path,
    baseline: Path,
    output_dir: Path,
    *,
    max_cycles: int = 500,
    radius: int = 3,
    iterations: int = 8,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    current = Path(baseline)
    history: list[dict[str, Any]] = []

    for iteration in range(1, max(1, int(iterations)) + 1):
        stage_dir = output_dir / f"iteration-{iteration:02d}"
        result = search_one_detour(
            omsim,
            puzzle,
            current,
            stage_dir,
            max_cycles=max_cycles,
            radius=radius,
        )
        baseline_oracle = result.get("baselineOMSim") or {}
        baseline_profile = result.get("baselinePurificationProfile") or {}
        best = result.get("best")
        record = {
            "iteration": iteration,
            "baselineSolution": str(current),
            "baselineOMSim": baseline_oracle,
            "baselinePurificationProfile": baseline_profile,
            "rawCandidateCount": int(result.get("rawCandidateCount") or 0),
            "chemistryPreservingNonregressingCount": int(result.get("chemistryPreservingNonregressingCount") or 0),
            "best": best,
        }
        history.append(record)
        if not best:
            record["stopReason"] = "no-neighborhood-detour"
            break

        best_oracle = best.get("omsim") or {}
        best_profile = best.get("purificationProfile") or {}
        if int(best_oracle.get("progressCycle") or 0) < int(baseline_oracle.get("progressCycle") or 0):
            record["stopReason"] = "oracle-regression"
            break
        if _counts(best_profile) < _counts(baseline_profile):
            record["stopReason"] = "chemistry-regression"
            break
        new_path = best.get("finalSolutionPath") or best.get("solutionPath")
        if not new_path:
            record["stopReason"] = "missing-best-solution"
            break
        if int(best_oracle.get("progressCycle") or 0) == int(baseline_oracle.get("progressCycle") or 0):
            # Allow one equal-progress spatial diversification, but stop if the
            # exact same physical solution would otherwise cycle forever.
            previous = parse_solution(current)
            candidate = parse_solution(new_path)
            if previous.get("parts") == candidate.get("parts"):
                record["stopReason"] = "no-physical-change"
                break
        current = Path(new_path)
        if int(best_oracle.get("exitCode") or 1) == 0:
            record["stopReason"] = "omsim-product-one"
            break

    final_solution = parse_solution(current)
    final_path = output_dir / "GEN249-best-iterative-track-detour.solution"
    write_solution(final_solution, final_path)
    final_record = history[-1] if history else {}
    final_best = final_record.get("best") or {}
    final_oracle = final_best.get("omsim") or final_record.get("baselineOMSim")
    final_profile = final_best.get("purificationProfile") or final_record.get("baselinePurificationProfile")
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-iterative-track-neighborhood-detour-search",
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": max_cycles,
            "radius": radius,
            "iterations": iterations,
        },
        "iterationCount": len(history),
        "history": history,
        "finalSolution": str(final_path),
        "finalOMSim": final_oracle,
        "finalPurificationProfile": final_profile,
        "acceptedProductOne": int((final_oracle or {}).get("exitCode") or 1) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Iterate target-free track detours while preserving chemistry under OMSim.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--radius", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=8)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        max_cycles=args.max_cycles,
        radius=args.radius,
        iterations=args.iterations,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "iterationCount": report["iterationCount"],
        "finalOMSim": report["finalOMSim"],
        "finalPurificationProfile": report["finalPurificationProfile"],
        "acceptedProductOne": report["acceptedProductOne"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
