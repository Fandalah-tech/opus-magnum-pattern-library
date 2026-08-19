from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.initial_overlap_repair import (
    initial_arm_base_overlaps,
    relocate_arm_base_preserving_tip,
)
from packages.opus_solver.product_delivery import ensure_all_standard_outputs


def probe(puzzle_path: Path, solution_path: Path, output_dir: Path) -> dict:
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(solution_path)
    baseline = ensure_all_standard_outputs(puzzle, solution)
    output_dir.mkdir(parents=True, exist_ok=True)

    variants: list[dict] = []

    def add_variant(name: str, candidate: dict, metadata: dict) -> None:
        path = output_dir / f"{name}.solution"
        write_solution(candidate, path)
        variants.append({
            "name": name,
            "solution": str(path),
            **metadata,
        })

    overlaps = initial_arm_base_overlaps(puzzle, baseline)
    add_variant("baseline-complete-outputs", baseline, {"mode": "baseline"})

    for overlap_index, overlap in enumerate(overlaps):
        arm_id = str(overlap.get("armPartId") or "")
        removed = deepcopy(baseline)
        removed["parts"] = [
            part for part in removed.get("parts", []) or []
            if str(part.get("id") or "") != arm_id
        ]
        removed.setdefault("source", {})["omsimMechanicalPreflight"] = {
            "mode": "remove-overlap-arm",
            "armPartId": arm_id,
            "targetSolutionBytesUsed": 0,
        }
        add_variant(
            f"overlap-{overlap_index:02d}-removed",
            removed,
            {"mode": "remove-overlap-arm", "overlap": overlap},
        )

        tip = tuple(int(value) for value in overlap.get("preservedTip") or (0, 0))
        for rotation in range(6):
            if rotation == int(overlap.get("armRotation") or 0):
                continue
            relocated = relocate_arm_base_preserving_tip(
                baseline,
                arm_part_id=arm_id,
                preserved_tip=tip,
                new_rotation=rotation,
            )
            add_variant(
                f"overlap-{overlap_index:02d}-rotation-{rotation}",
                relocated,
                {
                    "mode": "relocate-overlap-arm",
                    "overlap": overlap,
                    "newRotation": rotation,
                    "repair": (relocated.get("source", {}).get("initialArmBaseRepairs") or [])[-1],
                },
            )

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-omsim-mechanical-preflight-variants",
        "targetPuzzle": puzzle_path.name,
        "baselineSolution": solution_path.name,
        "targetSolutionBytesUsed": 0,
        "overlapCount": len(overlaps),
        "overlaps": overlaps,
        "variantCount": len(variants),
        "variants": variants,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate target-free OMSim mechanical preflight variants.")
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--solution", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report = probe(args.puzzle, args.solution, args.output_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetPuzzle": report["targetPuzzle"],
        "overlapCount": report["overlapCount"],
        "variantCount": report["variantCount"],
        "targetSolutionBytesUsed": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
