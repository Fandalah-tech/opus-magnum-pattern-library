from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_solution, write_solution
from tools.run_holdout_oracle_base_repair import run_omsim
from tools.run_holdout_oracle_timing_repair import _physical_nearby_program_indices

_ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}


def _signature(solution: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            str(part.get("id") or ""),
            tuple(
                (int(item.get("cycle") or 0), str(item.get("instruction") or ""))
                for item in sorted(part.get("program", []) or [], key=lambda x: int(x.get("cycle") or 0))
            ),
        )
        for part in solution.get("parts", []) or []
        if str(part.get("type") or "") in _ARM_TYPES
    )


def _variants(solution: dict[str, Any], collision_cycle: int, window: int = 10) -> list[dict[str, Any]]:
    implicated = _physical_nearby_program_indices(
        solution,
        collision_cycle=collision_cycle,
        window=window,
    )
    variants: list[dict[str, Any]] = []
    seen = {_signature(solution)}
    for part_index, part in enumerate(solution.get("parts", []) or []):
        part_id = str(part.get("id") or f"part-{part_index}")
        indices = sorted(implicated.get(part_id) or set())
        if not indices:
            continue
        program = [dict(item) for item in part.get("program", []) or []]
        if not program:
            continue
        occupied = {int(item.get("cycle") or 0) for item in program}
        min_cycle = min(occupied)
        max_cycle = max(occupied)

        for instruction_index in indices:
            if instruction_index < 0 or instruction_index >= len(program):
                continue
            original = program[instruction_index]
            original_instruction = str(original.get("instruction") or "")
            original_cycle = int(original.get("cycle") or 0)
            if original_instruction in {"period_override", "repeat", "reset"}:
                continue

            neutral = deepcopy(solution)
            target_program = neutral["parts"][part_index].get("program", []) or []
            target_program[instruction_index] = {
                **target_program[instruction_index],
                "instruction": "period_override",
                "rawCode": "O",
            }
            signature = _signature(neutral)
            if signature not in seen:
                seen.add(signature)
                variants.append({
                    "mode": "neutralize-source-cell",
                    "armPartId": part_id,
                    "instructionIndex": instruction_index,
                    "oldCycle": original_cycle,
                    "oldInstruction": original_instruction,
                    "newInstruction": "period_override",
                    "solution": neutral,
                })

            # Move the action into a nearby genuinely blank source tape cell,
            # leaving O at the old cell so the tape extent/period is unchanged.
            # Keeping the new cell within the old min/max avoids the period
            # stretching that caused chemistry and collision to march together.
            for delta in (-3, -2, -1, 1, 2, 3):
                new_cycle = original_cycle + delta
                if new_cycle < min_cycle or new_cycle > max_cycle or new_cycle in occupied:
                    continue
                moved = deepcopy(solution)
                moved_program = [dict(item) for item in moved["parts"][part_index].get("program", []) or []]
                moved_program[instruction_index] = {
                    **moved_program[instruction_index],
                    "instruction": "period_override",
                    "rawCode": "O",
                }
                moved_program.append({
                    "cycle": new_cycle,
                    "instruction": original_instruction,
                    "rawCode": original.get("rawCode"),
                })
                moved_program.sort(key=lambda item: int(item.get("cycle") or 0))
                moved["parts"][part_index]["program"] = moved_program
                signature = _signature(moved)
                if signature in seen:
                    continue
                seen.add(signature)
                variants.append({
                    "mode": "move-source-cell-with-period-preserved",
                    "armPartId": part_id,
                    "instructionIndex": instruction_index,
                    "oldCycle": original_cycle,
                    "newCycle": new_cycle,
                    "delta": delta,
                    "instruction": original_instruction,
                    "solution": moved,
                })
    return variants


def search(
    *,
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    window: int = 10,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = parse_solution(baseline_path)
    baseline_copy = output_dir / "baseline.solution"
    write_solution(baseline, baseline_copy)
    baseline_oracle = run_omsim(omsim, puzzle_path, baseline_copy)
    collision_cycle = baseline_oracle.get("collisionCycle")
    if collision_cycle is None:
        accepted = int(baseline_oracle.get("exitCode") or 0) == 0
        return {
            "schemaVersion": "0.1.0",
            "kind": "strict-heldout-collision-phase-neutralization-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "physicalPhaseProgramIndices": {},
            "generatedVariantCount": 0,
            "searchedVariantCount": 0,
            "acceptedProductOne": accepted,
            "acceptedSolution": str(baseline_copy) if accepted else None,
            "acceptedOMSim": baseline_oracle if accepted else None,
            "topVariants": [],
        }

    physical = _physical_nearby_program_indices(
        baseline,
        collision_cycle=int(collision_cycle),
        window=window,
    )
    variants = _variants(baseline, int(collision_cycle), window=window)
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
            int(item.get("mode") == "neutralize-source-cell"),
        ),
        reverse=True,
    )
    accepted_output = None
    if accepted is not None:
        accepted_output = output_dir / "GEN249-omsim-product1.solution"
        accepted_output.write_bytes(Path(accepted["solutionPath"]).read_bytes())

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-collision-phase-neutralization-search",
        "targetSolutionBytesUsed": 0,
        "request": {"window": int(window)},
        "baselineOMSim": baseline_oracle,
        "physicalPhaseProgramIndices": {key: sorted(value) for key, value in physical.items()},
        "generatedVariantCount": len(variants),
        "searchedVariantCount": len(records),
        "acceptedProductOne": accepted is not None,
        "acceptedSolution": str(accepted_output) if accepted_output is not None else None,
        "acceptedOMSim": accepted.get("omsim") if accepted is not None else None,
        "topVariants": records[:60],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Neutralize or phase-move physical collision tape cells without changing the tape period.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window", type=int, default=10)
    args = parser.parse_args()
    report = search(
        omsim=args.omsim,
        puzzle_path=args.puzzle,
        baseline_path=args.baseline,
        output_dir=args.output_dir,
        window=args.window,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "physicalPhaseProgramIndices": report["physicalPhaseProgramIndices"],
        "generatedVariantCount": report["generatedVariantCount"],
        "searchedVariantCount": report["searchedVariantCount"],
        "acceptedProductOne": report["acceptedProductOne"],
        "acceptedOMSim": report["acceptedOMSim"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
