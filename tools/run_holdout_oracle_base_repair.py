from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_engine.builder import DIRECTIONS
from packages.opus_parser import parse_solution, write_solution

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")


def run_omsim(omsim: Path, puzzle: Path, solution: Path) -> dict[str, Any]:
    process = subprocess.run(
        [str(omsim), "--puzzle-file", str(puzzle), "--metric", "product 1 cycles", str(solution)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (process.stdout or "") + (process.stderr or "")
    match = _COLLISION_RE.search(output)
    if process.returncode == 0:
        progress_cycle = 1_000_000_000
    elif match:
        progress_cycle = int(match.group(1))
    elif "cycle limit" in output.lower():
        progress_cycle = 999_999_999
    else:
        progress_cycle = 0
    return {
        "exitCode": int(process.returncode),
        "output": output.strip(),
        "progressCycle": progress_cycle,
        "collisionCycle": int(match.group(1)) if match else None,
        "collisionLocation": [int(match.group(2)), int(match.group(3))] if match else None,
    }


def variants_for_collision(solution: dict[str, Any], location: tuple[int, int]) -> list[dict[str, Any]]:
    matching = [
        part for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "arm1"
        and tuple(int(value) for value in (part.get("position") or (0, 0))) == location
    ]
    variants: list[dict[str, Any]] = []
    for arm in matching:
        arm_id = str(arm.get("id") or "")
        length = max(1, int(arm.get("length") or 1))
        old_rotation = int(arm.get("rotation") or 0) % 6
        old_direction = DIRECTIONS[old_rotation]
        tip = (location[0] + old_direction[0] * length, location[1] + old_direction[1] * length)

        removed = deepcopy(solution)
        removed["parts"] = [part for part in removed.get("parts", []) or [] if str(part.get("id") or "") != arm_id]
        variants.append({
            "mode": "remove-collision-base-arm",
            "armPartId": arm_id,
            "preservedTip": list(tip),
            "solution": removed,
        })

        for rotation in range(6):
            if rotation == old_rotation:
                continue
            direction = DIRECTIONS[rotation]
            new_base = (tip[0] - direction[0] * length, tip[1] - direction[1] * length)
            relocated = deepcopy(solution)
            target = next(part for part in relocated.get("parts", []) or [] if str(part.get("id") or "") == arm_id)
            target["position"] = [new_base[0], new_base[1]]
            target["rotation"] = rotation
            variants.append({
                "mode": "relocate-collision-base-arm",
                "armPartId": arm_id,
                "preservedTip": list(tip),
                "newBase": list(new_base),
                "newRotation": rotation,
                "solution": relocated,
            })
    return variants


def search(
    omsim: Path,
    puzzle: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    generations: int = 5,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    current = parse_solution(baseline_path)
    history: list[dict[str, Any]] = []
    accepted_path: str | None = None

    for generation in range(1, max(1, int(generations)) + 1):
        current_path = output_dir / f"generation-{generation:02d}-baseline.solution"
        write_solution(current, current_path)
        baseline = run_omsim(omsim, puzzle, current_path)
        entry: dict[str, Any] = {
            "generation": generation,
            "baselineSolution": str(current_path),
            "baseline": baseline,
            "targetSolutionBytesUsed": 0,
        }
        if baseline["exitCode"] == 0:
            accepted_path = str(current_path)
            entry["accepted"] = True
            history.append(entry)
            break
        collision_location = baseline.get("collisionLocation")
        if not collision_location:
            entry["accepted"] = False
            entry["stopReason"] = "no-motion-collision-location"
            history.append(entry)
            break

        candidates = variants_for_collision(current, tuple(collision_location))
        entry["matchingVariantCount"] = len(candidates)
        if not candidates:
            entry["accepted"] = False
            entry["stopReason"] = "no-arm-base-at-collision-location"
            history.append(entry)
            break

        evaluated: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            candidate_path = output_dir / f"generation-{generation:02d}-candidate-{index:02d}.solution"
            write_solution(candidate["solution"], candidate_path)
            oracle = run_omsim(omsim, puzzle, candidate_path)
            evaluated.append({
                key: value for key, value in candidate.items() if key != "solution"
            } | {
                "solutionPath": str(candidate_path),
                "omsim": oracle,
            })
        evaluated.sort(
            key=lambda item: (
                int((item.get("omsim") or {}).get("exitCode") == 0),
                int((item.get("omsim") or {}).get("progressCycle") or 0),
            ),
            reverse=True,
        )
        best = evaluated[0]
        entry["variants"] = evaluated
        entry["chosen"] = best
        entry["accepted"] = bool((best.get("omsim") or {}).get("exitCode") == 0)
        history.append(entry)
        current = parse_solution(best["solutionPath"])
        if entry["accepted"]:
            accepted_path = best["solutionPath"]
            break

    final_path = output_dir / "GEN249-best-oracle-base-repair.solution"
    write_solution(current, final_path)
    final_oracle = run_omsim(omsim, puzzle, final_path)
    if final_oracle["exitCode"] == 0:
        accepted_path = str(final_path)

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-omsim-collision-base-repair-search",
        "targetSolutionBytesUsed": 0,
        "requestedGenerations": max(1, int(generations)),
        "generationCount": len(history),
        "history": history,
        "finalSolution": str(final_path),
        "finalOMSim": final_oracle,
        "acceptedProductOne": final_oracle["exitCode"] == 0,
        "acceptedSolution": accepted_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Iterate OMSim collision locations into target-free arm-base repairs.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generations", type=int, default=5)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        generations=args.generations,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "generationCount": report["generationCount"],
        "finalOMSim": report["finalOMSim"],
        "acceptedProductOne": report["acceptedProductOne"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
