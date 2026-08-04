from __future__ import annotations

from typing import Any


def _old_arm_signature(frame: dict[str, Any]) -> dict[str, tuple]:
    return {
        str(state.get("partId")): (
            tuple(state.get("origin") or (0, 0)),
            int(state.get("rotation") or 0) % 6,
            int(state.get("length") or state.get("baseLength") or 1),
            bool(state.get("grabbing")),
        )
        for state in frame.get("armStates", [])
    }


def _engine_arm_signature(frame: dict[str, Any]) -> dict[str, tuple]:
    return {
        str(state.get("partId")): (
            tuple(state.get("origin") or (0, 0)),
            int(state.get("rotation") or 0) % 6,
            int(state.get("length") or 1),
            bool(state.get("grabbing")),
        )
        for state in frame.get("arms", [])
    }


def _old_atom_signature(frame: dict[str, Any]) -> list[tuple[str, int, int]]:
    atoms = []
    for molecule in frame.get("molecules", []):
        for atom in molecule.get("atoms", []):
            q, r = atom.get("position") or (0, 0)
            atoms.append((str(atom.get("element")), int(q), int(r)))
    return sorted(atoms)


def _engine_atom_signature(frame: dict[str, Any]) -> list[tuple[str, int, int]]:
    atoms = []
    for atom in frame.get("world", {}).get("atoms", []):
        q, r = atom.get("position") or (0, 0)
        atoms.append((str(atom.get("element")), int(q), int(r)))
    return sorted(atoms)


def _instruction_context(frame: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "partId": event.get("partId") or event.get("armId"),
            "instruction": event.get("instruction"),
        }
        for event in frame.get("events", [])
        if event.get("instruction")
    ]


def _simulation_error(frame: dict[str, Any]) -> dict[str, Any] | None:
    if frame.get("phase") != "error":
        return None
    event = next(
        (item for item in frame.get("events", []) if item.get("kind") == "simulation-error"),
        None,
    )
    return {
        "message": event.get("message") if event else None,
        "cycle": frame.get("cycle"),
    }


def classify_divergence(categories: dict[str, Any], legacy_frame: dict[str, Any], engine_frame: dict[str, Any]) -> dict[str, Any]:
    instructions = _instruction_context(legacy_frame) or _instruction_context(engine_frame)
    names = {str(item.get("instruction") or "") for item in instructions}
    engine_error = _simulation_error(engine_frame)

    if engine_error is not None:
        subsystem, reason = "engine-error", "simulation-error"
    elif "frameCount" in categories:
        subsystem, reason = "timeline", "frame-count-mismatch"
    elif "arms" in categories:
        if names & {"track_plus", "track_minus"}:
            subsystem, reason = "track", "arm-origin-divergence"
        elif names & {"extend", "retract", "extend_piston", "retract_piston"}:
            subsystem, reason = "piston", "arm-length-divergence"
        elif names & {"reset"}:
            subsystem, reason = "reset", "arm-state-divergence"
        else:
            subsystem, reason = "arm-kinematics", "arm-state-divergence"
    elif "atoms" in categories:
        legacy_count = int(categories["atoms"].get("legacyCount", 0))
        engine_count = int(categories["atoms"].get("engineCount", 0))
        if legacy_count != engine_count:
            subsystem, reason = "world-lifecycle", "atom-count-divergence"
        elif names & {"pivot_cw", "pivot_ccw", "pivot-clockwise", "pivot-counterclockwise"}:
            subsystem, reason = "pivot", "atom-position-divergence"
        else:
            subsystem, reason = "molecule-motion", "atom-position-divergence"
    else:
        subsystem, reason = "unknown", "unclassified-divergence"

    result = {
        "subsystem": subsystem,
        "reason": reason,
        "instructions": instructions,
        "confidence": "high" if instructions or subsystem in {"timeline", "world-lifecycle", "engine-error"} else "medium",
    }
    if engine_error is not None:
        result["engineError"] = engine_error
    return result


def compare_replays(old_replay: dict[str, Any], engine_replay: dict[str, Any]) -> dict[str, Any]:
    """Compare canonical observable state without relying on generated atom IDs."""
    old_frames = old_replay.get("frames", [])
    engine_frames = engine_replay.get("frames", [])
    compared = min(len(old_frames), len(engine_frames))
    divergence = None

    for index in range(compared):
        old_frame = old_frames[index]
        engine_frame = engine_frames[index]
        categories: dict[str, Any] = {}

        old_arms = _old_arm_signature(old_frame)
        new_arms = _engine_arm_signature(engine_frame)
        if old_arms != new_arms:
            categories["arms"] = {"legacy": old_arms, "engine": new_arms}

        old_atoms = _old_atom_signature(old_frame)
        new_atoms = _engine_atom_signature(engine_frame)
        if old_atoms != new_atoms:
            categories["atoms"] = {
                "legacyCount": len(old_atoms),
                "engineCount": len(new_atoms),
                "legacy": old_atoms,
                "engine": new_atoms,
            }

        if categories or _simulation_error(engine_frame) is not None:
            divergence = {
                "frameIndex": index,
                "legacyCycle": old_frame.get("displayCycle", old_frame.get("cycle")),
                "engineCycle": engine_frame.get("cycle"),
                "categories": categories,
                "classification": classify_divergence(categories, old_frame, engine_frame),
            }
            break

    if divergence is None and len(old_frames) != len(engine_frames):
        categories = {"frameCount": {"legacy": len(old_frames), "engine": len(engine_frames)}}
        divergence = {
            "frameIndex": compared,
            "categories": categories,
            "classification": classify_divergence(categories, {}, {}),
        }

    return {
        "schemaVersion": "0.2.0",
        "status": "match" if divergence is None else "diverged",
        "comparedFrameCount": compared,
        "legacyFrameCount": len(old_frames),
        "engineFrameCount": len(engine_frames),
        "firstDivergence": divergence,
        "limitations": [
            "Atom comparison uses element and board position rather than generated IDs.",
            "The legacy replay is a development reference, not an authoritative game simulation.",
            "Glyph effects absent from either engine can produce expected divergences.",
        ],
    }
