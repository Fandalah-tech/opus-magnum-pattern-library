from __future__ import annotations

from itertools import combinations
from typing import Any

from packages.opus_analysis.canonical import rotate_hex

ARM_TYPES = {"arm1", "arm2", "arm3", "arm6", "piston", "baron"}

# Canonical rotation-zero occupied cells for parts whose physical footprint is
# stable and already used by the project viewer. Unknown parts fall back to the
# anchor cell and are marked approximate rather than treated as exact.
FOOTPRINTS: dict[str, tuple[tuple[int, int], ...]] = {
    "bonder": ((0, 0), (1, 0)),
    "unbonder": ((0, 0), (1, 0)),
    "bonder-speed": ((0, 0), (1, 0), (0, -1), (-1, 1)),
    "glyph-calcification": ((0, 0),),
    "glyph-equilibrium": ((0, 0),),
    "glyph-disposal": ((0, 0), (1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)),
    "glyph-projection": ((0, 0), (1, 0)),
    "glyph-purification": ((0, 0), (1, 0), (2, 0)),
    "glyph-duplication": ((0, 0), (1, 0)),
    "glyph-life-and-death": ((0, 0), (1, 0)),
    "glyph-marker": ((0, 0),),
    "glyph-bonder-prisma": ((0, 0), (1, 0), (0, 1)),
    "glyph-unbonder-prisma": ((0, 0), (1, 0), (0, 1)),
}

BRANCH_OFFSETS = {
    "arm1": (0,),
    "piston": (0,),
    "arm2": (0, 3),
    "arm3": (0, 2, 4),
    "arm6": (0, 1, 2, 3, 4, 5),
    "baron": (0, 1, 2, 3, 4, 5),
}
DIRECTIONS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


def part_occupied_cells(part: dict[str, Any]) -> dict[str, Any]:
    part_type = str(part.get("type") or "")
    origin = tuple(int(value) for value in (part.get("position") or (0, 0)))

    if part_type == "track":
        cells = {
            (origin[0] + int(cell[0]), origin[1] + int(cell[1]))
            for cell in part.get("trackHexes", [])
        }
        return {"cells": cells, "precision": "exact", "source": "serialized-track-cells"}
    if part_type == "pipe":
        rotation = int(part.get("rotation") or 0) % 6
        cells = {
            (
                origin[0] + rotate_hex(tuple(int(value) for value in cell), rotation)[0],
                origin[1] + rotate_hex(tuple(int(value) for value in cell), rotation)[1],
            )
            for cell in part.get("pipeHexes", [])
        }
        if not cells:
            cells = {origin}
        return {"cells": cells, "precision": "exact", "source": "serialized-pipe-cells"}
    if part_type in ARM_TYPES:
        return {"cells": {origin}, "precision": "exact", "source": "arm-base"}

    base = FOOTPRINTS.get(part_type)
    if base is None:
        return {"cells": {origin}, "precision": "anchor-only", "source": "unknown-part-fallback"}

    rotation = int(part.get("rotation") or 0) % 6
    cells = set()
    for local in base:
        rotated = rotate_hex(local, rotation)
        cells.add((origin[0] + rotated[0], origin[1] + rotated[1]))
    return {"cells": cells, "precision": "exact", "source": "known-part-footprint"}


def _overlap_allowed(left: dict[str, Any], right: dict[str, Any]) -> bool:
    types = {str(left.get("type") or ""), str(right.get("type") or "")}
    # An arm base is expected to occupy a rail cell while travelling on track.
    return "track" in types and any(value in ARM_TYPES for value in types)


def arm_workspace_cells(part: dict[str, Any], *, track_cells: set[tuple[int, int]] | None = None) -> set[tuple[int, int]]:
    part_type = str(part.get("type") or "")
    if part_type not in ARM_TYPES:
        return set()

    base_origin = tuple(int(value) for value in (part.get("position") or (0, 0)))
    uses_track = any(str(item.get("instruction") or "").startswith("track_") for item in part.get("program", []))
    origins = set(track_cells or ()) if uses_track and track_cells else {base_origin}
    offsets = BRANCH_OFFSETS.get(part_type, (0,))
    base_length = max(1, int(part.get("length") or 1))
    lengths = range(base_length, 4) if part_type == "piston" else (base_length,)

    cells = set(origins)
    for origin in origins:
        for rotation in range(6):
            for offset in offsets:
                direction = DIRECTIONS[(rotation + offset) % 6]
                for length in lengths:
                    cells.add((origin[0] + direction[0] * length, origin[1] + direction[1] * length))
    return cells


def analyze_layout_geometry(parts: list[dict[str, Any]]) -> dict[str, Any]:
    footprints = {str(part.get("id")): part_occupied_cells(part) for part in parts}
    static_conflicts = []

    for left, right in combinations(parts, 2):
        left_id = str(left.get("id"))
        right_id = str(right.get("id"))
        overlap = footprints[left_id]["cells"] & footprints[right_id]["cells"]
        if not overlap or _overlap_allowed(left, right):
            continue
        exact = footprints[left_id]["precision"] == "exact" and footprints[right_id]["precision"] == "exact"
        static_conflicts.append({
            "leftPartId": left_id,
            "rightPartId": right_id,
            "leftType": left.get("type"),
            "rightType": right.get("type"),
            "cells": [list(cell) for cell in sorted(overlap)],
            "precision": "exact" if exact else "approximate",
        })

    track_cells = {
        cell
        for part in parts
        if part.get("type") == "track"
        for cell in part_occupied_cells(part)["cells"]
    }
    arm_workspaces = {
        str(part.get("id")): arm_workspace_cells(part, track_cells=track_cells)
        for part in parts
        if str(part.get("type") or "") in ARM_TYPES
    }
    workspace_overlaps = []
    arm_parts = [part for part in parts if str(part.get("type") or "") in ARM_TYPES]
    for left, right in combinations(arm_parts, 2):
        left_id = str(left.get("id"))
        right_id = str(right.get("id"))
        overlap = arm_workspaces[left_id] & arm_workspaces[right_id]
        if overlap:
            workspace_overlaps.append({
                "leftPartId": left_id,
                "rightPartId": right_id,
                "cellCount": len(overlap),
                "cells": [list(cell) for cell in sorted(overlap)[:24]],
                "truncated": len(overlap) > 24,
            })

    exact_conflicts = [item for item in static_conflicts if item["precision"] == "exact"]
    approximate_conflicts = [item for item in static_conflicts if item["precision"] != "exact"]
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "partCount": len(parts),
            "exactStaticConflictCount": len(exact_conflicts),
            "approximateStaticConflictCount": len(approximate_conflicts),
            "armWorkspaceOverlapCount": len(workspace_overlaps),
            "knownExactFootprintPartCount": sum(value["precision"] == "exact" for value in footprints.values()),
        },
        "staticConflicts": static_conflicts,
        "armWorkspaceOverlaps": workspace_overlaps,
        "footprints": {
            part_id: {
                "cells": [list(cell) for cell in sorted(value["cells"])],
                "precision": value["precision"],
                "source": value["source"],
            }
            for part_id, value in sorted(footprints.items())
        },
        "limitations": [
            "Arm workspaces are conservative reachable-tip sets, not collision predictions.",
            "Input/output and unknown part footprints remain anchor-only until their exact placement footprint is modeled.",
            "Static conflicts are diagnostics; engine/OMSim validation remains authoritative."
        ],
    }
