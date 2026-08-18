from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re
from typing import Any

from packages.opus_analysis import build_program_timeline
from packages.opus_engine import Simulator
from packages.opus_engine.builder import rotate_hex


_INPUT_ATOM_RE = re.compile(r"^(?P<input>.+)-spawn-\d+-atom-(?P<atom>\d+)$")


def _position(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def _add(first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
    return first[0] + second[0], first[1] + second[1]


def _sub(first: tuple[int, int], second: tuple[int, int]) -> tuple[int, int]:
    return first[0] - second[0], first[1] - second[1]


def replay_summary(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int,
) -> dict[str, Any]:
    """Replay one generated solution and return compact mechanical/chemistry progress."""

    horizon = max(1, int(max_cycles))
    simulator = Simulator.from_models(puzzle, solution)
    replay = simulator.run_timeline(build_program_timeline(solution, max_cycles=horizon))
    counts = Counter(
        str(event.get("kind") or "")
        for frame in replay.get("frames", []) or []
        for event in frame.get("events", []) or []
    )
    first_error = next(
        (
            {
                "cycle": int(event.get("cycle", frame.get("cycle", 0)) or 0),
                "message": str(event.get("message") or "Simulation error"),
            }
            for frame in replay.get("frames", []) or []
            for event in frame.get("events", []) or []
            if str(event.get("kind") or "") == "simulation-error"
        ),
        None,
    )
    return {
        "completedCycles": int((replay.get("summary") or {}).get("completedCycles") or 0),
        "requestedCycles": int((replay.get("summary") or {}).get("requestedCycles") or horizon),
        "terminatedWithError": bool((replay.get("summary") or {}).get("terminatedWithError")),
        "firstError": first_error,
        "eventCounts": dict(sorted(counts.items())),
        "purificationCount": int(counts.get("atom-purified", 0)),
        "productDeliveredCount": int(counts.get("product-delivered", 0)),
        "chemistryEventCount": sum(
            int(counts.get(kind, 0))
            for kind in (
                "atom-purified",
                "atom-projected",
                "atom-duplicated",
                "atom-calcified",
                "bond-created",
                "bond-removed",
            )
        ),
        "manipulationEventCount": sum(
            int(counts.get(kind, 0))
            for kind in ("atom-grabbed", "atoms-dropped", "input-spawned")
        ),
        "replay": replay,
    }


def first_grabbed_input_anchors(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    replay: dict[str, Any],
) -> list[dict[str, Any]]:
    """Infer which reagent atom each inherited input first presents to a grabber.

    Input atom ids encode the spawned reagent atom index.  Once that index is
    known, the anchor world coordinate is determined solely from the puzzle
    reagent geometry and the current input pose.  This remains valid even when
    the grabbed molecule moves later in the same engine frame.
    """

    inputs = {
        str(part.get("id") or ""): part
        for part in solution.get("parts", []) or []
        if str(part.get("type") or "") == "input"
    }
    reagents = list(puzzle.get("reagents", []) or [])
    first_events: dict[str, dict[str, Any]] = {}

    for frame in replay.get("frames", []) or []:
        for event in frame.get("events", []) or []:
            if str(event.get("kind") or "") != "atom-grabbed":
                continue
            atom_id = str(event.get("atomId") or "")
            match = _INPUT_ATOM_RE.match(atom_id)
            if match is None:
                continue
            input_id = str(match.group("input"))
            if input_id not in inputs or input_id in first_events:
                continue
            first_events[input_id] = {
                "atomId": atom_id,
                "atomIndex": int(match.group("atom")),
                "cycle": int(event.get("cycle", frame.get("cycle", 0)) or 0),
                "armId": str(event.get("armId") or ""),
                "branchIndex": int(event.get("branchIndex") or 0),
            }

    result: list[dict[str, Any]] = []
    for input_id, event in sorted(first_events.items(), key=lambda item: (item[1]["cycle"], item[0])):
        part = inputs[input_id]
        reagent_index = int(part.get("which") or 0)
        if not 0 <= reagent_index < len(reagents):
            continue
        atoms = list(reagents[reagent_index].get("atoms", []) or [])
        atom_index = int(event["atomIndex"])
        if not 0 <= atom_index < len(atoms):
            continue
        local = _position(atoms[atom_index].get("position"))
        rotation = int(part.get("rotation") or 0) % 6
        origin = _position(part.get("position"))
        anchor_world = _add(origin, rotate_hex(local, rotation))
        result.append({
            "inputId": input_id,
            "reagentIndex": reagent_index,
            "atomIndex": atom_index,
            "atomElement": str(atoms[atom_index].get("element") or ""),
            "atomLocalPosition": list(local),
            "anchorWorldPosition": list(anchor_world),
            "currentOrigin": list(origin),
            "currentRotation": rotation,
            "firstGrabCycle": int(event["cycle"]),
            "servingArmId": event["armId"],
            "branchIndex": int(event["branchIndex"]),
        })
    return result


def rotate_input_around_anchor(
    solution: dict[str, Any],
    anchor: dict[str, Any],
    *,
    rotation: int,
) -> dict[str, Any]:
    """Rotate a whole reagent molecule while keeping its first-grab atom fixed."""

    result = deepcopy(solution)
    input_id = str(anchor.get("inputId") or "")
    part = next(
        (
            item for item in result.get("parts", []) or []
            if str(item.get("id") or "") == input_id
            and str(item.get("type") or "") == "input"
        ),
        None,
    )
    if part is None:
        raise ValueError(f"Input part {input_id!r} not found")
    target_rotation = int(rotation) % 6
    local = _position(anchor.get("atomLocalPosition"))
    anchor_world = _position(anchor.get("anchorWorldPosition"))
    rotated_local = rotate_hex(local, target_rotation)
    new_origin = _sub(anchor_world, rotated_local)
    part["rotation"] = target_rotation
    part["position"] = [new_origin[0], new_origin[1]]
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/trace-guided-input-footprint-v1"
    source.setdefault("inputFootprintRepairs", []).append({
        "inputId": input_id,
        "reagentIndex": int(anchor.get("reagentIndex") or 0),
        "atomIndex": int(anchor.get("atomIndex") or 0),
        "anchorWorldPosition": list(anchor_world),
        "fromRotation": int(anchor.get("currentRotation") or 0) % 6,
        "toRotation": target_rotation,
        "fromOrigin": list(anchor.get("currentOrigin") or (0, 0)),
        "toOrigin": [new_origin[0], new_origin[1]],
        "targetSolutionBytesUsed": 0,
    })
    return result


def _rank(record: dict[str, Any]) -> tuple[Any, ...]:
    summary = record.get("summary") or {}
    return (
        int(summary.get("productDeliveredCount") or 0),
        int(summary.get("purificationCount") or 0),
        int(not bool(summary.get("terminatedWithError"))),
        int(summary.get("completedCycles") or 0),
        int(summary.get("chemistryEventCount") or 0),
        int(summary.get("manipulationEventCount") or 0),
        -int(record.get("rotationDistance") or 0),
    )


def search_input_footprint_rotations(
    puzzle: dict[str, Any],
    solution: dict[str, Any],
    *,
    max_cycles: int = 256,
    beam_width: int = 4,
    depth: int = 2,
) -> dict[str, Any]:
    """Search reagent rotations that preserve learned grab anchors but clear later motion.

    This targets a common blind-transfer failure: the donor transport path is
    useful, but a differently shaped target reagent respawns into that path.
    Each edit rotates the complete target reagent around the atom that the
    inherited mechanism already grabs, so feed semantics are preserved while
    the unused molecule footprint changes.
    """

    horizon = max(1, int(max_cycles))
    baseline = replay_summary(puzzle, solution, max_cycles=horizon)
    anchors = first_grabbed_input_anchors(puzzle, solution, baseline["replay"])
    baseline_compact = {key: value for key, value in baseline.items() if key != "replay"}

    beam = [{
        "solution": deepcopy(solution),
        "summary": baseline_compact,
        "edits": [],
    }]
    generations: list[dict[str, Any]] = []
    seen = {
        tuple(
            (str(part.get("id") or ""), int(part.get("rotation") or 0) % 6, tuple(part.get("position") or (0, 0)))
            for part in solution.get("parts", []) or []
            if str(part.get("type") or "") == "input"
        )
    }

    for generation in range(max(0, int(depth))):
        candidates: list[dict[str, Any]] = []
        for state in beam:
            # Recompute anchors after earlier edits because the preserved world
            # grab point remains fixed while the input origin/rotation changes.
            current_replay = replay_summary(puzzle, state["solution"], max_cycles=horizon)
            current_anchors = first_grabbed_input_anchors(puzzle, state["solution"], current_replay["replay"])
            for anchor in current_anchors:
                current_rotation = int(anchor.get("currentRotation") or 0) % 6
                for rotation in range(6):
                    if rotation == current_rotation:
                        continue
                    candidate = rotate_input_around_anchor(state["solution"], anchor, rotation=rotation)
                    signature = tuple(
                        (str(part.get("id") or ""), int(part.get("rotation") or 0) % 6, tuple(part.get("position") or (0, 0)))
                        for part in candidate.get("parts", []) or []
                        if str(part.get("type") or "") == "input"
                    )
                    if signature in seen:
                        continue
                    seen.add(signature)
                    replayed = replay_summary(puzzle, candidate, max_cycles=horizon)
                    compact = {key: value for key, value in replayed.items() if key != "replay"}
                    # Do not trade away the chemistry frontier already achieved.
                    if int(compact.get("purificationCount") or 0) < int(baseline_compact.get("purificationCount") or 0):
                        continue
                    distance = min((rotation - current_rotation) % 6, (current_rotation - rotation) % 6)
                    candidates.append({
                        "solution": candidate,
                        "summary": compact,
                        "rotationDistance": distance,
                        "edits": [
                            *state.get("edits", []),
                            (candidate.get("source") or {}).get("inputFootprintRepairs", [])[-1],
                        ],
                    })

        candidates.sort(key=_rank, reverse=True)
        beam = candidates[:max(1, int(beam_width))]
        generations.append({
            "generation": generation + 1,
            "candidateCount": len(candidates),
            "beamCount": len(beam),
            "bestSummary": deepcopy(beam[0]["summary"] if beam else baseline_compact),
            "bestEdits": deepcopy(beam[0].get("edits", []) if beam else []),
        })
        if not beam:
            break
        best = beam[0]["summary"]
        if not bool(best.get("terminatedWithError")) and int(best.get("completedCycles") or 0) >= horizon:
            break

    ordered = sorted(beam, key=_rank, reverse=True) if beam else []
    best_state = ordered[0] if ordered else {
        "solution": deepcopy(solution),
        "summary": baseline_compact,
        "edits": [],
    }
    return {
        "schemaVersion": "0.1.0",
        "kind": "trace-guided-input-footprint-rotation-search",
        "summary": {
            "maxCycles": horizon,
            "inputAnchorCount": len(anchors),
            "requestedDepth": max(0, int(depth)),
            "beamWidth": max(1, int(beam_width)),
            "generationCount": len(generations),
            "baselineCompletedCycles": int(baseline_compact.get("completedCycles") or 0),
            "bestCompletedCycles": int((best_state.get("summary") or {}).get("completedCycles") or 0),
            "baselinePurificationCount": int(baseline_compact.get("purificationCount") or 0),
            "bestPurificationCount": int((best_state.get("summary") or {}).get("purificationCount") or 0),
            "bestTerminatedWithError": bool((best_state.get("summary") or {}).get("terminatedWithError")),
            "targetSolutionBytesUsed": 0,
        },
        "anchors": anchors,
        "baseline": baseline_compact,
        "generations": generations,
        "best": best_state,
    }


__all__ = [
    "first_grabbed_input_anchors",
    "replay_summary",
    "rotate_input_around_anchor",
    "search_input_footprint_rotations",
]
