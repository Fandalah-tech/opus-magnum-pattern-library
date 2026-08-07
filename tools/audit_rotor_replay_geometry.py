from __future__ import annotations

import json
from pathlib import Path

REPORT = Path("reports/rotor-tail-best-candidate-replay.json")


def key(cell):
    return f"{int(cell[0])},{int(cell[1])}"


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    solution = report["renderContext"]["solution"]
    track = next(part for part in solution.get("parts", []) if part.get("type") == "track")
    track_origin = track.get("position") or [0, 0]
    track_world = [
        [track_origin[0] + cell[0], track_origin[1] + cell[1]]
        for cell in track.get("trackHexes", [])
    ]

    static = set()
    for part in solution.get("parts", []):
        if part.get("type") == "track":
            for cell in track_world:
                static.add(key(cell))
        else:
            static.add(key(part.get("position") or [0, 0]))

    cumulative = set(static)
    samples = {0, 37, report.get("solverStartIndex", 0), len(report.get("frames", [])) - 1}
    sample_payload = []
    max_area = len(cumulative)

    for index, frame in enumerate(report.get("frames", [])):
        state = frame.get("state", {})
        for atom in state.get("atoms", []):
            cumulative.add(key(atom.get("position") or [0, 0]))
        for arm in state.get("arms", {}).values():
            cumulative.add(key(arm.get("origin") or [0, 0]))
            for tip in arm.get("tips", []):
                cumulative.add(key(tip.get("position") or [0, 0]))
        max_area = max(max_area, len(cumulative))

        if index in samples:
            atoms = state.get("atoms", [])
            held_atoms = [atom for atom in atoms if atom.get("heldBy")]
            arms = state.get("arms", {})
            tracked = [
                {
                    "id": arm_id,
                    "type": arm.get("partType"),
                    "origin": arm.get("origin"),
                    "trackIndex": arm.get("trackIndex"),
                    "heldAtoms": arm.get("heldAtoms", []),
                }
                for arm_id, arm in arms.items()
                if arm.get("trackCellCount", 0)
            ]
            sample_payload.append({
                "index": index,
                "cycle": state.get("cycle"),
                "score": state.get("score"),
                "atomCount": len(atoms),
                "heldAtomCount": len(held_atoms),
                "heldAtoms": [
                    {"id": atom.get("id"), "position": atom.get("position"), "heldBy": atom.get("heldBy")}
                    for atom in held_atoms
                ],
                "trackedArms": tracked,
                "cumulativeAreaApprox": len(cumulative),
            })

    print(json.dumps({
        "schemaVersion": report.get("schemaVersion"),
        "replayFixes": report.get("replayFixes"),
        "track": {
            "origin": track_origin,
            "localCells": track.get("trackHexes", []),
            "worldCells": track_world,
            "originExplicitlyOnRail": track_origin in track_world,
        },
        "samples": sample_payload,
        "maxCumulativeAreaApprox": max_area,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
