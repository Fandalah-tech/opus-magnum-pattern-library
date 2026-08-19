from __future__ import annotations

from typing import Any

from .manufacturing_extensions import build_manufacturing_plan


TRANSFORM_GLYPH_EVENTS = {
    "glyph-calcification": "atom-calcified",
    "glyph-duplication": "atom-duplicated",
    "glyph-life-and-death": "atoms-animated",
    "glyph-animismus": "atoms-animated",
    "glyph-projection": "atom-projected",
    "glyph-purification": "atom-purified",
    "glyph-unification": "atoms-unified",
    "glyph-dispersion": "atom-divided",
}

KIND_EVENTS = {
    "duplicate": "atom-duplicated",
    "calcify": "atom-calcified",
    "animate": "atoms-animated",
    "project": "atom-projected",
    "purify": "atom-purified",
    "unify": "atoms-unified",
    "divide": "atom-divided",
}


def required_chemistry_events(puzzle: dict[str, Any]) -> set[str]:
    """Return engine event kinds that prove progress toward the manufacturing plan.

    Generic chemistry plans encode reactions as ``transform`` operations with a
    glyph name, whereas older specialized plans often use reaction-specific
    operation kinds.  Progress scoring must recognize both representations or a
    valid blind search can perform the target chemistry without receiving any
    ranking credit.
    """

    events: set[str] = set()
    plan = build_manufacturing_plan(puzzle)
    for operation in plan.operations:
        kind = str(operation.kind or "")
        glyph = str(operation.glyph or "")
        if kind in {"unbond", "extract"}:
            events.add("bond-removed")
        elif kind == "bond":
            events.update({
                "bond-created",
                "floating-bond-created",
                "floating-bond-settled",
            })
        elif kind == "deliver":
            events.update({"product-delivered", "repeating-product-completed"})
        elif kind in KIND_EVENTS:
            events.add(KIND_EVENTS[kind])
        elif kind == "transform" and glyph in TRANSFORM_GLYPH_EVENTS:
            events.add(TRANSFORM_GLYPH_EVENTS[glyph])
    return events


__all__ = ["required_chemistry_events"]
