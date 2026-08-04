from __future__ import annotations

from typing import Any

ROTATE_CW = {"rotate_cw", "rotate-clockwise"}
ROTATE_CCW = {"rotate_ccw", "rotate-counterclockwise"}
EXTEND = {"extend", "extend_piston"}
RETRACT = {"retract", "retract_piston"}
GRAB = {"grab"}
DROP = {"drop"}
RESET = {"reset"}
TRACK_PLUS = {"track_plus"}
TRACK_MINUS = {"track_minus"}
PIVOT_CW = {"pivot_cw", "pivot-clockwise"}
PIVOT_CCW = {"pivot_ccw", "pivot-counterclockwise"}


def _track_for_arm(part: dict[str, Any], tracks: list[dict[str, Any]]) -> list[list[int]]:
    origin = list(part.get("position") or [0, 0])
    for track in tracks:
        cells = [list(cell) for cell in track.get("trackHexes", [])]
        if origin in cells:
            return cells
    return []


def _initial_arm_state(part: dict[str, Any], track_cells: list[list[int]]) -> dict[str, Any]:
    base_length = max(1, int(part.get("length") or 1))
    base_origin = list(part.get("position") or [0, 0])
    track_index = track_cells.index(base_origin) if base_origin in track_cells else 0
    return {
        "partId": part["id"],
        "armNumber": part.get("armNumber"),
        "partType": part.get("type"),
        "origin": list(base_origin),
        "baseOrigin": list(base_origin),
        "rotation": int(part.get("rotation") or 0) % 6,
        "baseRotation": int(part.get("rotation") or 0) % 6,
        "length": base_length,
        "baseLength": base_length,
        "grabbing": False,
        "heldRotation": 0,
        "trackIndex": track_index,
        "baseTrackIndex": track_index,
        "trackCells": [list(cell) for cell in track_cells],
        "lastInstruction": None,
        "stateSource": "kinematic-program-model",
    }


def _move_on_track(state: dict[str, Any], delta: int) -> None:
    cells = state.get("trackCells") or []
    if not cells:
        return
    next_index = max(0, min(len(cells) - 1, int(state.get("trackIndex", 0)) + delta))
    state["trackIndex"] = next_index
    state["origin"] = list(cells[next_index])


def _reset_state(state: dict[str, Any]) -> None:
    state["origin"] = list(state.get("baseOrigin") or [0, 0])
    state["rotation"] = int(state.get("baseRotation", 0)) % 6
    state["length"] = int(state.get("baseLength", 1))
    state["trackIndex"] = int(state.get("baseTrackIndex", 0))
    state["grabbing"] = False
    state["heldRotation"] = 0


def _apply_instruction(state: dict[str, Any], instruction: str | None) -> None:
    if not instruction:
        return
    state["lastInstruction"] = instruction
    if instruction in ROTATE_CW:
        state["rotation"] = (int(state["rotation"]) - 1) % 6
    elif instruction in ROTATE_CCW:
        state["rotation"] = (int(state["rotation"]) + 1) % 6
    elif instruction in EXTEND and state.get("partType") == "piston":
        state["length"] = min(3, int(state["length"]) + 1)
    elif instruction in RETRACT and state.get("partType") == "piston":
        state["length"] = max(int(state["baseLength"]), int(state["length"]) - 1)
    elif instruction in GRAB:
        state["grabbing"] = True
    elif instruction in DROP:
        state["grabbing"] = False
    elif instruction in RESET:
        _reset_state(state)
    elif instruction in TRACK_PLUS:
        _move_on_track(state, 1)
    elif instruction in TRACK_MINUS:
        _move_on_track(state, -1)
    elif instruction in PIVOT_CW:
        state["heldRotation"] = (int(state["heldRotation"]) - 1) % 6
    elif instruction in PIVOT_CCW:
        state["heldRotation"] = (int(state["heldRotation"]) + 1) % 6


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if key != "trackCells"}


def build_replay_trace(solution: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic arm-state trace from macro-expanded programs.

    This layer resolves arm rotation, piston extension, grab state, pivot
    metadata, reset state and movement along ordered track cells. Atom motion,
    collisions and glyph chemistry remain outside this kinematic model.
    """
    parts = {part["id"]: part for part in solution.get("parts", [])}
    tracks = [part for part in solution.get("parts", []) if part.get("type") == "track"]
    arm_parts = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    states = {
        part["id"]: _initial_arm_state(part, _track_for_arm(part, tracks))
        for part in arm_parts
    }
    frames: list[dict[str, Any]] = []

    for row in timeline.get("cycles", []):
        events: list[dict[str, Any]] = []
        for event in row.get("events", []):
            part = parts.get(event.get("partId"), {})
            instruction = event.get("instruction")
            state = states.get(event.get("partId"))
            before = _public_state(state) if state is not None else None
            if state is not None:
                _apply_instruction(state, instruction)
            after = _public_state(state) if state is not None else None
            events.append({
                "kind": "arm-instruction",
                "partId": event.get("partId"),
                "armNumber": event.get("armNumber"),
                "partType": event.get("type"),
                "instruction": instruction,
                "rawCode": event.get("rawCode"),
                "tapeCycle": event.get("tapeCycle"),
                "generatedBy": event.get("generatedBy"),
                "sourceCycle": event.get("sourceCycle"),
                "before": before,
                "after": after,
                "origin": part.get("position"),
            })

        frames.append({
            "cycle": row.get("cycle", 0),
            "phase": 1,
            "phaseLabel": "after-instructions",
            "activeArmCount": row.get("activeArms", 0),
            "events": events,
            "armStates": [_public_state(state) for state in states.values()],
            "molecules": [],
        })

    has_tracks = any(state.get("trackCells") for state in states.values())
    return {
        "schemaVersion": "0.3.0",
        "traceType": "complete-arm-kinematic-replay",
        "source": "opus-analysis",
        "summary": {
            "frameCount": len(frames),
            "cycleCount": timeline.get("summary", {}).get("horizon", len(frames)),
            "phaseCount": 1,
            "hasPhysicalArmStates": True,
            "hasMoleculeStates": False,
        },
        "capabilities": {
            "seek": True,
            "playback": True,
            "activeArmHighlight": True,
            "physicalArmAnimation": True,
            "pistonAnimation": True,
            "grabState": True,
            "pivotState": True,
            "resetState": True,
            "trackAnimation": has_tracks,
            "moleculeAnimation": False,
        },
        "limitations": [
            "Arm poses are derived from instruction semantics, not exported from OMSim internals.",
            "Reset is represented as a state restoration on its scheduled cycle; its hidden generated path is not split into substeps.",
            "Track movement follows the ordered trackHexes sequence and does not yet resolve branching tracks.",
            "Atom positions, bonds, collisions and glyph effects are not resolved yet.",
        ],
        "frames": frames,
    }
