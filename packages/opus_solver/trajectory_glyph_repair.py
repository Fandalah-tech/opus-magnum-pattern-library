from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import DIRECTIONS

from .candidate_solution import serialize_candidate_roundtrip
from .chemistry_transplant import mechanical_fingerprint
from .solver import validate_generated_solution


METAL_ORDER = ("lead", "tin", "iron", "copper", "silver", "gold")


def _add(first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
    return first[0] + second[0], first[1] + second[1]


def _scale(direction: tuple[int, int], factor: int) -> tuple[int, int]:
    return direction[0] * factor, direction[1] * factor


def purification_poses_from_replay(replay: dict[str, Any]) -> list[dict[str, Any]]:
    """Find purification glyph poses proven useful by target-candidate trajectories.

    A purification glyph consumes equal metals on the two endpoints of a
    three-cell straight line and produces the next metal on the empty center.
    This function observes only the candidate replay: it records poses where
    two equal, purifiable metals actually coexist at the two endpoints while the
    center is empty. No target solution geometry participates.
    """

    observations: dict[tuple[tuple[int, int], int, str], dict[str, Any]] = {}
    for frame in replay.get("frames", []):
        cycle = int(frame.get("cycle") or 0)
        atoms = list((frame.get("world") or {}).get("atoms", []))
        by_position = {
            tuple(int(value) for value in (atom.get("position") or (0, 0))): atom
            for atom in atoms
        }
        seen_frame_keys: set[tuple[tuple[int, int], int, str]] = set()
        for origin, first in by_position.items():
            element = str(first.get("element") or "")
            if element not in METAL_ORDER or element == "gold":
                continue
            for rotation, direction in enumerate(DIRECTIONS):
                center = _add(origin, direction)
                second_position = _add(origin, _scale(direction, 2))
                second = by_position.get(second_position)
                if second is None or str(second.get("element") or "") != element:
                    continue
                if center in by_position:
                    continue

                # Canonicalize the reversible endpoint ordering. Iterating from
                # the opposite endpoint sees the same physical line again, so
                # count the canonical pose at most once in each replay frame.
                reverse_origin = second_position
                reverse_rotation = (rotation + 3) % 6
                forward_key = (origin, rotation, element)
                reverse_key = (reverse_origin, reverse_rotation, element)
                key = min(forward_key, reverse_key)
                if key in seen_frame_keys:
                    continue
                seen_frame_keys.add(key)

                pose_origin, pose_rotation, _ = key
                item = observations.setdefault(key, {
                    "position": list(pose_origin),
                    "rotation": int(pose_rotation),
                    "element": element,
                    "producedElement": METAL_ORDER[METAL_ORDER.index(element) + 1],
                    "firstCycle": cycle,
                    "lastCycle": cycle,
                    "observationCount": 0,
                    "sampleAtomPairs": [],
                })
                item["lastCycle"] = cycle
                item["observationCount"] += 1
                pair = sorted((
                    str(first.get("id") or ""),
                    str(second.get("id") or ""),
                ))
                if pair not in item["sampleAtomPairs"] and len(item["sampleAtomPairs"]) < 4:
                    item["sampleAtomPairs"].append(pair)

    return sorted(
        observations.values(),
        key=lambda item: (
            -int(item["observationCount"]),
            int(item["firstCycle"]),
            str(item["element"]),
            tuple(item["position"]),
            int(item["rotation"]),
        ),
    )


def _run_replay(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int,
) -> dict[str, Any]:
    roundtrip = serialize_candidate_roundtrip(solution)
    timeline = build_program_timeline(roundtrip["parsed"], max_cycles=max(1, int(max_cycles)))
    return Simulator.from_models(puzzle, roundtrip["parsed"]).run_timeline(timeline)


def _rank(validation: dict[str, Any], *, observation_count: int) -> tuple[Any, ...]:
    counts = validation.get("eventCounts") or {}
    return (
        int(bool(validation.get("complete"))),
        int(validation.get("totalDelivered") or 0),
        int(counts.get("atom-purified") or 0),
        int(validation.get("distinctRequiredChemistryEventCount") or 0),
        int(not bool(validation.get("terminatedWithError"))),
        int(validation.get("completedCycles") or 0),
        int(validation.get("requiredChemistryEventCount") or 0),
        int(validation.get("chemistryEventCount") or 0),
        int(observation_count),
    )


def search_trajectory_guided_purification(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    discovery_cycles: int = 160,
    validation_cycles: int = 320,
    pose_limit: int = 96,
    result_limit: int = 16,
) -> dict[str, Any]:
    """Relocate learned purification glyphs onto target-observed metal pairs.

    Arms, tracks, programs, feeds, and all other parts remain frozen. Only the
    position/rotation of one existing purification glyph changes per candidate,
    so this is a bounded static-glyph repair rather than a puzzle-specific
    architecture generator.
    """

    purification_parts = [
        part for part in solution.get("parts", [])
        if str(part.get("type") or "") == "glyph-purification"
    ]
    if not purification_parts:
        return {
            "schemaVersion": "0.1.0",
            "summary": {
                "purificationGlyphCount": 0,
                "discoveredPoseCount": 0,
                "testedVariantCount": 0,
                "returnedVariantCount": 0,
                "purificationReachedCount": 0,
                "hasCompleteSolution": False,
            },
            "poses": [],
            "variants": [],
        }

    replay = _run_replay(puzzle, solution, max_cycles=discovery_cycles)
    poses = purification_poses_from_replay(replay)[:max(0, int(pose_limit))]
    before_mechanics = mechanical_fingerprint(solution)
    variants: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[int, int], int]] = set()

    for glyph in purification_parts:
        glyph_id = str(glyph.get("id") or "")
        original_position = tuple(int(value) for value in (glyph.get("position") or (0, 0)))
        original_rotation = int(glyph.get("rotation") or 0) % 6
        for pose in poses:
            position = tuple(int(value) for value in pose["position"])
            rotation = int(pose["rotation"]) % 6
            key = (glyph_id, position, rotation)
            if key in seen:
                continue
            seen.add(key)
            if position == original_position and rotation == original_rotation:
                continue

            candidate = deepcopy(solution)
            target_glyph = next(
                part for part in candidate.get("parts", [])
                if str(part.get("id") or "") == glyph_id
            )
            target_glyph["position"] = list(position)
            target_glyph["rotation"] = rotation
            if mechanical_fingerprint(candidate) != before_mechanics:
                raise AssertionError("Static purification repair changed arm/track mechanics")

            try:
                roundtrip = serialize_candidate_roundtrip(candidate)
                validation = validate_generated_solution(
                    puzzle,
                    roundtrip["parsed"],
                    max_cycles=max(1, int(validation_cycles)),
                )
                record = {
                    "glyphId": glyph_id,
                    "originalPosition": list(original_position),
                    "originalRotation": original_rotation,
                    "position": list(position),
                    "rotation": rotation,
                    "trajectoryEvidence": deepcopy(pose),
                    "serialization": roundtrip["diagnostics"],
                    "validation": validation,
                    "solution": candidate,
                    "mechanicsPreserved": True,
                }
                record["rank"] = _rank(
                    validation,
                    observation_count=int(pose.get("observationCount") or 0),
                )
            except Exception as error:
                record = {
                    "glyphId": glyph_id,
                    "position": list(position),
                    "rotation": rotation,
                    "trajectoryEvidence": deepcopy(pose),
                    "errorType": type(error).__name__,
                    "error": str(error),
                    "rank": (0, 0, 0, 0, 0, 0, 0, 0, 0),
                }
            variants.append(record)

    variants.sort(key=lambda item: tuple(item.get("rank") or ()), reverse=True)
    selected = variants[:max(0, int(result_limit))]
    for item in selected:
        item.pop("rank", None)

    purification_reached = sum(
        int(((item.get("validation") or {}).get("eventCounts") or {}).get("atom-purified") or 0) > 0
        for item in variants
    )
    complete_count = sum(bool((item.get("validation") or {}).get("complete")) for item in variants)
    discovery_events = Counter(
        str(event.get("kind") or "unknown")
        for frame in replay.get("frames", [])
        for event in frame.get("events", [])
    )
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "purificationGlyphCount": len(purification_parts),
            "discoveryCycles": max(1, int(discovery_cycles)),
            "validationCycles": max(1, int(validation_cycles)),
            "discoveryCompletedCycles": int((replay.get("summary") or {}).get("completedCycles") or 0),
            "discoveryTerminatedWithError": bool((replay.get("summary") or {}).get("terminatedWithError")),
            "discoveryEventCounts": dict(sorted(discovery_events.items())),
            "discoveredPoseCount": len(poses),
            "testedVariantCount": len(variants),
            "returnedVariantCount": len(selected),
            "purificationReachedCount": purification_reached,
            "completeVariantCount": complete_count,
            "hasCompleteSolution": complete_count > 0,
            "mechanicsFingerprint": before_mechanics,
        },
        "poses": poses,
        "variants": selected,
    }


__all__ = [
    "purification_poses_from_replay",
    "search_trajectory_guided_purification",
]
