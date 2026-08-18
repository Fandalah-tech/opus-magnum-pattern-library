from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS
from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.purification_chain import purification_profile

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


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


def _next_arm_number(solution: dict[str, Any]) -> int:
    return 1 + max(
        (
            int(part.get("armNumber") or 0)
            for part in solution.get("parts", []) or []
            if str(part.get("type") or "").startswith("arm")
            or str(part.get("type") or "") in {"piston", "baron"}
        ),
        default=0,
    )


def _purification_events_near_collision(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    collision_cycle: int,
    collision_location: tuple[int, int],
) -> list[dict[str, Any]]:
    horizon = max(1, int(collision_cycle) + 4)
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    records: list[dict[str, Any]] = []
    for frame in replay.get("frames", []) or []:
        for event in frame.get("events", []) or []:
            if str(event.get("kind") or "") != "atom-purified":
                continue
            position = _position(event.get("position"))
            event_cycle = int(event.get("cycle", frame.get("cycle", 0)) or 0)
            if position != collision_location:
                continue
            if abs(event_cycle - int(collision_cycle)) > 4:
                continue
            records.append({
                "cycle": event_cycle,
                "position": [position[0], position[1]],
                "element": str(event.get("element") or ""),
                "producedAtomId": str(event.get("producedAtomId") or ""),
                "glyphPartId": str(event.get("glyphPartId") or ""),
            })
    return records


def _add_evacuation_arm(
    solution: dict[str, Any],
    *,
    position: tuple[int, int],
    base_rotation: int,
    grab_cycle: int,
    motion_instruction: str,
) -> dict[str, Any]:
    result = deepcopy(solution)
    direction = DIRECTIONS[int(base_rotation) % 6]
    base = (position[0] - direction[0], position[1] - direction[1])
    existing = {str(part.get("id") or "") for part in result.get("parts", []) or []}
    serial = 0
    while f"reaction-evacuation-arm-{serial}" in existing:
        serial += 1
    part_id = f"reaction-evacuation-arm-{serial}"
    result.setdefault("parts", []).append({
        "id": part_id,
        "type": "arm1",
        "enabled": True,
        "position": [base[0], base[1]],
        "length": 1,
        "rotation": int(base_rotation) % 6,
        "which": 0,
        "armNumber": _next_arm_number(result),
        "program": [
            {"cycle": int(grab_cycle), "instruction": "grab"},
            {"cycle": int(grab_cycle) + 1, "instruction": str(motion_instruction)},
            {"cycle": int(grab_cycle) + 2, "instruction": "drop"},
        ],
    })
    result.setdefault("source", {})["generator"] = "opus_solver/reaction-output-evacuation-v1"
    result["source"].setdefault("reactionOutputEvacuations", []).append({
        "armPartId": part_id,
        "reactionOutputPosition": [position[0], position[1]],
        "basePosition": [base[0], base[1]],
        "baseRotation": int(base_rotation) % 6,
        "grabCycle": int(grab_cycle),
        "motionCycle": int(grab_cycle) + 1,
        "motionInstruction": str(motion_instruction),
        "targetSolutionBytesUsed": 0,
    })
    return result


def search(
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    timing_radius: int = 2,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_path)
    baseline_oracle = _run_omsim(omsim, puzzle_path, baseline_path)
    collision_cycle = baseline_oracle.get("collisionCycle")
    collision_location_raw = baseline_oracle.get("collisionLocation")
    if collision_cycle is None or not collision_location_raw:
        return {
            "schemaVersion": "0.1.0",
            "kind": "strict-heldout-reaction-output-evacuation-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "reactionEvents": [],
            "variantCount": 0,
            "best": None,
        }
    collision_location = tuple(int(value) for value in collision_location_raw)
    reaction_events = _purification_events_near_collision(
        puzzle,
        solution,
        collision_cycle=int(collision_cycle),
        collision_location=collision_location,
    )

    # If the local engine places the conversion a few cycles differently from
    # OMSim, still search around the authoritative collision cycle. The event
    # supplies semantic evidence that this hex is a conversion output; OMSim
    # remains the acceptance oracle for exact timing.
    anchor_cycles = {int(collision_cycle) - 1}
    for event in reaction_events:
        anchor_cycles.add(int(event.get("cycle") or 0))
    grab_cycles = sorted({
        max(0, anchor + delta)
        for anchor in anchor_cycles
        for delta in range(-max(0, int(timing_radius)), max(0, int(timing_radius)) + 1)
    })

    evaluated: list[dict[str, Any]] = []
    for grab_cycle in grab_cycles:
        for rotation in range(6):
            for instruction in ("rotate_cw", "rotate_ccw"):
                candidate = _add_evacuation_arm(
                    solution,
                    position=collision_location,
                    base_rotation=rotation,
                    grab_cycle=grab_cycle,
                    motion_instruction=instruction,
                )
                path = output_dir / f"candidate-{len(evaluated):03d}.solution"
                write_solution(candidate, path)
                oracle = _run_omsim(omsim, puzzle_path, path)
                evaluated.append({
                    "grabCycle": grab_cycle,
                    "baseRotation": rotation,
                    "motionInstruction": instruction,
                    "solutionPath": str(path),
                    "omsim": oracle,
                })

    evaluated.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
        ),
        reverse=True,
    )
    best = evaluated[0] if evaluated else None
    best_profile = None
    if best:
        best_solution = parse_solution(best["solutionPath"])
        best_profile = purification_profile(puzzle, best_solution, max_cycles=500)
        final_path = output_dir / "GEN249-best-reaction-output-evacuation.solution"
        write_solution(best_solution, final_path)
        best["finalSolutionPath"] = str(final_path)

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-reaction-output-evacuation-search",
        "targetSolutionBytesUsed": 0,
        "baselineOMSim": baseline_oracle,
        "collisionLocation": list(collision_location),
        "reactionEvents": reaction_events,
        "grabCycles": grab_cycles,
        "variantCount": len(evaluated),
        "best": best,
        "bestLocalPurificationProfile": best_profile,
        "topVariants": evaluated[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evacuate a locally observed reaction output blocking OMSim motion.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timing-radius", type=int, default=2)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        timing_radius=args.timing_radius,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "reactionEvents": report["reactionEvents"],
        "variantCount": report["variantCount"],
        "best": report["best"],
        "bestLocalPurificationProfile": report["bestLocalPurificationProfile"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
