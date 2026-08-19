from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
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


def _transport_arm(solution: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for part in solution.get("parts", []) or []:
        program = sorted(part.get("program", []) or [], key=lambda item: int(item.get("cycle") or 0))
        instructions = [str(item.get("instruction") or "") for item in program]
        if (
            len(program) >= 2
            and "grab" in instructions
            and "drop" in instructions
            and any(item in {"track_plus", "track_minus"} for item in instructions)
        ):
            candidates.append(part)
    return min(candidates, key=lambda part: len(part.get("program", []) or []), default=None)


def _short_period_events(part: dict[str, Any]) -> tuple[int, dict[int, dict[str, Any]]]:
    ordered = sorted(part.get("program", []) or [], key=lambda item: int(item.get("cycle") or 0))
    if not ordered:
        return 1, {}
    start = int(ordered[0].get("cycle") or 0)
    normalized = {
        int(item.get("cycle") or 0) - start: deepcopy(item)
        for item in ordered
    }
    period = max(normalized) + 1
    return period, normalized


def _unroll_with_delay(
    part: dict[str, Any],
    *,
    horizon: int,
    delay_cycle: int,
    delay_length: int,
) -> list[dict[str, Any]]:
    period, normalized = _short_period_events(part)
    result = []
    for physical_cycle in range(max(1, int(horizon))):
        template = normalized.get(physical_cycle % period)
        if template is None:
            continue
        emitted_cycle = physical_cycle if physical_cycle < int(delay_cycle) else physical_cycle + int(delay_length)
        if emitted_cycle >= horizon:
            continue
        item = deepcopy(template)
        item["cycle"] = emitted_cycle
        result.append(item)
    return result


def search(
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    horizon: int = 500,
    radius: int = 15,
    max_delay: int = 3,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_path)
    baseline_oracle = _run_omsim(omsim, puzzle_path, baseline_path)
    baseline_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    collision_cycle = baseline_oracle.get("collisionCycle")
    arm = _transport_arm(solution)
    if collision_cycle is None or arm is None:
        return {
            "schemaVersion": "0.1.0",
            "kind": "strict-heldout-one-time-transport-delay-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "baselinePurificationProfile": baseline_profile,
            "variantCount": 0,
            "best": None,
        }

    arm_id = str(arm.get("id") or "")
    original_program = deepcopy(arm.get("program", []) or [])
    start_delay = max(1, int(collision_cycle) - max(1, int(radius)))
    end_delay = int(collision_cycle) + 2
    evaluated: list[dict[str, Any]] = []

    for delay_cycle in range(start_delay, end_delay + 1):
        for delay_length in range(1, max(1, int(max_delay)) + 1):
            candidate = deepcopy(solution)
            target = next(part for part in candidate.get("parts", []) or [] if str(part.get("id") or "") == arm_id)
            target["program"] = _unroll_with_delay(
                arm,
                horizon=horizon,
                delay_cycle=delay_cycle,
                delay_length=delay_length,
            )
            candidate.setdefault("source", {})["generator"] = "opus_solver/one-time-transport-delay-v1"
            candidate["source"]["oneTimeTransportDelay"] = {
                "armPartId": arm_id,
                "originalProgram": original_program,
                "collisionCycleEvidence": int(collision_cycle),
                "delayCycle": delay_cycle,
                "delayLength": delay_length,
                "unrolledHorizon": int(horizon),
                "targetSolutionBytesUsed": 0,
            }
            path = output_dir / f"candidate-{len(evaluated):03d}.solution"
            write_solution(candidate, path)
            oracle = _run_omsim(omsim, puzzle_path, path)
            profile = purification_profile(puzzle, candidate, max_cycles=horizon)
            evaluated.append({
                "armPartId": arm_id,
                "delayCycle": delay_cycle,
                "delayLength": delay_length,
                "solutionPath": str(path),
                "omsim": oracle,
                "purificationProfile": profile,
            })

    baseline_frontier = int(baseline_profile.get("frontierIndex") if baseline_profile.get("frontierIndex") is not None else -1)
    baseline_count = int(baseline_profile.get("count") or 0)
    evaluated.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("purificationProfile") or {}).get("frontierIndex") if (item.get("purificationProfile") or {}).get("frontierIndex") is not None else -1) >= baseline_frontier,
            int((item.get("purificationProfile") or {}).get("count") or 0) >= baseline_count,
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int(((item.get("purificationProfile") or {}).get("countsByElement") or {}).get("gold", 0)),
            int((item.get("purificationProfile") or {}).get("count") or 0),
        ),
        reverse=True,
    )
    best = evaluated[0] if evaluated else None
    if best:
        final = parse_solution(best["solutionPath"])
        final_path = output_dir / "GEN249-best-one-time-delay.solution"
        write_solution(final, final_path)
        best["finalSolutionPath"] = str(final_path)

    preserving = [
        item for item in evaluated
        if int((item.get("purificationProfile") or {}).get("frontierIndex") if (item.get("purificationProfile") or {}).get("frontierIndex") is not None else -1) >= baseline_frontier
    ]
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-one-time-transport-delay-search",
        "targetSolutionBytesUsed": 0,
        "baselineOMSim": baseline_oracle,
        "baselinePurificationProfile": baseline_profile,
        "transportArmPartId": arm_id,
        "collisionCycleEvidence": int(collision_cycle),
        "delayWindow": [start_delay, end_delay],
        "variantCount": len(evaluated),
        "frontierPreservingVariantCount": len(preserving),
        "best": best,
        "topVariants": evaluated[:30],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Insert one-time idle slack near an OMSim collision without target solution evidence.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizon", type=int, default=500)
    parser.add_argument("--radius", type=int, default=15)
    parser.add_argument("--max-delay", type=int, default=3)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        horizon=args.horizon,
        radius=args.radius,
        max_delay=args.max_delay,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "collisionCycleEvidence": report.get("collisionCycleEvidence"),
        "variantCount": report["variantCount"],
        "frontierPreservingVariantCount": report.get("frontierPreservingVariantCount", 0),
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
