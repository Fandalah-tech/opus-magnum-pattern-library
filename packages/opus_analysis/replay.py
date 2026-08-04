from __future__ import annotations

from typing import Any


def build_replay_trace(solution: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    """Build the first canonical replay trace from the expanded arm timeline.

    This trace is intentionally program-static. It is suitable for transport,
    controls, active-arm highlighting and schema stabilization, but it does not
    claim molecule positions or physically simulated arm transforms yet.
    """
    parts = {part["id"]: part for part in solution.get("parts", [])}
    frames: list[dict[str, Any]] = []

    for row in timeline.get("cycles", []):
        events: list[dict[str, Any]] = []
        for event in row.get("events", []):
            part = parts.get(event.get("partId"), {})
            events.append({
                "kind": "arm-instruction",
                "partId": event.get("partId"),
                "armNumber": event.get("armNumber"),
                "partType": event.get("type"),
                "instruction": event.get("instruction"),
                "rawCode": event.get("rawCode"),
                "tapeCycle": event.get("tapeCycle"),
                "origin": part.get("position"),
                "baseRotation": part.get("rotation"),
                "baseLength": part.get("length"),
            })
        frames.append({
            "cycle": row.get("cycle", 0),
            "phase": 0,
            "activeArmCount": row.get("activeArms", 0),
            "events": events,
            "armStates": [
                {
                    "partId": event["partId"],
                    "instruction": event["instruction"],
                    "tapeCycle": event["tapeCycle"],
                    "physicalState": "unknown",
                }
                for event in events
            ],
            "molecules": [],
        })

    return {
        "schemaVersion": "0.1.0",
        "traceType": "static-program-replay",
        "source": "opus-analysis",
        "summary": {
            "frameCount": len(frames),
            "cycleCount": timeline.get("summary", {}).get("horizon", len(frames)),
            "phaseCount": 1,
            "hasPhysicalArmStates": False,
            "hasMoleculeStates": False,
        },
        "capabilities": {
            "seek": True,
            "playback": True,
            "activeArmHighlight": True,
            "physicalArmAnimation": False,
            "moleculeAnimation": False,
        },
        "limitations": [
            "Frames reflect scheduled instructions, not OMSim physical states.",
            "Arm rotations, pivots, extensions, grabs and drops are not resolved yet.",
            "Molecule and atom states are intentionally empty until OMSim tracing is integrated.",
        ],
        "frames": frames,
    }
