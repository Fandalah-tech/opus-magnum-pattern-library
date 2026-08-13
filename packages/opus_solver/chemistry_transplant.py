from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Callable

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS, build_input_sources, rotate_hex

from .candidate_solution import serialize_candidate_roundtrip
from .component_timing import oracle_outcome
from .solver import validate_generated_solution


PROGRAMMABLE_ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}
TRANSPLANTED_PART_TYPES = {"input", "unbonder", "glyph-duplication", "bonder-prisma"}
INERT_REPLAY_PART_TYPES = TRANSPLANTED_PART_TYPES | {
    "bonder",
    "glyph-calcification",
    "out-std",
}
BOND_PROGRESS_EVENTS = {
    "bond-created",
    "floating-bond-created",
    "floating-bond-settled",
}
OracleValidator = Callable[[dict[str, Any]], dict[str, Any]]
Hex = tuple[int, int]


def _add_hex(first: Hex, second: Hex) -> Hex:
    return first[0] + second[0], first[1] + second[1]


def _subtract_hex(first: Hex, second: Hex) -> Hex:
    return first[0] - second[0], first[1] - second[1]


def _direction(first: Hex, second: Hex) -> int:
    delta = _subtract_hex(second, first)
    if delta not in DIRECTIONS:
        raise ValueError(f"Positions are not adjacent: {first}, {second}")
    return DIRECTIONS.index(delta)


def mechanical_fingerprint(solution: dict[str, Any]) -> str:
    """Hash the arm programs and track geometry that a transplant must freeze."""
    parts = [
        deepcopy(part)
        for part in solution.get("parts", [])
        if str(part.get("type") or "") in PROGRAMMABLE_ARM_TYPES | {"track"}
    ]
    parts.sort(key=lambda part: (str(part.get("type") or ""), str(part.get("id") or "")))
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def _mechanical_family_fingerprint(solution: dict[str, Any]) -> str:
    """Group equal mechanisms while ignoring the timing values being repaired."""
    parts = []
    for part in solution.get("parts", []):
        part_type = str(part.get("type") or "")
        if part_type not in PROGRAMMABLE_ARM_TYPES | {"track"}:
            continue
        item = {
            key: deepcopy(value)
            for key, value in part.items()
            if key != "program"
        }
        if part_type in PROGRAMMABLE_ARM_TYPES:
            item["programInstructions"] = [
                str(instruction.get("instruction") or "")
                for instruction in part.get("program", [])
            ]
        parts.append(item)
    parts.sort(key=lambda part: (str(part.get("type") or ""), str(part.get("id") or "")))
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def arm_grab_sites(
    solution: dict[str, Any],
    *,
    max_cycles: int = 256,
) -> list[dict[str, Any]]:
    """Replay a molecule-free mechanism and return its distinct grab-tip cells."""
    replay_solution = deepcopy(solution)
    replay_solution["parts"] = [
        part
        for part in replay_solution.get("parts", [])
        if str(part.get("type") or "") not in INERT_REPLAY_PART_TYPES
    ]
    timeline = build_program_timeline(
        replay_solution,
        max_cycles=max(1, int(max_cycles)),
    )
    replay = Simulator.from_models({}, replay_solution).run_timeline(timeline)
    frames_by_cycle = {
        int(frame.get("cycle") or 0): frame
        for frame in replay.get("frames", [])
    }
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int, Hex]] = set()
    for row in timeline.get("cycles", []):
        cycle = int(row.get("cycle") or 0)
        frame = frames_by_cycle.get(cycle)
        if frame is None:
            continue
        arms = {
            str(arm.get("partId") or ""): arm
            for arm in frame.get("arms", [])
        }
        for event in row.get("events", []):
            if str(event.get("instruction") or "") != "grab":
                continue
            part_id = str(event.get("partId") or "")
            arm = arms.get(part_id)
            if arm is None:
                continue
            for tip in arm.get("tips", []):
                branch_index = int(tip.get("branchIndex") or 0)
                position = tuple(tip.get("position") or (0, 0))
                key = (part_id, branch_index, position)
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "cycle": cycle,
                    "partId": part_id,
                    "branchIndex": branch_index,
                    "position": list(position),
                })
    return result


def _prism_poses(first: Hex, second: Hex) -> list[dict[str, Any]]:
    target = {first, second}
    poses: dict[str, dict[str, Any]] = {}
    for q in range(min(first[0], second[0]) - 1, max(first[0], second[0]) + 2):
        for r in range(min(first[1], second[1]) - 1, max(first[1], second[1]) + 2):
            for rotation in range(6):
                origin = (q, r)
                cells = [
                    _add_hex(origin, rotate_hex(cell, rotation))
                    for cell in ((0, 0), (1, 0), (0, 1))
                ]
                for left, right, channel in (
                    (0, 1, "black"),
                    (1, 2, "red"),
                    (2, 0, "yellow"),
                ):
                    if {cells[left], cells[right]} == target:
                        poses.setdefault(channel, {
                            "position": list(origin),
                            "rotation": rotation,
                            "channel": channel,
                        })
    return [poses[channel] for channel in ("black", "red", "yellow") if channel in poses]


def prism_poses_for_pair(first: Hex, second: Hex) -> list[dict[str, Any]]:
    """Return deterministic prism poses exposing each channel to an adjacent pair."""
    return _prism_poses(first, second)


def _set_part_pose(
    solution: dict[str, Any],
    *,
    part_type: str,
    position: Hex,
    rotation: int,
) -> None:
    part = next(
        (
            item
            for item in solution.get("parts", [])
            if str(item.get("type") or "") == part_type
        ),
        None,
    )
    if part is None:
        raise ValueError(f"Missing transplant part: {part_type}")
    part["position"] = list(position)
    part["rotation"] = int(rotation) % 6


def _normal_duplication_pairs(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
) -> list[tuple[Hex, Hex]]:
    pairs: list[tuple[Hex, Hex]] = []
    for source in build_input_sources(puzzle, solution):
        positions = [position for _, position in source.atom_templates]
        elements = [element for element, _ in source.atom_templates]
        for first_index, second_index, kind in source.bond_templates:
            if kind != "normal":
                continue
            first_element = elements[first_index]
            second_element = elements[second_index]
            if {first_element, second_element} == {"salt"}:
                continue
            if first_element == "salt" and second_element != "salt":
                pairs.append((positions[second_index], positions[first_index]))
            elif second_element == "salt" and first_element != "salt":
                pairs.append((positions[first_index], positions[second_index]))
    return pairs


def _transplant_part_ids(solution: dict[str, Any]) -> dict[str, str] | None:
    ids: dict[str, str] = {}
    for part_type in TRANSPLANTED_PART_TYPES:
        part = next(
            (
                item
                for item in solution.get("parts", [])
                if str(item.get("type") or "") == part_type
            ),
            None,
        )
        if part is None:
            return None
        ids[part_type] = str(part.get("id") or "")
    return ids


def enumerate_chemistry_transplants(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_grab_cycles: int = 256,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Move input and required glyphs onto observed grab cells, freezing mechanics."""
    part_ids = _transplant_part_ids(solution)
    if part_ids is None or not puzzle.get("reagents"):
        return []
    input_part = next(
        part
        for part in solution.get("parts", [])
        if str(part.get("id") or "") == part_ids["input"]
    )
    reagent_index = int(input_part.get("which") or 0)
    reagents = puzzle.get("reagents", [])
    if reagent_index < 0 or reagent_index >= len(reagents):
        return []
    reagent_atoms = reagents[reagent_index].get("atoms", [])
    if not reagent_atoms:
        return []

    before = mechanical_fingerprint(solution)
    variants: list[dict[str, Any]] = []
    seen_inputs: set[tuple[Hex, int]] = set()
    for grab_site in arm_grab_sites(solution, max_cycles=max_grab_cycles):
        tip = tuple(grab_site["position"])
        for rotation in range(6):
            for atom_index, atom in enumerate(reagent_atoms):
                local_position = rotate_hex(
                    tuple(atom.get("position") or (0, 0)),
                    rotation,
                )
                input_position = _subtract_hex(tip, local_position)
                input_signature = (input_position, rotation)
                if input_signature in seen_inputs:
                    continue
                seen_inputs.add(input_signature)

                placed_input = deepcopy(solution)
                _set_part_pose(
                    placed_input,
                    part_type="input",
                    position=input_position,
                    rotation=rotation,
                )
                for classical, salt in _normal_duplication_pairs(puzzle, placed_input):
                    pair_rotation = _direction(classical, salt)
                    prism_poses = _prism_poses(classical, salt)
                    for prism_pose in prism_poses:
                        variant = deepcopy(placed_input)
                        _set_part_pose(
                            variant,
                            part_type="unbonder",
                            position=classical,
                            rotation=pair_rotation,
                        )
                        _set_part_pose(
                            variant,
                            part_type="glyph-duplication",
                            position=classical,
                            rotation=pair_rotation,
                        )
                        _set_part_pose(
                            variant,
                            part_type="bonder-prisma",
                            position=tuple(prism_pose["position"]),
                            rotation=int(prism_pose["rotation"]),
                        )
                        after = mechanical_fingerprint(variant)
                        if after != before:
                            raise AssertionError("Chemistry transplant changed the frozen mechanism")
                        variants.append({
                            "solution": variant,
                            "placement": {
                                "inputPartId": part_ids["input"],
                                "inputPosition": list(input_position),
                                "inputRotation": rotation,
                                "anchoredAtomIndex": atom_index,
                                "grabSite": grab_site,
                                "classicalPosition": list(classical),
                                "saltPosition": list(salt),
                                "prismChannel": prism_pose["channel"],
                                "prismPosition": prism_pose["position"],
                                "prismRotation": prism_pose["rotation"],
                            },
                            "mechanicalFingerprint": before,
                            "mechanicsPreserved": True,
                        })
                        if limit > 0 and len(variants) >= int(limit):
                            return variants
    return variants


def transplant_operation_coverage(validation: dict[str, Any]) -> list[str]:
    counts = validation.get("eventCounts") or {}
    coverage = []
    if int(counts.get("bond-removed") or 0) > 0:
        coverage.append("unbond")
    if int(counts.get("atom-duplicated") or 0) > 0:
        coverage.append("duplicate")
    if any(int(counts.get(kind) or 0) > 0 for kind in BOND_PROGRESS_EVENTS):
        coverage.append("bond")
    return coverage


def _local_rank(record: dict[str, Any]) -> tuple[Any, ...]:
    validation = record.get("validation") or {}
    counts = validation.get("eventCounts") or {}
    return (
        int(not validation.get("terminatedWithError")),
        int(int(counts.get("atom-grabbed") or 0) > 0),
        len(record.get("operationCoverage") or []),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(counts.get("input-spawned") or 0),
        int(validation.get("manipulationEventCount") or 0),
        int(validation.get("completedCycles") or 0),
    )


def _oracle_rank(record: dict[str, Any]) -> tuple[Any, ...]:
    outcome_rank = {
        "complete": 5,
        "cycle-limit": 4,
        "collision": 3,
        "track-error": 2,
        "instruction-conflict": 1,
        "other": 0,
    }
    return (
        outcome_rank.get(str(record.get("oracleOutcome") or "other"), 0),
        *_local_rank(record),
    )


def _select_mechanical_parents(
    sources: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    limit = max(0, int(limit))
    if limit == 0:
        return []
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source_index, source in enumerate(sources):
        solution = source.get("solution")
        if not solution:
            continue
        outcome = str(source.get("oracleOutcome") or "")
        if outcome not in {"complete", "cycle-limit"} and not (
            source.get("oracleValidation") or {}
        ).get("valid"):
            continue
        if source.get("candidateRank") is not None:
            family = (
                "source",
                int(source.get("candidateRank") or 0),
                source.get("sourceVariantIndex"),
            )
        else:
            family = ("mechanism", _mechanical_family_fingerprint(solution))
        if family in seen:
            continue
        seen.add(family)
        selected.append({**source, "_sourceIndex": source_index, "_family": family})
        if len(selected) >= limit:
            break
    return selected


def search_chemistry_transplant_candidates(
    puzzle: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    source_limit: int = 4,
    variant_limit: int = 1500,
    result_limit: int = 20,
    max_grab_cycles: int = 256,
    local_cycles: int = 160,
    oracle_promotion_limit: int = 120,
    oracle_validator: OracleValidator | None = None,
    oracle_workers: int = 1,
) -> dict[str, Any]:
    """Transplant target chemistry onto oracle-stable mechanical parents."""
    parents = _select_mechanical_parents(sources, limit=source_limit)
    records: list[dict[str, Any]] = []
    remaining = max(0, int(variant_limit))
    for parent in parents:
        if remaining == 0:
            break
        variants = enumerate_chemistry_transplants(
            puzzle,
            parent["solution"],
            max_grab_cycles=max_grab_cycles,
            limit=remaining,
        )
        for variant in variants:
            record: dict[str, Any] = {
                "variantIndex": len(records),
                "sourceIndex": int(parent.get("_sourceIndex") or 0),
                "sourceCandidateRank": parent.get("candidateRank"),
                "sourceVariantIndex": parent.get("sourceVariantIndex"),
                "sourceProgramEdit": parent.get("programEdit"),
                "sourceOracleOutcome": parent.get("oracleOutcome"),
                "placement": variant["placement"],
                "mechanicalFingerprint": variant["mechanicalFingerprint"],
                "mechanicsPreserved": variant["mechanicsPreserved"],
                "solution": variant["solution"],
            }
            try:
                roundtrip = serialize_candidate_roundtrip(variant["solution"])
                validation = validate_generated_solution(
                    puzzle,
                    roundtrip["parsed"],
                    max_cycles=max(1, int(local_cycles)),
                )
                record["serialization"] = roundtrip["diagnostics"]
                record["validation"] = validation
                record["validationScope"] = "bounded-local"
                record["operationCoverage"] = transplant_operation_coverage(validation)
            except Exception as exc:
                record["failureMode"] = "generation-error"
                record["generationError"] = {
                    "errorType": type(exc).__name__,
                    "message": str(exc),
                }
                record["validation"] = {
                    "terminatedWithError": True,
                    "completedCycles": 0,
                    "eventCounts": {},
                }
                record["operationCoverage"] = []
            records.append(record)
        remaining = max(0, int(variant_limit) - len(records))

    promoted = sorted(records, key=_local_rank, reverse=True)[
        :max(0, int(oracle_promotion_limit))
    ]
    oracle_outcomes: Counter[str] = Counter()
    if oracle_validator is not None and promoted:
        def validate_with_oracle(record: dict[str, Any]) -> dict[str, Any]:
            try:
                return oracle_validator(record["solution"])
            except Exception as exc:
                return {
                    "valid": False,
                    "rawOutput": f"oracle validation error: {type(exc).__name__}: {exc}",
                    "issues": [{"cycle": None, "message": str(exc)}],
                }

        with ThreadPoolExecutor(max_workers=max(1, min(10, int(oracle_workers)))) as executor:
            validations = list(executor.map(validate_with_oracle, promoted))
        for record, oracle_validation in zip(promoted, validations):
            record["oracleValidation"] = oracle_validation
            record["oracleOutcome"] = oracle_outcome(oracle_validation)
            oracle_outcomes[record["oracleOutcome"]] += 1

    ranked = sorted(
        promoted if oracle_validator is not None else records,
        key=_oracle_rank if oracle_validator is not None else _local_rank,
        reverse=True,
    )
    selected = ranked[:max(0, int(result_limit))]
    stable_active_count = sum(
        str(record.get("oracleOutcome") or "") in {"complete", "cycle-limit"}
        and int((record.get("validation") or {}).get("eventCounts", {}).get("atom-grabbed") or 0) > 0
        and len(record.get("operationCoverage") or []) == 3
        for record in promoted
    )
    local_active_count = sum(
        int((record.get("validation") or {}).get("eventCounts", {}).get("atom-grabbed") or 0) > 0
        and len(record.get("operationCoverage") or []) == 3
        for record in records
    )
    error_free_count = sum(
        not (record.get("validation") or {}).get("terminatedWithError")
        for record in records
    )

    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "selectedMechanicalParentCount": len(parents),
            "selectedMechanicalParents": [
                {
                    "sourceCandidateRank": parent.get("candidateRank"),
                    "sourceVariantIndex": parent.get("sourceVariantIndex"),
                    "sourceOracleOutcome": parent.get("oracleOutcome"),
                }
                for parent in parents
            ],
            "searchedVariantCount": len(records),
            "returnedVariantCount": len(selected),
            "localErrorFreeVariantCount": error_free_count,
            "localActiveFullOperationVariantCount": local_active_count,
            "oraclePromotedVariantCount": len(promoted) if oracle_validator is not None else 0,
            "oracleOutcomeCounts": dict(sorted(oracle_outcomes.items())),
            "oracleStableActiveFullOperationVariantCount": stable_active_count,
            "hasOracleStableActiveTransplant": stable_active_count > 0,
            "sourceLimit": max(0, int(source_limit)),
            "variantLimit": max(0, int(variant_limit)),
            "maxGrabCycles": max(1, int(max_grab_cycles)),
            "localCycles": max(1, int(local_cycles)),
            "oraclePromotionLimit": max(0, int(oracle_promotion_limit)),
            "oracleEnabled": oracle_validator is not None,
            "oracleWorkers": max(1, min(10, int(oracle_workers))),
            "selectionPolicy": (
                "oracle-stability-then-active-operation-coverage"
                if oracle_validator is not None
                else "local-survival-then-active-operation-coverage"
            ),
        },
        "variants": selected,
    }
