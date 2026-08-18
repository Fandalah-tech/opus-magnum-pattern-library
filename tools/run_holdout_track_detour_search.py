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


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _adjacent(first: tuple[int, int], second: tuple[int, int]) -> bool:
    delta = second[0] - first[0], second[1] - first[1]
    return delta in set(DIRECTIONS)


def _neighbors(position: tuple[int, int]) -> set[tuple[int, int]]:
    return {
        (position[0] + delta[0], position[1] + delta[1])
        for delta in DIRECTIONS
    }


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


def _absolute_track(part: dict[str, Any]) -> list[tuple[int, int]]:
    origin = _position(part.get("position"))
    return [
        (origin[0] + int(cell[0]), origin[1] + int(cell[1]))
        for cell in part.get("trackHexes", []) or []
    ]


def _track_detours(solution: dict[str, Any], collision: tuple[int, int]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    all_track_cells = {
        cell
        for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "track"
        for cell in _absolute_track(part)
    }
    for part in solution.get("parts", []) or []:
        if str(part.get("type") or "") != "track":
            continue
        cells = _absolute_track(part)
        origin = _position(part.get("position"))
        for index, cell in enumerate(cells):
            if cell != collision or index <= 0 or index >= len(cells) - 1:
                continue
            previous = cells[index - 1]
            following = cells[index + 1]
            alternatives = sorted(
                (_neighbors(previous) & _neighbors(following)) - {collision},
            )
            for alternative in alternatives:
                if alternative in all_track_cells and alternative != collision:
                    continue
                candidate = deepcopy(solution)
                target = next(
                    item for item in candidate.get("parts", []) or []
                    if str(item.get("id") or "") == str(part.get("id") or "")
                )
                target["trackHexes"][index] = [
                    alternative[0] - origin[0],
                    alternative[1] - origin[1],
                ]
                candidate.setdefault("source", {})["generator"] = "opus_solver/track-collision-detour-v1"
                candidate["source"]["trackCollisionDetour"] = {
                    "trackPartId": str(part.get("id") or ""),
                    "trackCellIndex": index,
                    "collisionCell": list(collision),
                    "previousCell": list(previous),
                    "nextCell": list(following),
                    "replacementCell": list(alternative),
                    "targetSolutionBytesUsed": 0,
                }
                variants.append({
                    "trackPartId": str(part.get("id") or ""),
                    "trackCellIndex": index,
                    "previousCell": list(previous),
                    "nextCell": list(following),
                    "replacementCell": list(alternative),
                    "solution": candidate,
                })
    return variants


def search(
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    max_cycles: int = 500,
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
            "kind": "strict-heldout-track-collision-detour-search",
            "targetSolutionBytesUsed": 0,
            "baselineOMSim": baseline_oracle,
            "variantCount": 0,
            "best": None,
        }
    collision = tuple(int(value) for value in collision_raw)
    raw_variants = _track_detours(solution, collision)
    evaluated: list[dict[str, Any]] = []
    for index, variant in enumerate(raw_variants):
        candidate = variant["solution"]
        path = output_dir / f"candidate-{index:03d}.solution"
        write_solution(candidate, path)
        oracle = _run_omsim(omsim, puzzle_path, path)
        profile = purification_profile(puzzle, candidate, max_cycles=max_cycles)
        evaluated.append({
            key: value for key, value in variant.items() if key != "solution"
        } | {
            "solutionPath": str(path),
            "omsim": oracle,
            "purificationProfile": profile,
        })

    baseline_frontier = int(baseline_profile.get("frontierIndex") if baseline_profile.get("frontierIndex") is not None else -1)
    evaluated.sort(
        key=lambda item: (
            int((item.get("omsim") or {}).get("exitCode") == 0),
            int((item.get("purificationProfile") or {}).get("frontierIndex") if (item.get("purificationProfile") or {}).get("frontierIndex") is not None else -1) >= baseline_frontier,
            int((item.get("omsim") or {}).get("progressCycle") or 0),
            int((item.get("purificationProfile") or {}).get("count") or 0),
        ),
        reverse=True,
    )
    best = evaluated[0] if evaluated else None
    if best:
        final = parse_solution(best["solutionPath"])
        final_path = output_dir / "GEN249-best-track-detour.solution"
        write_solution(final, final_path)
        best["finalSolutionPath"] = str(final_path)

    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-track-collision-detour-search",
        "targetSolutionBytesUsed": 0,
        "baselineOMSim": baseline_oracle,
        "baselinePurificationProfile": baseline_profile,
        "collisionLocation": list(collision),
        "variantCount": len(evaluated),
        "best": best,
        "variants": evaluated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reroute a track around an authoritative collision cell without target solution geometry.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        max_cycles=args.max_cycles,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "baselineOMSim": report["baselineOMSim"],
        "collisionLocation": report.get("collisionLocation"),
        "variantCount": report["variantCount"],
        "best": report["best"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
