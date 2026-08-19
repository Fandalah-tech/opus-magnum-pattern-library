from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.adjacent_intermediate_purification import (
    search_adjacent_intermediate_purification,
)
from packages.opus_solver.product_delivery import search_singleton_product_delivery

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")
_PRODUCT_RE = re.compile(r"product 1 cycles:\s*([0-9.]+)")


def _run_omsim(omsim: Path, puzzle: Path, solution: Path) -> dict[str, Any]:
    process = subprocess.run(
        [str(omsim), "--puzzle-file", str(puzzle), "--metric", "product 1 cycles", str(solution)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = ((process.stdout or "") + (process.stderr or "")).strip()
    collision = _COLLISION_RE.search(output)
    product = _PRODUCT_RE.search(output)
    return {
        "exitCode": int(process.returncode),
        "output": output,
        "collisionCycle": int(collision.group(1)) if collision else None,
        "collisionLocation": [int(collision.group(2)), int(collision.group(3))] if collision else None,
        "product1Cycles": float(product.group(1)) if product and process.returncode == 0 else None,
    }


def _gold_cycle(profile: dict[str, Any]) -> int | None:
    cycles = list((profile.get("cyclesByElement") or {}).get("gold") or [])
    return min((int(value) for value in cycles), default=None)


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    max_cycles: int = 1500,
    adjacent_limit: int = 24,
    delivery_limit: int = 24,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    baseline = parse_solution(baseline_path)

    adjacent = search_adjacent_intermediate_purification(
        puzzle,
        baseline,
        element="silver",
        max_cycles=max_cycles,
        observation_limit=160,
        result_limit=adjacent_limit,
    )
    adjacent_records: list[dict[str, Any]] = []
    delivery_records: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None

    for index, variant in enumerate(adjacent.get("variants", []) or []):
        path = output_dir / "adjacent" / f"candidate-{index:02d}.solution"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_solution(variant["solution"], path)
        oracle = _run_omsim(omsim, puzzle_path, path)
        profile = variant.get("purificationProfile") or {}
        gold_cycle = _gold_cycle(profile)
        collision_cycle = oracle.get("collisionCycle")
        gold_reachable = bool(
            gold_cycle is not None
            and (collision_cycle is None or int(gold_cycle) < int(collision_cycle))
        )
        record = {
            "candidateIndex": index,
            "solutionPath": str(path),
            "observation": variant.get("observation"),
            "purifierPose": variant.get("purifierPose"),
            "purificationProfile": profile,
            "goldCycle": gold_cycle,
            "omsim": oracle,
            "goldBeforeOfficialCollision": gold_reachable,
        }
        adjacent_records.append(record)
        if not gold_reachable:
            continue

        delivery = search_singleton_product_delivery(
            puzzle,
            variant["solution"],
            max_cycles=max_cycles,
            opportunity_limit=120,
            result_limit=delivery_limit,
        )
        for delivery_index, delivery_variant in enumerate(delivery.get("variants", []) or []):
            delivery_path = output_dir / "delivery" / f"adjacent-{index:02d}-candidate-{delivery_index:02d}.solution"
            delivery_path.parent.mkdir(parents=True, exist_ok=True)
            write_solution(delivery_variant["solution"], delivery_path)
            delivery_oracle = _run_omsim(omsim, puzzle_path, delivery_path)
            delivery_record = {
                "parentAdjacentIndex": index,
                "deliveryIndex": delivery_index,
                "solutionPath": str(delivery_path),
                "localSummary": delivery_variant.get("summary"),
                "omsim": delivery_oracle,
            }
            delivery_records.append(delivery_record)
            if int(delivery_oracle.get("exitCode") or 0) == 0:
                accepted = delivery_record
                break
        if accepted is not None:
            break

    adjacent_records.sort(
        key=lambda item: (
            int(bool(item.get("goldBeforeOfficialCollision"))),
            -int(item.get("goldCycle") or 10**9),
            int((item.get("omsim") or {}).get("collisionCycle") or 10**9),
        ),
        reverse=True,
    )
    delivery_records.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            -float((item.get("omsim") or {}).get("product1Cycles") or 10**9),
            int((item.get("omsim") or {}).get("collisionCycle") or 0),
        ),
        reverse=True,
    )

    accepted_output = None
    if accepted is not None:
        accepted_output = output_dir / "GEN249-omsim-product1.solution"
        accepted_output.write_bytes(Path(accepted["solutionPath"]).read_bytes())

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-adjacent-pair-finish",
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": int(max_cycles),
            "adjacentLimit": int(adjacent_limit),
            "deliveryLimit": int(delivery_limit),
        },
        "adjacentSummary": adjacent.get("summary"),
        "baselinePurificationProfile": adjacent.get("baselinePurificationProfile"),
        "observations": list(adjacent.get("observations") or [])[:80],
        "adjacentCandidateCount": len(adjacent_records),
        "goldBeforeOfficialCollisionCount": sum(bool(item.get("goldBeforeOfficialCollision")) for item in adjacent_records),
        "adjacentCandidates": adjacent_records[:40],
        "deliveryCandidateCount": len(delivery_records),
        "deliveryCandidates": delivery_records[:60],
        "acceptedProductOne": accepted is not None,
        "acceptedSolution": str(accepted_output) if accepted_output is not None else None,
        "acceptedOMSim": accepted.get("omsim") if accepted is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exploit an already-adjacent silver pair and immediately try the first official product.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=1500)
    parser.add_argument("--adjacent-limit", type=int, default=24)
    parser.add_argument("--delivery-limit", type=int, default=24)
    args = parser.parse_args()

    report = search(
        omsim=args.omsim,
        puzzle_path=args.puzzle,
        baseline_path=args.baseline,
        output_dir=args.output_dir,
        max_cycles=args.max_cycles,
        adjacent_limit=args.adjacent_limit,
        delivery_limit=args.delivery_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "adjacentSummary": report["adjacentSummary"],
        "goldBeforeOfficialCollisionCount": report["goldBeforeOfficialCollisionCount"],
        "deliveryCandidateCount": report["deliveryCandidateCount"],
        "acceptedProductOne": report["acceptedProductOne"],
        "acceptedOMSim": report["acceptedOMSim"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
