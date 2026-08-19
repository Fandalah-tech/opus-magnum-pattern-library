from __future__ import annotations

import argparse
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_engine.builder import DIRECTIONS
from packages.opus_parser import parse_puzzle, parse_solution, write_solution
from packages.opus_solver.purification_chain import purification_profile

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")
_DIRECTION_SET = set(DIRECTIONS)


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _neighbors(position: tuple[int, int]) -> set[tuple[int, int]]:
    return {(position[0] + du, position[1] + dv) for du, dv in DIRECTIONS}


def _hex_distance(first: tuple[int, int], second: tuple[int, int]) -> int:
    du = first[0] - second[0]
    dv = first[1] - second[1]
    return max(abs(du), abs(dv), abs(du + dv))


def _absolute_track(part: dict[str, Any]) -> list[tuple[int, int]]:
    origin = _position(part.get("position"))
    return [
        (origin[0] + int(cell[0]), origin[1] + int(cell[1]))
        for cell in part.get("trackHexes", []) or []
    ]


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


def _candidate_detours(
    solution: dict[str, Any],
    collision: tuple[int, int],
    *,
    radius: int,
) -> list[dict[str, Any]]:
    all_cells = {
        cell
        for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "track"
        for cell in _absolute_track(part)
    }
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for part in solution.get("parts", []) or []:
        if str(part.get("type") or "") != "track":
            continue
        cells = _absolute_track(part)
        origin = _position(part.get("position"))
        for index in range(1, len(cells) - 1):
            current = cells[index]
            if _hex_distance(current, collision) > max(0, int(radius)):
                continue
            previous, following = cells[index - 1], cells[index + 1]
            alternatives = sorted((_neighbors(previous) & _neighbors(following)) - {current})
            for alternative in alternatives:
                if alternative in all_cells and alternative != current:
                    continue
                key = (str(part.get("id") or ""), index, alternative)
                if key in seen:
                    continue
                seen.add(key)
                candidate = deepcopy(solution)
                target = next(
                    item for item in candidate.get("parts", []) or []
                    if str(item.get("id") or "") == str(part.get("id") or "")
                )
                target["trackHexes"][index] = [
                    alternative[0] - origin[0],
                    alternative[1] - origin[1],
                ]
                candidate.setdefault("source", {})["generator"] = "opus_solver/track-neighborhood-detour-v1"
                candidate["source"]["trackNeighborhoodDetour"] = {
                    "trackPartId": str(part.get("id") or ""),
                    "trackCellIndex": index,
                    "authoritativeCollision": list(collision),
                    "oldTrackCell": list(current),
                    "replacementTrackCell": list(alternative),
                    "distanceFromCollision": _hex_distance(current, collision),
                    "targetSolutionBytesUsed": 0,
                }
                candidates.append({
                    "solution": candidate,
                    "trackPartId": str(part.get("id") or ""),
                    "trackCellIndex": index,
                    "oldTrackCell": list(current),
                    "replacementTrackCell": list(alternative),
                    "distanceFromCollision": _hex_distance(current, collision),
                })
    return candidates


def search(
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    max_cycles: int = 500,
    radius: int = 2,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    solution = parse_solution(baseline_path)
    baseline_oracle = _run_omsim(omsim, puzzle_path, baseline_path)
    baseline_profile = purification_profile(puzzle, solution, max_cycles=max_cycles)
    collision_raw = baseline_oracle.get("collisionLocation")
    if not collision_raw:
        return {
            "schemaVersion": "0.1.0",
            "kind": "strict-heldout-track-neighborhood-detour-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "baselinePurificationProfile": baseline_profile,
            "variantCount": 0,
            "best": None,
        }

    collision = tuple(int(v) for v in collision_raw)
    raw_candidates = _candidate_detours(solution, collision, radius=radius)
    baseline_counts = baseline_profile.get("countsByElement") or {}
    baseline_silver = int(baseline_counts.get("silver", 0))
    baseline_gold = int(baseline_counts.get("gold", 0))
    evaluated: list[dict[str, Any]] = []

    for index, item in enumerate(raw_candidates):
        candidate = item["solution"]
        profile = purification_profile(puzzle, candidate, max_cycles=max_cycles)
        counts = profile.get("countsByElement") or {}
        path = output_dir / f"candidate-{index:03d}.solution"
        write_solution(candidate, path)
        oracle = _run_omsim(omsim, puzzle_path, path)
        evaluated.append({
            key: value for key, value in item.items() if key != "solution"
        } | {
            "solutionPath": str(path),
            "purificationProfile": profile,
            "preservesSilver": int(counts.get("silver", 0)) >= baseline_silver,
            "preservesGold": int(counts.get("gold", 0)) >= baseline_gold,
            "omsim": oracle,
        })

    evaluated.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int(item.get("preservesGold", False)),
            int(item.get("preservesSilver", False)),
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int(((item.get("purificationProfile") or {}).get("countsByElement") or {}).get("silver", 0)),
            int((item.get("purificationProfile") or {}).get("count") or 0),
            -int(item.get("distanceFromCollision") or 0),
        ),
        reverse=True,
    )
    best = evaluated[0] if evaluated else None
    if best:
        final = parse_solution(best["solutionPath"])
        final_path = output_dir / "GEN249-best-track-neighborhood-detour.solution"
        write_solution(final, final_path)
        best["finalSolutionPath"] = str(final_path)

    nonregressing = [
        item for item in evaluated
        if item.get("preservesSilver") and item.get("preservesGold")
        and int((item.get("omsim") or {}).get("progressCycle") or 0) >= int(baseline_oracle.get("progressCycle") or 0)
    ]
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-track-neighborhood-detour-search",
        "targetSolutionBytesUsed": 0,
        "request": {"maxCycles": max_cycles, "radius": radius},
        "baselineOMSim": baseline_oracle,
        "baselinePurificationProfile": baseline_profile,
        "collisionLocation": list(collision),
        "rawCandidateCount": len(raw_candidates),
        "variantCount": len(evaluated),
        "chemistryPreservingNonregressingCount": len(nonregressing),
        "best": best,
        "topVariants": evaluated[:30],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reroute nearby track cells around an authoritative molecule collision.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--radius", type=int, default=2)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        max_cycles=args.max_cycles,
        radius=args.radius,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "collisionLocation": report.get("collisionLocation"),
        "rawCandidateCount": report.get("rawCandidateCount", 0),
        "variantCount": report["variantCount"],
        "chemistryPreservingNonregressingCount": report.get("chemistryPreservingNonregressingCount", 0),
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
