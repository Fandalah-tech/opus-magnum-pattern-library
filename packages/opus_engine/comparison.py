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


def compare_replays(old_replay: dict[str, Any], engine_replay: dict[str, Any]) -> dict[str, Any]:
    """Compare canonical observable state without relying on generated atom IDs."""
    old_frames = old_replay.get("frames", [])
    engine_frames = engine_replay.get("frames", [])
    compared = min(len(old_frames), len(engine_frames))
    divergences: list[dict[str, Any]] = []

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

        if categories:
            divergences.append({
                "frameIndex": index,
                "legacyCycle": old_frame.get("displayCycle", old_frame.get("cycle")),
                "engineCycle": engine_frame.get("cycle"),
                "categories": categories,
            })
            break

    frame_count_mismatch = len(old_frames) != len(engine_frames)
    if not divergences and frame_count_mismatch:
        divergences.append({
            "frameIndex": compared,
            "categories": {
                "frameCount": {"legacy": len(old_frames), "engine": len(engine_frames)}
            },
        })

    return {
        "schemaVersion": "0.1.0",
        "status": "match" if not divergences else "diverged",
        "comparedFrameCount": compared,
        "legacyFrameCount": len(old_frames),
        "engineFrameCount": len(engine_frames),
        "firstDivergence": divergences[0] if divergences else None,
        "limitations": [
            "Atom comparison uses element and board position rather than generated IDs.",
            "The legacy replay is a development reference, not an authoritative game simulation.",
            "Glyph effects absent from either engine can produce expected divergences.",
        ],
    }
