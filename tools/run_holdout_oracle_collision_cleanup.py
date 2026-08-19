from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS
from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from tools.run_holdout_oracle_base_repair import run_omsim


def _pos(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _frame_for_cycle(replay: dict[str, Any], cycle: int) -> dict[str, Any] | None:
    frames = replay.get("frames", []) or []
    exact = [frame for frame in frames if int(frame.get("cycle") or 0) == int(cycle)]
    if exact:
        return exact[-1]
    earlier = [frame for frame in frames if int(frame.get("cycle") or 0) <= int(cycle)]
    return earlier[-1] if earlier else None


def _next_arm_number(solution: dict[str, Any]) -> int:
    return 1 + max(
        (int(part.get("armNumber") or 0) for part in solution.get("parts", []) or []),
        default=0,
    )


def _initial_atom_cells(puzzle: dict[str, Any], solution: dict[str, Any]) -> set[tuple[int, int]]:
    simulator = Simulator.from_models(puzzle, solution)
    frame = simulator.frames[0] if simulator.frames else simulator.snapshot("initial")
    return {_pos(atom.get("position")) for atom in (frame.get("world") or {}).get("atoms", []) or []}


def _cleanup_variants(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    collision_cycle: int,
    collision_location: tuple[int, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    horizon = max(1, int(collision_cycle) + 2)
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    frame = _frame_for_cycle(replay, int(collision_cycle) - 1)
    world = (frame or {}).get("world") or {}
    atoms = list(world.get("atoms", []) or [])
    at_collision = [atom for atom in atoms if _pos(atom.get("position")) == collision_location]
    unheld = [atom for atom in at_collision if not (atom.get("heldBy") or [])]
    initial_cells = _initial_atom_cells(puzzle, solution)
    existing_arm_bases = {
        _pos(part.get("position"))
        for part in solution.get("parts", []) or []
        if str(part.get("type") or "").startswith("arm") or str(part.get("type") or "") in {"piston", "baron"}
    }

    variants: list[dict[str, Any]] = []
    for atom in unheld:
        for rotation, direction in enumerate(DIRECTIONS):
            base = (collision_location[0] - direction[0], collision_location[1] - direction[1])
            if base in initial_cells or base in existing_arm_bases:
                continue
            for instruction in ("rotate_cw", "rotate_ccw"):
                candidate = deepcopy(solution)
                serial = 0
                existing = {str(part.get("id") or "") for part in candidate.get("parts", []) or []}
                while f"oracle-cleanup-arm-{serial}" in existing:
                    serial += 1
                part_id = f"oracle-cleanup-arm-{serial}"
                candidate.setdefault("parts", []).append({
                    "id": part_id,
                    "type": "arm1",
                    "enabled": True,
                    "position": [base[0], base[1]],
                    "length": 1,
                    "rotation": rotation,
                    "which": 0,
                    "armNumber": _next_arm_number(candidate),
                    "program": [
                        {"cycle": int(collision_cycle) - 1, "instruction": "grab"},
                        {"cycle": int(collision_cycle), "instruction": instruction},
                        {"cycle": int(collision_cycle) + 1, "instruction": "drop"},
                    ],
                })
                candidate.setdefault("source", {}).setdefault("oracleCollisionCleanupRepairs", []).append({
                    "armPartId": part_id,
                    "collisionCycle": int(collision_cycle),
                    "collisionLocation": list(collision_location),
                    "targetAtomId": str(atom.get("id") or ""),
                    "targetElement": str(atom.get("element") or ""),
                    "base": [base[0], base[1]],
                    "rotation": rotation,
                    "motionInstruction": instruction,
                    "targetSolutionBytesUsed": 0,
                })
                variants.append({
                    "targetAtomId": str(atom.get("id") or ""),
                    "targetElement": str(atom.get("element") or ""),
                    "base": [base[0], base[1]],
                    "rotation": rotation,
                    "motionInstruction": instruction,
                    "solution": candidate,
                })

    diagnosis = {
        "frameCycle": int((frame or {}).get("cycle") or -1),
        "collisionCycle": int(collision_cycle),
        "collisionLocation": list(collision_location),
        "atomsAtCollisionLocation": [
            {
                "id": str(atom.get("id") or ""),
                "element": str(atom.get("element") or ""),
                "position": list(_pos(atom.get("position"))),
                "heldBy": list(atom.get("heldBy") or []),
            }
            for atom in at_collision
        ],
        "unheldAtomCount": len(unheld),
        "initialAtomCellsBlockCleanup": list(collision_location) in [list(cell) for cell in initial_cells],
    }
    return variants, diagnosis


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_path)
    baseline_copy = output_dir / "baseline.solution"
    write_solution(solution, baseline_copy)
    baseline_oracle = run_omsim(omsim, puzzle_path, baseline_copy)
    collision_cycle = baseline_oracle.get("collisionCycle")
    location = baseline_oracle.get("collisionLocation")
    if collision_cycle is None or location is None:
        accepted = int(baseline_oracle.get("exitCode") or 0) == 0
        return {
            "schemaVersion": "0.1.0",
            "kind": "strict-heldout-oracle-collision-cleanup-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "diagnosis": None,
            "generatedVariantCount": 0,
            "searchedVariantCount": 0,
            "acceptedProductOne": accepted,
            "acceptedSolution": str(baseline_copy) if accepted else None,
            "acceptedOMSim": baseline_oracle if accepted else None,
            "topVariants": [],
        }

    variants, diagnosis = _cleanup_variants(
        puzzle,
        solution,
        collision_cycle=int(collision_cycle),
        collision_location=(int(location[0]), int(location[1])),
    )
    records: list[dict[str, Any]] = []
    accepted: dict[str, Any] | None = None
    for index, variant in enumerate(variants):
        path = output_dir / f"candidate-{index:02d}.solution"
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
        ),
        reverse=True,
    )
    accepted_output = None
    if accepted is not None:
        accepted_output = output_dir / "GEN249-omsim-product1.solution"
        accepted_output.write_bytes(Path(accepted["solutionPath"]).read_bytes())
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-oracle-collision-cleanup-search",
        "targetSolutionBytesUsed": 0,
        "baselineOMSim": baseline_oracle,
        "diagnosis": diagnosis,
        "generatedVariantCount": len(variants),
        "searchedVariantCount": len(records),
        "acceptedProductOne": accepted is not None,
        "acceptedSolution": str(accepted_output) if accepted_output is not None else None,
        "acceptedOMSim": accepted.get("omsim") if accepted is not None else None,
        "topVariants": records[:40],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Use the official collision cell plus the generated local world to synthesize a one-time cleanup arm.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim,
        puzzle_path=args.puzzle,
        baseline_path=args.baseline,
        output_dir=args.output_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "diagnosis": report["diagnosis"],
        "generatedVariantCount": report["generatedVariantCount"],
        "acceptedProductOne": report["acceptedProductOne"],
        "acceptedOMSim": report["acceptedOMSim"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
