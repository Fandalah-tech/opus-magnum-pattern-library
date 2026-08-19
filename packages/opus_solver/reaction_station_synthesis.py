from __future__ import annotations

from copy import deepcopy
from typing import Any


def _next_part_id(solution: dict[str, Any], prefix: str) -> str:
    existing = {str(part.get("id") or "") for part in solution.get("parts", []) or []}
    serial = 0
    while f"{prefix}-{serial}" in existing:
        serial += 1
    return f"{prefix}-{serial}"


def add_static_glyph(
    solution: dict[str, Any],
    *,
    part_type: str,
    origin: list[int] | tuple[int, int],
    rotation: int,
    prefix: str,
) -> tuple[dict[str, Any], str]:
    """Append one static glyph without perturbing inherited mechanism timing."""

    result = deepcopy(solution)
    part_id = _next_part_id(result, prefix)
    result.setdefault("parts", []).append({
        "id": part_id,
        "type": str(part_type),
        "enabled": True,
        "position": [int(origin[0]), int(origin[1])],
        "length": 1,
        "rotation": int(rotation) % 6,
        "which": 0,
        "armNumber": 0,
        "program": [],
    })
    return result, part_id


def add_purification_station(
    solution: dict[str, Any],
    opportunity: dict[str, Any],
    *,
    unbond_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add a purifier and every unbonder needed to free its blocked input atom.

    Earlier repair stages moved inherited glyphs.  That is sufficient for a
    first reaction, but later metal stages can require the original stations to
    keep producing their own intermediates.  This constructor instead adds a
    new static reaction station and, when requested, one unbonder for each
    distinct bond touching the blocked conversion atom.  All geometry is taken
    from generated replay evidence.
    """

    result = deepcopy(solution)
    added_unbonders: list[str] = []
    seen_bonds: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for candidate in unbond_candidates or []:
        first = tuple(int(value) for value in (candidate.get("origin") or (0, 0)))
        second = tuple(int(value) for value in (candidate.get("second") or (0, 0)))
        bond_key = tuple(sorted((first, second)))
        if bond_key in seen_bonds:
            continue
        seen_bonds.add(bond_key)
        result, part_id = add_static_glyph(
            result,
            part_type="unbonder",
            origin=first,
            rotation=int(candidate.get("rotation") or 0),
            prefix="synth-unbonder",
        )
        added_unbonders.append(part_id)

    result, purifier_id = add_static_glyph(
        result,
        part_type="glyph-purification",
        origin=opportunity.get("origin") or (0, 0),
        rotation=int(opportunity.get("rotation") or 0),
        prefix="synth-purifier",
    )
    source = result.setdefault("source", {})
    source["generator"] = "opus_solver/additive-purification-station-v1"
    source.setdefault("additivePurificationStations", []).append({
        "purifierPartId": purifier_id,
        "unbonderPartIds": added_unbonders,
        "producedElement": str(opportunity.get("producedElement") or ""),
        "opportunity": deepcopy(opportunity),
        "unbondCandidates": deepcopy(unbond_candidates or []),
        "targetSolutionBytesUsed": 0,
    })
    return result


__all__ = [
    "add_purification_station",
    "add_static_glyph",
]
