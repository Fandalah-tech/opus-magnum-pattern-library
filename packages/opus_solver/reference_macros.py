from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .mechanical_macros import MechanicalMacro


def compile_reference_macro(data: Mapping[str, Any]) -> MechanicalMacro:
    """Compile a versioned human-reference macro document.

    Cycle numbers are metadata only; the compiled macro preserves every cycle,
    including empty instruction frames, so synchronized timing remains exact.
    """
    if data.get("schemaVersion") != "0.1.0":
        raise ValueError(f"unsupported reference macro schema: {data.get('schemaVersion')!r}")
    name = data.get("name")
    cycles = data.get("cycles")
    if not isinstance(name, str) or not name:
        raise ValueError("reference macro name must be a non-empty string")
    if not isinstance(cycles, list) or not cycles:
        raise ValueError("reference macro cycles must be a non-empty list")

    actions: list[dict[str, str]] = []
    previous_cycle: int | None = None
    for row in cycles:
        if not isinstance(row, Mapping):
            raise ValueError("reference macro cycle rows must be objects")
        cycle = row.get("cycle")
        instructions = row.get("instructions", {})
        if not isinstance(cycle, int):
            raise ValueError("reference macro cycle must be an integer")
        if previous_cycle is not None and cycle != previous_cycle + 1:
            raise ValueError("reference macro cycles must be contiguous")
        if not isinstance(instructions, Mapping):
            raise ValueError("reference macro instructions must be an object")
        action: dict[str, str] = {}
        for part_id, instruction in instructions.items():
            if not isinstance(part_id, str) or not isinstance(instruction, str):
                raise ValueError("reference macro instructions must map strings to strings")
            action[part_id] = instruction
        actions.append(action)
        previous_cycle = cycle

    tags = data.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("reference macro tags must be a list of strings")
    return MechanicalMacro.from_actions(name, actions, tags=tags)


def load_reference_macro(path: str | Path) -> MechanicalMacro:
    return compile_reference_macro(json.loads(Path(path).read_text(encoding="utf-8")))
