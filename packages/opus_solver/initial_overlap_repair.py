from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS

from .input_footprint_repair import replay_summary
from .purification_chain import purification_profile


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def initial_arm_base_overlaps(puzzle: dict[str, Any], solution: dict[str, Any]) -> list[dict[str, Any]]:
    """Find generated arm bases occupied by reagent atoms on the initial board."""

    simulator = Simulator.from_models(puzzle, solution)
    initial = simulator.frames[0] if simulator.frames else simulator.snapshot("initial")
    atoms_by_position = {
        _position(atom.get("position")): atom
        for atom in (initial.get("world") or {}).get("atoms", []) or []
    }
    overlaps = []
    for part in solution.get("parts", []) or []:
        part_type = str(part.get("type") or "")
        if part_type != "arm1":
            continue
        base = _position(part.get("position"))
        atom = atoms_by_position.get(base)
        if atom is None:
            continue
        direction = DIRECTIONS[int(part.get("rotation") or 0) % 6]
        length = max(1, int(part.get("length") or 1))
        tip = (base[0] + direction[0] * length, base[1] + direction[1] * length)
        overlaps.append({
            "armPartId": str(part.get("id") or ""),
            "armBase": [base[0], base[1]],
            "armRotation": int(part.get("rotation") or 0) % 6,
            "armLength": length,
            "preservedTip": [tip[0], tip[1]],
            "overlappingAtomId": str(atom.get("id") or ""),
            "overlappingElement": str(atom.get("element") or ""),
            "evidence": "generated-initial-reagent-arm-base-overlap",
        })
    return overlaps


def relocate_arm_base_preserving_tip(
    solution: dict[str, Any],
    *,
    arm_part_id: str,
    preserved_tip: tuple[int, int],
    new_rotation: int,
    new_length: int | None = None,
) -> dict[str, Any]:
    """Move an arm base while keeping its initial tip on the intended grab cell.

    Length is allowed to change because a one-hex arm can be geometrically
    impossible when its base lies inside the reagent footprint.  Longer regular
    arms are mechanically equivalent at the grab instant but rotate around a
    different legal pivot; replay decides whether the downstream chemistry is
    still useful.
    """

    result = deepcopy(solution)
    arm = next(
        part for part in result.get("parts", []) or []
        if str(part.get("id") or "") == str(arm_part_id)
    )
    old_length = max(1, int(arm.get("length") or 1))
    length = old_length if new_length is None else max(1, min(3, int(new_length)))
    rotation = int(new_rotation) % 6
    direction = DIRECTIONS[rotation]
    base = (
        int(preserved_tip[0]) - direction[0] * length,
        int(preserved_tip[1]) - direction[1] * length,
    )
    old_base = list(arm.get("position") or (0, 0))
    old_rotation = int(arm.get("rotation") or 0) % 6
    arm["position"] = [base[0], base[1]]
    arm["rotation"] = rotation
    arm["length"] = length
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/initial-arm-base-overlap-repair-v2"
    source.setdefault("initialArmBaseRepairs", []).append({
        "armPartId": str(arm_part_id),
        "oldBase": old_base,
        "oldRotation": old_rotation,
        "oldLength": old_length,
        "newBase": [base[0], base[1]],
        "newRotation": rotation,
        "newLength": length,
        "preservedTip": [int(preserved_tip[0]), int(preserved_tip[1])],
        "targetSolutionBytesUsed": 0,
    })
    return result


def _rank(record: dict[str, Any]) -> tuple[Any, ...]:
    profile = record.get("purificationProfile") or {}
    summary = record.get("summary") or {}
    return (
        int((profile.get("countsByElement") or {}).get("gold", 0)),
        int(profile.get("count") or 0),
        int(summary.get("productDeliveredCount") or 0),
        int(not bool(summary.get("terminatedWithError"))),
        int(summary.get("completedCycles") or 0),
        int(summary.get("chemistryEventCount") or 0),
    )


def search_initial_arm_base_repairs(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 500,
    beam_width: int = 6,
    max_arm_length: int = 3,
) -> dict[str, Any]:
    """Repair initial arm/reagent overlap while preserving each arm's grab tip.

    The generated mechanism's own reagent spawn and replay are the only search
    evidence.  For each overlapping arm1 we keep the original intended tip and
    enumerate legal pivots at regular-arm lengths 1..3.  This strictly
    generalizes the old same-length relocation: when every adjacent base lies
    inside a bulky reagent, a longer arm can keep the same grab cell while
    placing its base outside the reagent.  Candidates must preserve the
    baseline gold/purification frontier before entering the beam.
    """

    horizon = max(1, int(max_cycles))
    arm_length_limit = max(1, min(3, int(max_arm_length)))
    baseline_profile = purification_profile(puzzle, solution, max_cycles=horizon)
    baseline_summary_full = replay_summary(puzzle, solution, max_cycles=horizon)
    baseline_summary_full.pop("replay", None)
    required_gold = int((baseline_profile.get("countsByElement") or {}).get("gold", 0))
    required_purification = int(baseline_profile.get("count") or 0)

    beam = [{
        "solution": deepcopy(solution),
        "purificationProfile": baseline_profile,
        "summary": baseline_summary_full,
        "repairs": [],
    }]
    generations = []

    for generation_index in range(8):
        expanded: list[dict[str, Any]] = []
        any_overlap = False
        for state in beam:
            overlaps = initial_arm_base_overlaps(puzzle, state["solution"])
            if not overlaps:
                expanded.append(state)
                continue
            any_overlap = True
            target = overlaps[0]
            tip = tuple(int(value) for value in target.get("preservedTip") or (0, 0))

            simulator = Simulator.from_models(puzzle, state["solution"])
            initial = simulator.frames[0]
            initial_atom_cells = {
                _position(atom.get("position"))
                for atom in (initial.get("world") or {}).get("atoms", []) or []
            }
            other_part_bases = {
                _position(part.get("position"))
                for part in state["solution"].get("parts", []) or []
                if str(part.get("id") or "") != str(target.get("armPartId") or "")
                and str(part.get("type") or "") != "track"
            }

            old_rotation = int(target.get("armRotation") or 0) % 6
            old_length = max(1, int(target.get("armLength") or 1))
            for length in range(1, arm_length_limit + 1):
                for rotation in range(6):
                    if rotation == old_rotation and length == old_length:
                        continue
                    direction = DIRECTIONS[rotation]
                    base = (tip[0] - direction[0] * length, tip[1] - direction[1] * length)
                    if base in initial_atom_cells or base in other_part_bases:
                        continue
                    candidate = relocate_arm_base_preserving_tip(
                        state["solution"],
                        arm_part_id=str(target.get("armPartId") or ""),
                        preserved_tip=tip,
                        new_rotation=rotation,
                        new_length=length,
                    )
                    profile = purification_profile(puzzle, candidate, max_cycles=horizon)
                    if int((profile.get("countsByElement") or {}).get("gold", 0)) < required_gold:
                        continue
                    if int(profile.get("count") or 0) < required_purification:
                        continue
                    summary = replay_summary(puzzle, candidate, max_cycles=horizon)
                    summary.pop("replay", None)
                    expanded.append({
                        "solution": candidate,
                        "purificationProfile": profile,
                        "summary": summary,
                        "repairs": [
                            *state.get("repairs", []),
                            {
                                **target,
                                "newBase": [base[0], base[1]],
                                "newRotation": rotation,
                                "newLength": length,
                            },
                        ],
                    })

        deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for state in expanded:
            signature = tuple(
                (
                    str(part.get("id") or ""),
                    tuple(part.get("position") or (0, 0)),
                    int(part.get("rotation") or 0),
                    int(part.get("length") or 1),
                )
                for part in state["solution"].get("parts", []) or []
                if str(part.get("type") or "") == "arm1"
            )
            previous = deduped.get(signature)
            if previous is None or _rank(state) > _rank(previous):
                deduped[signature] = state
        beam = sorted(deduped.values(), key=_rank, reverse=True)[:max(1, int(beam_width))]
        generations.append({
            "generation": generation_index + 1,
            "candidateCount": len(expanded),
            "beamCount": len(beam),
            "remainingOverlapCount": min(
                (len(initial_arm_base_overlaps(puzzle, state["solution"])) for state in beam),
                default=0,
            ),
        })
        if not any_overlap or not beam:
            break
        if all(not initial_arm_base_overlaps(puzzle, state["solution"]) for state in beam):
            break

    clean = [state for state in beam if not initial_arm_base_overlaps(puzzle, state["solution"])]
    clean.sort(key=_rank, reverse=True)
    best = clean[0] if clean else None
    return {
        "schemaVersion": "0.2.0",
        "kind": "initial-arm-base-overlap-repair-search",
        "summary": {
            "maxCycles": horizon,
            "maxArmLength": arm_length_limit,
            "baselineOverlapCount": len(initial_arm_base_overlaps(puzzle, solution)),
            "cleanCandidateCount": len(clean),
            "bestRemainingOverlapCount": len(initial_arm_base_overlaps(puzzle, best["solution"])) if best else len(initial_arm_base_overlaps(puzzle, solution)),
            "baselinePurificationCount": required_purification,
            "bestPurificationCount": int((best or {}).get("purificationProfile", {}).get("count") or 0),
            "baselineGoldCount": required_gold,
            "bestGoldCount": int(((best or {}).get("purificationProfile", {}).get("countsByElement") or {}).get("gold", 0)),
            "targetSolutionBytesUsed": 0,
        },
        "baselineOverlaps": initial_arm_base_overlaps(puzzle, solution),
        "generations": generations,
        "candidates": clean,
        "best": best,
    }


__all__ = [
    "initial_arm_base_overlaps",
    "relocate_arm_base_preserving_tip",
    "search_initial_arm_base_repairs",
]
