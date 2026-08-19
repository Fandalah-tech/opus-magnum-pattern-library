from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.opus_engine.builder import DIRECTIONS
from packages.opus_parser import parse_puzzle, parse_solution, write_solution, write_solution_bytes
from packages.opus_solver.additive_purification_search import search_additive_purification_stations
from packages.opus_solver.intermediate_convergence import search_intermediate_convergence
from packages.opus_solver.purification_chain import purification_profile

_COLLISION_RE = re.compile(r"collision during motion phase on cycle (\d+) at (-?\d+) (-?\d+)")


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _neighbors(position: tuple[int, int]) -> set[tuple[int, int]]:
    return {(position[0] + d[0], position[1] + d[1]) for d in DIRECTIONS}


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


def _absolute_track(part: dict[str, Any]) -> list[tuple[int, int]]:
    origin = _position(part.get("position"))
    return [(origin[0] + int(c[0]), origin[1] + int(c[1])) for c in part.get("trackHexes", []) or []]


def _track_detours(solution: dict[str, Any], collision: tuple[int, int]) -> list[dict[str, Any]]:
    all_cells = {
        cell for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "track"
        for cell in _absolute_track(part)
    }
    variants: list[dict[str, Any]] = []
    for part in solution.get("parts", []) or []:
        if str(part.get("type") or "") != "track":
            continue
        cells = _absolute_track(part)
        origin = _position(part.get("position"))
        for index, cell in enumerate(cells):
            if cell != collision or index <= 0 or index >= len(cells) - 1:
                continue
            previous, following = cells[index - 1], cells[index + 1]
            alternatives = sorted((_neighbors(previous) & _neighbors(following)) - {collision})
            for alternative in alternatives:
                if alternative in all_cells and alternative != collision:
                    continue
                candidate = deepcopy(solution)
                target = next(p for p in candidate.get("parts", []) or [] if str(p.get("id") or "") == str(part.get("id") or ""))
                target["trackHexes"][index] = [alternative[0] - origin[0], alternative[1] - origin[1]]
                candidate.setdefault("source", {})["generator"] = "opus_solver/mechanical-chemistry-loop-track-detour-v1"
                candidate["source"].setdefault("mechanicalChemistryLoop", []).append({
                    "stage": "track-detour",
                    "trackPartId": str(part.get("id") or ""),
                    "trackCellIndex": index,
                    "collisionCell": list(collision),
                    "replacementCell": list(alternative),
                    "targetSolutionBytesUsed": 0,
                })
                variants.append({
                    "solution": candidate,
                    "action": {
                        "kind": "track-detour",
                        "trackPartId": str(part.get("id") or ""),
                        "trackCellIndex": index,
                        "collisionCell": list(collision),
                        "replacementCell": list(alternative),
                    },
                })
    return variants


def _signature(solution: dict[str, Any]) -> str:
    # Binary serialization is canonical enough for generated physical states and
    # excludes transient in-memory ranking metadata.
    return hashlib.sha256(write_solution_bytes(solution)).hexdigest()


def _profile_score(profile: dict[str, Any]) -> tuple[int, int, int, int]:
    counts = profile.get("countsByElement") or {}
    return (
        int(profile.get("frontierIndex") if profile.get("frontierIndex") is not None else -1),
        int(counts.get("gold", 0)),
        int(counts.get("silver", 0)),
        int(profile.get("count") or 0),
    )


def _state_score(state: dict[str, Any]) -> tuple[Any, ...]:
    oracle = state.get("omsim") or {}
    profile = state.get("purificationProfile") or {}
    frontier, gold, silver, count = _profile_score(profile)
    return (
        int(oracle.get("exitCode") == 0),
        frontier,
        gold,
        silver,
        int(oracle.get("progressCycle") or 0),
        count,
    )


def _evaluate(
    omsim: Path,
    puzzle_path: Path,
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    path: Path,
    *,
    max_cycles: int,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    write_solution(solution, path)
    return {
        "solution": solution,
        "solutionPath": str(path),
        "omsim": _run_omsim(omsim, puzzle_path, path),
        "purificationProfile": purification_profile(puzzle, solution, max_cycles=max_cycles),
        "actions": deepcopy(actions),
    }


def _compact(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "solutionPath": state.get("solutionPath"),
        "omsim": state.get("omsim"),
        "purificationProfile": state.get("purificationProfile"),
        "actions": state.get("actions"),
    }


def search(
    omsim: Path,
    puzzle_path: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    max_cycles: int = 500,
    generations: int = 4,
    beam_width: int = 3,
    additive_result_limit: int = 16,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    puzzle = parse_puzzle(puzzle_path)
    baseline_solution = parse_solution(baseline_path)
    baseline = _evaluate(
        omsim,
        puzzle_path,
        puzzle,
        baseline_solution,
        output_dir / "generation-00-baseline.solution",
        max_cycles=max_cycles,
        actions=[],
    )
    beam = [baseline]
    history: list[dict[str, Any]] = []
    candidate_serial = 0

    for generation in range(1, max(1, int(generations)) + 1):
        mechanical_states: list[dict[str, Any]] = []
        for state in beam:
            mechanical_states.append(state)
            collision = (state.get("omsim") or {}).get("collisionLocation")
            if not collision:
                continue
            for detour in _track_detours(state["solution"], tuple(int(v) for v in collision)):
                candidate_serial += 1
                mechanical_states.append(_evaluate(
                    omsim, puzzle_path, puzzle, detour["solution"],
                    output_dir / f"generation-{generation:02d}-mechanical-{candidate_serial:04d}.solution",
                    max_cycles=max_cycles,
                    actions=[*state.get("actions", []), detour["action"]],
                ))

        # Retain mechanically useful diversity before the more expensive
        # chemistry search. Preserve the best chemistry state even if its
        # official collision is earlier, plus the best oracle-surviving states.
        mechanical_states.sort(key=_state_score, reverse=True)
        mechanical_states = mechanical_states[:max(beam_width * 2, 4)]

        expanded: list[dict[str, Any]] = list(mechanical_states)
        for state in mechanical_states:
            additive = search_additive_purification_stations(
                puzzle,
                state["solution"],
                max_cycles=max_cycles,
                opportunity_limit=180,
                result_limit=additive_result_limit,
            )
            base_profile_score = _profile_score(state["purificationProfile"])
            for variant in additive.get("variants", []) or []:
                variant_solution = variant.get("solution")
                variant_profile = variant.get("purificationProfile") or {}
                if not variant_solution or _profile_score(variant_profile) <= base_profile_score:
                    continue
                candidate_serial += 1
                action = {
                    "kind": "additive-purification",
                    "repairMode": variant.get("repairMode"),
                    "producedElement": (variant.get("opportunity") or {}).get("producedElement"),
                    "output": (variant.get("opportunity") or {}).get("output"),
                    "addedUnbonderCount": variant.get("addedUnbonderCount"),
                }
                expanded.append(_evaluate(
                    omsim, puzzle_path, puzzle, variant_solution,
                    output_dir / f"generation-{generation:02d}-chemistry-{candidate_serial:04d}.solution",
                    max_cycles=max_cycles,
                    actions=[*state.get("actions", []), action],
                ))

        # Once two free-silver-producing stages exist, explicitly try the
        # generic intermediate convergence synthesis that previously produced
        # the strict-blind gold milestone.
        convergence_parents = sorted(expanded, key=_state_score, reverse=True)[:max(beam_width * 2, 4)]
        for state in convergence_parents:
            counts = (state.get("purificationProfile") or {}).get("countsByElement") or {}
            if int(counts.get("silver", 0)) < 2 or int(counts.get("gold", 0)) > 0:
                continue
            convergence = search_intermediate_convergence(
                puzzle,
                state["solution"],
                element="silver",
                max_cycles=max_cycles,
                observation_limit=100,
                result_limit=12,
            )
            for variant in convergence.get("variants", []) or []:
                candidate = variant.get("solution")
                if not candidate:
                    continue
                candidate_serial += 1
                expanded.append(_evaluate(
                    omsim, puzzle_path, puzzle, candidate,
                    output_dir / f"generation-{generation:02d}-convergence-{candidate_serial:04d}.solution",
                    max_cycles=max_cycles,
                    actions=[*state.get("actions", []), {
                        "kind": "intermediate-convergence",
                        "element": "silver",
                        "destination": (variant.get("move") or {}).get("destination"),
                        "purifierOutput": (variant.get("purifierPose") or {}).get("output"),
                    }],
                ))

        deduped: dict[str, dict[str, Any]] = {}
        for state in expanded:
            key = _signature(state["solution"])
            previous = deduped.get(key)
            if previous is None or _state_score(state) > _state_score(previous):
                deduped[key] = state
        ordered = sorted(deduped.values(), key=_state_score, reverse=True)
        beam = ordered[:max(1, int(beam_width))]
        history.append({
            "generation": generation,
            "mechanicalCandidateCount": len(mechanical_states),
            "expandedCandidateCount": len(expanded),
            "dedupedCandidateCount": len(deduped),
            "beam": [_compact(state) for state in beam],
        })
        if beam and int((beam[0].get("omsim") or {}).get("exitCode") or 1) == 0:
            break

    best = max(beam, key=_state_score) if beam else baseline
    final_path = output_dir / "GEN249-best-mechanical-chemistry-loop.solution"
    write_solution(best["solution"], final_path)
    best["solutionPath"] = str(final_path)
    return {
        "schemaVersion": "0.1.0",
        "kind": "strict-heldout-mechanical-chemistry-loop",
        "targetSolutionBytesUsed": 0,
        "request": {
            "maxCycles": max_cycles,
            "generations": generations,
            "beamWidth": beam_width,
            "additiveResultLimit": additive_result_limit,
        },
        "baseline": _compact(baseline),
        "generationCount": len(history),
        "history": history,
        "best": _compact(best),
        "acceptedProductOne": int((best.get("omsim") or {}).get("exitCode") or 1) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Alternate target-free track repair and chemistry synthesis under OMSim.")
    parser.add_argument("--omsim", type=Path, required=True)
    parser.add_argument("--puzzle", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--generations", type=int, default=4)
    parser.add_argument("--beam-width", type=int, default=3)
    parser.add_argument("--additive-result-limit", type=int, default=16)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        max_cycles=args.max_cycles,
        generations=args.generations,
        beam_width=args.beam_width,
        additive_result_limit=args.additive_result_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "generationCount": report["generationCount"],
        "best": report["best"],
        "acceptedProductOne": report["acceptedProductOne"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
