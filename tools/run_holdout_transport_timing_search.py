from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from itertools import combinations
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_puzzle, parse_solution, write_solution
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


def _transport_arms(solution: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for part in solution.get("parts", []) or []:
        program = list(part.get("program", []) or [])
        instructions = [str(item.get("instruction") or "") for item in program]
        if (
            (str(part.get("type") or "").startswith("arm") or str(part.get("type") or "") in {"piston", "baron"})
            and "grab" in instructions
            and ("track_plus" in instructions or "track_minus" in instructions)
            and "drop" in instructions
        ):
            result.append(part)
    return result


def _spacing_variants(part: dict[str, Any], *, max_period: int = 8) -> list[dict[str, Any]]:
    ordered = sorted(part.get("program", []) or [], key=lambda item: int(item.get("cycle") or 0))
    if len(ordered) != 3:
        return []
    instructions = [str(item.get("instruction") or "") for item in ordered]
    if instructions[0] != "grab" or instructions[-1] != "drop":
        return []
    if instructions[1] not in {"track_plus", "track_minus"}:
        return []

    variants = []
    # Keep grab at physical phase zero. Choose two later tape cells, yielding
    # deterministic idle gaps without puzzle-specific coordinates or timings.
    for motion_cycle, drop_cycle in combinations(range(1, max(3, int(max_period))), 2):
        program = deepcopy(ordered)
        program[0]["cycle"] = 0
        program[1]["cycle"] = motion_cycle
        program[2]["cycle"] = drop_cycle
        variants.append({
            "motionCycle": motion_cycle,
            "dropCycle": drop_cycle,
            "period": drop_cycle + 1,
            "program": program,
        })
    return variants


def search(
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    max_cycles: int = 500,
    max_period: int = 9,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_path)
    baseline_oracle = _run_omsim(omsim, puzzle_path, baseline_path)
    baseline_profile = purification_profile(puzzle, solution, max_cycles=max_cycles)
    transport_arms = _transport_arms(solution)

    evaluated: list[dict[str, Any]] = []
    for arm in transport_arms:
        arm_id = str(arm.get("id") or "")
        original_program = deepcopy(arm.get("program", []) or [])
        for variant in _spacing_variants(arm, max_period=max_period):
            candidate = deepcopy(solution)
            target = next(part for part in candidate.get("parts", []) or [] if str(part.get("id") or "") == arm_id)
            target["program"] = deepcopy(variant["program"])
            candidate.setdefault("source", {})["generator"] = "opus_solver/transport-tape-spacing-v1"
            candidate["source"]["transportTapeSpacingRepair"] = {
                "armPartId": arm_id,
                "oldProgram": original_program,
                "newProgram": deepcopy(variant["program"]),
                "targetSolutionBytesUsed": 0,
            }
            path = output_dir / f"candidate-{len(evaluated):03d}.solution"
            write_solution(candidate, path)
            oracle = _run_omsim(omsim, puzzle_path, path)
            profile = purification_profile(puzzle, candidate, max_cycles=max_cycles)
            evaluated.append({
                "armPartId": arm_id,
                "motionCycle": variant["motionCycle"],
                "dropCycle": variant["dropCycle"],
                "period": variant["period"],
                "solutionPath": str(path),
                "omsim": oracle,
                "purificationProfile": profile,
            })

    evaluated.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int(((item.get("purificationProfile") or {}).get("countsByElement") or {}).get("gold", 0)),
            int((item.get("purificationProfile") or {}).get("count") or 0),
        ),
        reverse=True,
    )
    best = evaluated[0] if evaluated else None
    if best:
        final = parse_solution(best["solutionPath"])
        final_path = output_dir / "GEN249-best-transport-timing.solution"
        write_solution(final, final_path)
        best["finalSolutionPath"] = str(final_path)

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-transport-timing-search",
        "targetSolutionBytesUsed": 0,
        "baselineOMSim": baseline_oracle,
        "baselinePurificationProfile": baseline_profile,
        "transportArmCount": len(transport_arms),
        "variantCount": len(evaluated),
        "best": best,
        "topVariants": evaluated[:30],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Search generic idle spacing in a transport arm tape against OMSim.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--max-period", type=int, default=9)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        max_cycles=args.max_cycles,
        max_period=args.max_period,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "transportArmCount": report["transportArmCount"],
        "variantCount": report["variantCount"],
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
