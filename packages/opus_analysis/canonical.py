from __future__ import annotations

import hashlib
import json
from typing import Any


def rotate_hex(position: tuple[int, int], steps: int) -> tuple[int, int]:
    """Rotate an axial hex coordinate by 60-degree steps."""
    q, r = position
    for _ in range(steps % 6):
        q, r = -r, q + r
    return q, r


def _program(part: dict[str, Any], *, normalize_time: bool, global_min_cycle: int) -> list[dict[str, Any]]:
    result = []
    for item in part.get("program", []):
        cycle = int(item.get("cycle") or 0)
        if normalize_time:
            cycle -= global_min_cycle
        result.append({
            "cycle": cycle,
            "instruction": str(item.get("instruction") or "unknown"),
        })
    return sorted(result, key=lambda item: (item["cycle"], item["instruction"]))


def canonical_solution_payload(solution: dict[str, Any], *, normalize_time: bool = False) -> dict[str, Any]:
    """Return a translation/rotation invariant structural representation.

    IDs such as part ids and arm numbers are omitted because they are labels,
    while conduit ids are retained because they pair pipe endpoints/segments in
    Production puzzles. Track and pipe cell geometry participate in the global
    rotation and translation normalization.
    """
    parts = list(solution.get("parts", []))
    instruction_cycles = [
        int(item.get("cycle") or 0)
        for part in parts
        for item in part.get("program", [])
    ]
    global_min_cycle = min(instruction_cycles) if instruction_cycles else 0

    candidates: list[str] = []
    payloads: dict[str, dict[str, Any]] = {}
    for steps in range(6):
        rotated_parts: list[dict[str, Any]] = []
        occupied: list[tuple[int, int]] = []

        for part in parts:
            position = tuple(int(v) for v in (part.get("position") or (0, 0)))
            rotated_position = rotate_hex(position, steps)
            occupied.append(rotated_position)
            track_hexes = [
                rotate_hex(tuple(int(v) for v in cell), steps)
                for cell in part.get("trackHexes", [])
            ]
            # Track cells are serialized as world-axis offsets from the track
            # origin. Conduit cells are local to the pipe part and therefore
            # rotate through the part rotation, not by mutating their payload.
            pipe_hexes = [tuple(int(v) for v in cell) for cell in part.get("pipeHexes", [])]
            occupied.extend(
                (rotated_position[0] + cell[0], rotated_position[1] + cell[1])
                for cell in track_hexes
            )
            rotated_part_rotation = (int(part.get("rotation") or 0) + steps) % 6
            occupied.extend(
                (
                    rotated_position[0] + rotate_hex(cell, rotated_part_rotation)[0],
                    rotated_position[1] + rotate_hex(cell, rotated_part_rotation)[1],
                )
                for cell in pipe_hexes
            )
            rotated_parts.append({
                "type": str(part.get("type") or ""),
                "enabled": bool(part.get("enabled", True)),
                "position": rotated_position,
                "length": int(part.get("length") or 0),
                "rotation": rotated_part_rotation,
                "which": int(part.get("which") or 0),
                "program": _program(part, normalize_time=normalize_time, global_min_cycle=global_min_cycle),
                "trackHexes": track_hexes,
                "pipeId": int(part.get("pipeId") or 0) if part.get("type") == "pipe" else None,
                "pipeHexes": pipe_hexes,
            })

        anchor = min(occupied) if occupied else (0, 0)
        normalized_parts = []
        for part in rotated_parts:
            q, r = part["position"]
            normalized = dict(part)
            normalized["position"] = [q - anchor[0], r - anchor[1]]
            normalized["trackHexes"] = [list(cell) for cell in part["trackHexes"]]
            normalized["pipeHexes"] = [list(cell) for cell in part["pipeHexes"]]
            normalized_parts.append(normalized)

        normalized_parts.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        payload = {
            "puzzleFile": str(solution.get("puzzleFile") or ""),
            "parts": normalized_parts,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        candidates.append(encoded)
        payloads[encoded] = payload

    best = min(candidates) if candidates else json.dumps({"puzzleFile": "", "parts": []}, sort_keys=True)
    return payloads.get(best, {"puzzleFile": "", "parts": []})


def canonical_solution_payload_with_source_ids(
    solution: dict[str, Any],
    *,
    normalize_time: bool = False,
) -> dict[str, Any]:
    """Return the canonical payload while retaining each original part ID.

    Source IDs are attached only after choosing the same identity-free
    canonical representation used by :func:`canonical_solution_payload`, so
    they never affect structural or mechanism hashes.
    """
    target = canonical_solution_payload(solution, normalize_time=normalize_time)
    parts = list(solution.get("parts", []))
    instruction_cycles = [
        int(item.get("cycle") or 0)
        for part in parts
        for item in part.get("program", [])
    ]
    global_min_cycle = min(instruction_cycles) if instruction_cycles else 0

    for steps in range(6):
        rotated_parts: list[dict[str, Any]] = []
        occupied: list[tuple[int, int]] = []
        for part in parts:
            position = tuple(int(value) for value in (part.get("position") or (0, 0)))
            rotated_position = rotate_hex(position, steps)
            occupied.append(rotated_position)
            track_hexes = [
                rotate_hex(tuple(int(value) for value in cell), steps)
                for cell in part.get("trackHexes", [])
            ]
            pipe_hexes = [tuple(int(value) for value in cell) for cell in part.get("pipeHexes", [])]
            occupied.extend(
                (rotated_position[0] + cell[0], rotated_position[1] + cell[1])
                for cell in track_hexes
            )
            rotated_part_rotation = (int(part.get("rotation") or 0) + steps) % 6
            occupied.extend(
                (
                    rotated_position[0] + rotate_hex(cell, rotated_part_rotation)[0],
                    rotated_position[1] + rotate_hex(cell, rotated_part_rotation)[1],
                )
                for cell in pipe_hexes
            )
            rotated_parts.append({
                "sourcePartId": str(part.get("id") or ""),
                "type": str(part.get("type") or ""),
                "enabled": bool(part.get("enabled", True)),
                "position": rotated_position,
                "length": int(part.get("length") or 0),
                "rotation": rotated_part_rotation,
                "which": int(part.get("which") or 0),
                "program": _program(part, normalize_time=normalize_time, global_min_cycle=global_min_cycle),
                "trackHexes": track_hexes,
                "pipeId": int(part.get("pipeId") or 0) if part.get("type") == "pipe" else None,
                "pipeHexes": pipe_hexes,
            })

        anchor = min(occupied) if occupied else (0, 0)
        normalized_parts = []
        for part in rotated_parts:
            q, r = part["position"]
            normalized = dict(part)
            normalized["position"] = [q - anchor[0], r - anchor[1]]
            normalized["trackHexes"] = [list(cell) for cell in part["trackHexes"]]
            normalized["pipeHexes"] = [list(cell) for cell in part["pipeHexes"]]
            normalized_parts.append(normalized)

        normalized_parts.sort(key=lambda item: (
            json.dumps(
                {key: value for key, value in item.items() if key != "sourcePartId"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            item["sourcePartId"],
        ))
        identity_free = [
            {key: value for key, value in item.items() if key != "sourcePartId"}
            for item in normalized_parts
        ]
        if identity_free == target.get("parts", []):
            return {
                "puzzleFile": target.get("puzzleFile", ""),
                "parts": normalized_parts,
            }
    raise ValueError("Could not align source part identities with canonical payload")


def canonical_solution_hash(solution: dict[str, Any], *, normalize_time: bool = False) -> str:
    payload = canonical_solution_payload(solution, normalize_time=normalize_time)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
