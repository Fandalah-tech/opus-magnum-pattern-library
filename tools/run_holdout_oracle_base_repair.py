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
from packages.opus_solver.input_footprint_repair import replay_summary
from packages.opus_solver.purification_chain import purification_profile

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


def variants_for_collision(
    solution: dict[str, Any],
    location: tuple[int, int],
    *,
    max_arm_length: int = 3,
) -> list[dict[str, Any]]:
    """Enumerate target-free replacements for an arm base at an oracle collision.

    Besides the historical same-length pivot relocation, keep the intended grab
    tip fixed while trying regular-arm lengths 1..3. Bulky reagents can occupy
    every adjacent pivot cell, making a length-one arm physically impossible;
    a longer arm can preserve the grab cell from a legal base. OMSim remains
    the authority for whether the changed pivot path is mechanically valid.
    """

    matching = [
        part for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "arm1"
        and tuple(int(value) for value in (part.get("position") or (0, 0))) == location
    ]
    variants: list[dict[str, Any]] = []
    length_limit = max(1, min(3, int(max_arm_length)))
    for arm in matching:
        arm_id = str(arm.get("id") or "")
        old_length = max(1, int(arm.get("length") or 1))
        old_rotation = int(arm.get("rotation") or 0) % 6
        old_direction = DIRECTIONS[old_rotation]
        tip = (
            location[0] + old_direction[0] * old_length,
            location[1] + old_direction[1] * old_length,
        )

        removed = deepcopy(solution)
        removed["parts"] = [
            part for part in removed.get("parts", []) or []
            if str(part.get("id") or "") != arm_id
        ]
        variants.append({
            "mode": "remove-collision-base-arm",
            "armPartId": arm_id,
            "oldLength": old_length,
            "preservedTip": list(tip),
            "solution": removed,
        })

        for length in range(1, length_limit + 1):
            for rotation in range(6):
                if rotation == old_rotation and length == old_length:
                    continue
                direction = DIRECTIONS[rotation]
                new_base = (
                    tip[0] - direction[0] * length,
                    tip[1] - direction[1] * length,
                )
                relocated = deepcopy(solution)
                target = next(
                    part for part in relocated.get("parts", []) or []
                    if str(part.get("id") or "") == arm_id
                )
                target["position"] = [new_base[0], new_base[1]]
                target["rotation"] = rotation
                target["length"] = length
                variants.append({
                    "mode": "relocate-collision-base-arm",
                    "armPartId": arm_id,
                    "oldLength": old_length,
                    "preservedTip": list(tip),
                    "newBase": list(new_base),
                    "newRotation": rotation,
                    "newLength": length,
                    "solution": relocated,
                })
    return variants


def _profile_counts(profile: dict[str, Any]) -> tuple[int, int]:
    counts = profile.get("countsByElement") or {}
    return int(counts.get("gold", 0)), int(profile.get("count") or 0)


def _chemistry_contract(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the minimum chemistry frontier that a mechanical repair must keep.

    Once gold has actually been produced, that event proves the complete
    iron->copper->silver->gold chain needed for a first-product proof. Extra
    lower-metal purifications produced later are useful but not prerequisites,
    so requiring their exact count can reject mechanically superior repairs.
    Before gold exists, retain the older total-purification/frontier contract.
    """

    counts = profile.get("countsByElement") or {}
    gold = int(counts.get("gold", 0))
    frontier_index = int(profile.get("frontierIndex") if profile.get("frontierIndex") is not None else -1)
    if gold > 0:
        return {
            "mode": "gold-frontier",
            "requiredGoldCount": gold,
            "requiredFrontierIndex": frontier_index,
            "requiredPurificationCount": None,
        }
    return {
        "mode": "pre-gold-frontier",
        "requiredGoldCount": 0,
        "requiredFrontierIndex": frontier_index,
        "requiredPurificationCount": int(profile.get("count") or 0),
    }


def _chemistry_preserved(profile: dict[str, Any], contract: dict[str, Any]) -> bool:
    counts = profile.get("countsByElement") or {}
    if int(counts.get("gold", 0)) < int(contract.get("requiredGoldCount") or 0):
        return False
    frontier_index = int(profile.get("frontierIndex") if profile.get("frontierIndex") is not None else -1)
    if frontier_index < int(contract.get("requiredFrontierIndex") if contract.get("requiredFrontierIndex") is not None else -1):
        return False
    required_purification = contract.get("requiredPurificationCount")
    if required_purification is not None and int(profile.get("count") or 0) < int(required_purification):
        return False
    return True


def _physical_signature(solution: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (
            str(part.get("id") or ""),
            str(part.get("type") or ""),
            tuple(int(value) for value in (part.get("position") or (0, 0))),
            int(part.get("rotation") or 0) % 6,
            int(part.get("length") or 1),
        )
        for part in solution.get("parts", []) or []
    )


def _choose_variant(
    evaluated: list[dict[str, Any]],
    baseline_progress: int,
) -> tuple[dict[str, Any] | None, str]:
    accepted = [
        item for item in evaluated
        if int((item.get("omsim") or {}).get("exitCode") or 0) == 0
    ]
    if accepted:
        accepted.sort(
            key=lambda item: int((item.get("omsim") or {}).get("progressCycle") or 0),
            reverse=True,
        )
        return accepted[0], "accepted-product"

    advancing = [
        item for item in evaluated
        if bool(item.get("chemistryPreserved"))
        and not bool(item.get("visitedState"))
        and int((item.get("omsim") or {}).get("progressCycle") or 0) > int(baseline_progress)
    ]
    if advancing:
        advancing.sort(
            key=lambda item: (
                int((item.get("omsim") or {}).get("progressCycle") or 0),
                int((item.get("purificationProfile") or {}).get("count") or 0),
                int(item.get("newLength") or 1),
            ),
            reverse=True,
        )
        return advancing[0], "chemistry-frontier-preserving-oracle-advance"

    return None, "no-unvisited-chemistry-preserving-oracle-advance"


def search(
    omsim: Path,
    puzzle: Path,
    baseline_path: Path,
    output_dir: Path,
    *,
    generations: int = 5,
    max_arm_length: int = 3,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    current = parse_solution(baseline_path)
    puzzle_model = parse_puzzle(puzzle)
    history: list[dict[str, Any]] = []
    accepted_path: str | None = None
    visited_signatures: set[tuple[Any, ...]] = {_physical_signature(current)}

    for generation in range(1, max(1, int(generations)) + 1):
        current_path = output_dir / f"generation-{generation:02d}-baseline.solution"
        write_solution(current, current_path)
        baseline = run_omsim(omsim, puzzle, current_path)
        baseline_profile = purification_profile(puzzle_model, current, max_cycles=500)
        contract = _chemistry_contract(baseline_profile)
        entry: dict[str, Any] = {
            "generation": generation,
            "baselineSolution": str(current_path),
            "baseline": baseline,
            "baselinePurificationProfile": baseline_profile,
            "chemistryContract": contract,
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

        candidates = variants_for_collision(
            current,
            tuple(collision_location),
            max_arm_length=max_arm_length,
        )
        entry["matchingVariantCount"] = len(candidates)
        if not candidates:
            entry["accepted"] = False
            entry["stopReason"] = "no-arm-base-at-collision-location"
            history.append(entry)
            break

        evaluated: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            signature = _physical_signature(candidate["solution"])
            candidate_path = output_dir / f"generation-{generation:02d}-candidate-{index:02d}.solution"
            write_solution(candidate["solution"], candidate_path)
            oracle = run_omsim(omsim, puzzle, candidate_path)
            profile = purification_profile(puzzle_model, candidate["solution"], max_cycles=500)
            chemistry_preserved = _chemistry_preserved(profile, contract)
            evaluated.append({
                key: value for key, value in candidate.items() if key != "solution"
            } | {
                "solutionPath": str(candidate_path),
                "omsim": oracle,
                "purificationProfile": profile,
                "chemistryPreserved": chemistry_preserved,
                "visitedState": signature in visited_signatures,
                "physicalSignature": [list(value) if isinstance(value, tuple) else value for value in signature],
            })
        evaluated.sort(
            key=lambda item: (
                int((item.get("omsim") or {}).get("exitCode") == 0),
                int(bool(item.get("chemistryPreserved"))),
                int(not bool(item.get("visitedState"))),
                int((item.get("omsim") or {}).get("progressCycle") or 0),
                int((item.get("purificationProfile") or {}).get("count") or 0),
            ),
            reverse=True,
        )
        best, choice_reason = _choose_variant(
            evaluated,
            int(baseline.get("progressCycle") or 0),
        )
        entry["variants"] = evaluated
        entry["chemistryPreservingVariantCount"] = sum(
            bool(item.get("chemistryPreserved")) for item in evaluated
        )
        entry["unvisitedChemistryPreservingVariantCount"] = sum(
            bool(item.get("chemistryPreserved")) and not bool(item.get("visitedState"))
            for item in evaluated
        )
        entry["choiceReason"] = choice_reason
        if best is None:
            entry["accepted"] = False
            entry["stopReason"] = choice_reason
            history.append(entry)
            break

        entry["chosen"] = best
        entry["accepted"] = bool((best.get("omsim") or {}).get("exitCode") == 0)
        history.append(entry)
        current = parse_solution(best["solutionPath"])
        visited_signatures.add(_physical_signature(current))
        if entry["accepted"]:
            accepted_path = best["solutionPath"]
            break

    final_path = output_dir / "GEN249-best-oracle-base-repair.solution"
    write_solution(current, final_path)
    final_oracle = run_omsim(omsim, puzzle, final_path)
    if final_oracle["exitCode"] == 0:
        accepted_path = str(final_path)

    local_profile = purification_profile(puzzle_model, current, max_cycles=500)
    local_full = replay_summary(puzzle_model, current, max_cycles=500)
    local_full.pop("replay", None)

    return {
        "schemaVersion": "0.5.0",
        "kind": "strict-heldout-omsim-collision-base-repair-search",
        "targetSolutionBytesUsed": 0,
        "requestedGenerations": max(1, int(generations)),
        "maxArmLength": max(1, min(3, int(max_arm_length))),
        "generationCount": len(history),
        "visitedStateCount": len(visited_signatures),
        "history": history,
        "finalSolution": str(final_path),
        "finalOMSim": final_oracle,
        "localPurificationProfile": local_profile,
        "localReplaySummary": local_full,
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
    parser.add_argument("--max-arm-length", type=int, default=3)
    args = parser.parse_args()

    report = search(
        args.omsim,
        args.puzzle,
        args.baseline,
        args.output_dir,
        generations=args.generations,
        max_arm_length=args.max_arm_length,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "generationCount": report["generationCount"],
        "visitedStateCount": report["visitedStateCount"],
        "finalOMSim": report["finalOMSim"],
        "localPurificationProfile": report["localPurificationProfile"],
        "acceptedProductOne": report["acceptedProductOne"],
        "targetSolutionBytesUsed": 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
