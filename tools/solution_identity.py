from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from packages.opus_parser import parse_solution_bytes

DIRECTIONS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


def _program(part: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in sorted(part.get("program") or [], key=lambda x: int(x.get("cycle", 0))):
        entry = {
            "cycle": int(item.get("cycle", 0)),
            "instruction": str(item.get("instruction") or ""),
        }
        if not entry["instruction"] and item.get("rawCode") is not None:
            entry["rawCode"] = item.get("rawCode")
        out.append(entry)
    return out


def _rotate_direction(rotation: int) -> tuple[int, int]:
    return DIRECTIONS[int(rotation) % 6]


def _cell(q: int, r: int, q0: int, r0: int) -> list[int]:
    return [int(q) - q0, int(r) - r0]


def _canonical_parts(model: dict[str, Any], *, translation_invariant: bool) -> list[dict[str, Any]]:
    parts = list(model.get("parts") or [])
    q0 = r0 = 0
    if translation_invariant and parts:
        positions = [tuple(map(int, p.get("position") or (0, 0))) for p in parts]
        q0 = min(q for q, _ in positions)
        r0 = min(r for _, r in positions)

    canonical: list[dict[str, Any]] = []
    for part in parts:
        part_type = str(part.get("type") or "")
        q, r = map(int, part.get("position") or (0, 0))
        rotation = int(part.get("rotation") or 0) % 6
        enabled = bool(part.get("enabled", True))

        # A bonder/unbonder is mechanically an unordered edge. The game/runtime
        # accepts either endpoint as the serialized origin with the opposite
        # rotation. Normalize both representations to the exact same footprint.
        if part_type in {"bonder", "unbonder"}:
            dq, dr = _rotate_direction(rotation)
            cells = sorted((_cell(q, r, q0, r0), _cell(q + dq, r + dr, q0, r0)))
            canonical.append({"type": part_type, "enabled": enabled, "edge": cells})
            continue

        # These glyphs act on a single cell; their serialized rotation is inert.
        if part_type in {"glyph-calcification", "glyph-disposal"}:
            canonical.append({"type": part_type, "enabled": enabled, "cell": _cell(q, r, q0, r0)})
            continue

        item: dict[str, Any] = {
            "type": part_type,
            "enabled": enabled,
            "position": _cell(q, r, q0, r0),
            "length": int(part.get("length") or 1),
            "rotation": rotation,
            "which": int(part.get("which") or 0),
            "program": _program(part),
        }
        if part_type == "track":
            cells = []
            for cell in part.get("trackHexes") or []:
                cq, cr = map(int, cell)
                cells.append(_cell(cq, cr, q0, r0))
            item["trackHexes"] = sorted(cells)

        # armNumber is deliberately excluded: it is a display/serialization label,
        # not a mechanical degree of freedom. Part order is normalized below.
        canonical.append(item)

    canonical.sort(key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":")))
    return canonical


def canonical_payload(path: Path, *, translation_invariant: bool = False) -> dict[str, Any]:
    model = parse_solution_bytes(path.read_bytes(), source_name=path.name)
    return {
        "puzzleFile": str(model.get("puzzleFile") or ""),
        "parts": _canonical_parts(model, translation_invariant=translation_invariant),
    }


def canonical_id(path: Path, *, translation_invariant: bool = False) -> str:
    payload = canonical_payload(path, translation_invariant=translation_invariant)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def mechanical_id(path: Path) -> str:
    """Identity of the actual mechanism, preserving absolute board coordinates."""
    return canonical_id(path, translation_invariant=False)


def translation_class_id(path: Path) -> str:
    """Diagnostic identity that ignores a uniform axial translation of the whole layout."""
    return canonical_id(path, translation_invariant=True)


def raw_id(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
