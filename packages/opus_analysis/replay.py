from __future__ import annotations

from typing import Any

ROTATE_CW = {"rotate_cw", "rotate-clockwise"}
ROTATE_CCW = {"rotate_ccw", "rotate-counterclockwise"}
EXTEND = {"extend", "extend_piston"}
RETRACT = {"retract", "retract_piston"}
GRAB = {"grab"}
DROP = {"drop", "reset"}
PIVOT_CW = {"pivot_cw", "pivot-clockwise"}
PIVOT_CCW = {"pivot_ccw", "pivot-counterclockwise"}


def _initial_arm_state(part: dict[str, Any]) -> dict[str, Any]:
    base_length = max(1, int(part.get("length") or 1))
    return {
        "partId": part["id"],
        "armNumber": part.get("armNumber"),
        "partType": part.get("type"),
        "origin": part.get("position") or [0, 0],
        "rotation": int(part.get("rotation") or 0) % 6,
        "length": base_length,
        "baseLength": base_length,
        "grabbing": False,
        "heldRotation": 0,
        "trackOffset": 0,
        "lastInstruction": None,
        "stateSource": "kinematic-program-model",
    }


def _apply_instruction(state: dict[str, Any], instruction: str | None) -> None:
    if not instruction:
        return
    state["lastInstruction"] = instruction
    if instruction in ROTATE_CW:
        state["rotation"] = (state["rotation"] - 1) % 6
    elif instruction in ROTATE_CCW:
        state["rotation"] = (state["rotation"] + 1) % 6
    elif instruction in EXTEND and state.get("partType") == "piston":
        state["length"] = min(3, int(state["length"]) + 1)
    elif instruction in RETRACT and state.get("partType") == "piston":
        state["length"] = max(int(state["baseLength"]), int(state["length"]) - 1)
    elif instruction in GRAB:
        state["grabbing"] = True
    elif instruction in DROP:
        state["grabbing"] = False
    elif instruction in PIVOT_CW:
        state["heldRotation"] = (int(state["heldRotation"]) - 1) % 6
    elif instruction in PIVOT_CCW:
        state["heldRotation"] = (int(state["heldRotation"]) + 1) % 6


def build_replay_trace(solution: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    """Build a canonical replay trace with deterministic arm kinematics.

    Arm rotation, piston length and grab state are evolved directly from the
    expanded instruction tapes. This is a real stateful kinematic model, but it
    is not yet a complete OMSim physical trace: track motion, atoms, bonds,
    collisions and glyph effects remain unresolved.
    """
    parts = {part["id"]: part for part in solution.get("parts", [])}
    arm_parts = [
        part for part in solution.get("parts", [])
        if part.get("type", "").startswith("arm") or part.get("type") in {"piston", "baron"}
    ]
    states = {part["id"]: _initial_arm_state(part) for part in arm_parts}
    frames: list[dict[str, Any]] = []

    for row in timeline.get("cycles", []):
        events: list[dict[str, Any]] = []
        for event in row.get("events", []):
            part = parts.get(event.get("partId"), {})
            instruction = event.get("instruction")
            events.append({
                "kind": "arm-instruction",
                "partId": event.get("partId"),
                "armNumber": event.get("armNumber"),
                "partType": event.get("type"),
                "instruction": instruction,
                "rawCode": event.get("rawCode"),
                "tapeCycle": event.get("tapeCycle"),
                "origin": part.get("position"),
                "baseRotation": part.get("rotation"),
                "baseLength": part.get("length"),
            })
            state = states.get(event.get("partId"))
            if state is not None:
                _apply_instruction(state, instruction)

        frames.append({
            "cycle": row.get("cycle", 0),
            "phase": 1,
            "phaseLabel": "after-instructions",
            "activeArmCount": row.get("activeArms", 0),
            "events": events,
            "armStates": [dict(state) for state in states.values()],
            "molecules": [],
        })

    return {
        "schemaVersion": "0.2.0",
        "traceType": "kinematic-arm-replay",
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
            "trackAnimation": False,
            "moleculeAnimation": False,
        },
        "limitations": [
            "Arm poses are derived from instruction semantics, not exported from OMSim internals.",
            "Each frame represents the state after the scheduled instructions for that cycle.",
            "Track motion, atom positions, bonds, collisions and glyph effects are not resolved yet.",
            "Pivot instructions update held-object orientation metadata, but molecules are not drawn yet.",
        ],
        "frames": frames,
    }
