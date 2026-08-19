from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_solution, write_solution
from tools.run_holdout_oracle_base_repair import run_omsim
from tools.run_holdout_oracle_timing_repair import timing_variants


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    window: int = 10,
    max_delay: int = 12,
) -> dict[str, Any]:
    """Use OMSim itself as the only acceptance oracle for the last timing edge.

    The baseline already locally contains a completed product. At this final
    stage we do not need to replay every timing mutation in Python: serialize a
    bounded phase-aware timing neighborhood, ask pinned OMSim for `product 1
    cycles`, and stop immediately on the first accepted candidate. This avoids
    spending most of the search budget re-simulating candidates the official
    oracle rejects anyway.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = parse_solution(baseline_path)
    baseline_copy = output_dir / "baseline.solution"
    write_solution(baseline, baseline_copy)
    baseline_oracle = run_omsim(omsim, puzzle_path, baseline_copy)
    collision_cycle = baseline_oracle.get("collisionCycle")
    if collision_cycle is None:
        return {
            "schemaVersion": "0.1.0",
            "kind": "strict-heldout-fast-product-timing-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "searchedVariantCount": 0,
            "acceptedProductOne": int(baseline_oracle.get("exitCode") or 0) == 0,
            "acceptedSolution": str(baseline_copy) if int(baseline_oracle.get("exitCode") or 0) == 0 else None,
            "acceptedOMSim": baseline_oracle if int(baseline_oracle.get("exitCode") or 0) == 0 else None,
            "topVariants": [],
        }

    variants = timing_variants(
        baseline,
        collision_cycle=int(collision_cycle),
        window=window,
        max_delay=max_delay,
    )
    records: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None
    for index, variant in enumerate(variants):
        path = output_dir / f"candidate-{index:03d}.solution"
        write_solution(variant["solution"], path)
        oracle = run_omsim(omsim, puzzle_path, path)
        record = {
            **{key: value for key, value in variant.items() if key != "solution"},
            "solutionPath": str(path),
            "omsim": oracle,
        }
        records.append(record)
        if int(oracle.get("exitCode") or 0) == 0:
            accepted = record
            break

    records.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            -abs(int(item.get("delta") or 0)),
        ),
        reverse=True,
    )
    accepted_output = None
    if accepted is not None:
        accepted_output = output_dir / "GEN249-omsim-product1.solution"
        accepted_output.write_bytes(Path(accepted["solutionPath"]).read_bytes())

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-fast-product-timing-search",
        "targetSolutionBytesUsed": 0,
        "request": {"window": int(window), "maxDelay": int(max_delay)},
        "baselineOMSim": baseline_oracle,
        "generatedVariantCount": len(variants),
        "searchedVariantCount": len(records),
        "acceptedProductOne": accepted is not None,
        "acceptedSolution": str(accepted_output) if accepted_output is not None else None,
        "acceptedOMSim": accepted.get("omsim") if accepted is not None else None,
        "topVariants": records[:40],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast OMSim-only timing search around a blind locally delivered product.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument("--max-delay", type=int, default=12)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim,
        puzzle_path=args.puzzle,
        baseline_path=args.baseline,
        output_dir=args.output_dir,
        window=args.window,
        max_delay=args.max_delay,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "generatedVariantCount": report.get("generatedVariantCount", 0),
        "searchedVariantCount": report["searchedVariantCount"],
        "acceptedProductOne": report["acceptedProductOne"],
        "acceptedOMSim": report["acceptedOMSim"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
