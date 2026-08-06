from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .mechanical_macros import MechanicalMacro, MacroGuard


def _compile_guard(data: Mapping[str, Any]) -> MacroGuard | None:
    guard_data = data.get("guard")
    if guard_data is None:
        return None
    if not isinstance(guard_data, Mapping):
        raise ValueError("reference macro guard must be an object")
    arms = guard_data.get("arms", {})
    if not isinstance(arms, Mapping) or not arms:
        raise ValueError("reference macro guard arms must be a non-empty object")

    expected: dict[str, dict[str, Any]] = {}
    allowed_fields = {"origin", "rotation", "length", "trackIndex", "grabbing", "heldBranches"}
    for arm_id, fields in arms.items():
        if not isinstance(arm_id, str) or not isinstance(fields, Mapping):
            raise ValueError("reference macro guard arms must map strings to objects")
        unknown = set(fields) - allowed_fields
        if unknown:
            raise ValueError(f"unknown arm guard fields for {arm_id}: {sorted(unknown)}")
        normalized = dict(fields)
        if "origin" in normalized:
            origin = normalized["origin"]
            if not isinstance(origin, list) or len(origin) != 2 or not all(isinstance(v, int) for v in origin):
                raise ValueError("arm guard origin must contain two integers")
            normalized["origin"] = tuple(origin)
        if "heldBranches" in normalized:
            branches = normalized["heldBranches"]
            if not isinstance(branches, list) or not all(isinstance(v, int) for v in branches):
                raise ValueError("arm guard heldBranches must be a list of integers")
            normalized["heldBranches"] = tuple(sorted(branches))
        expected[arm_id] = normalized

    def guard(simulator: Any) -> bool:
        for arm_id, fields in expected.items():
            arm = getattr(simulator, "arms", {}).get(arm_id)
            if arm is None:
                return False
            actual = {
                "origin": tuple(arm.origin),
                "rotation": arm.rotation,
                "length": arm.length,
                "trackIndex": arm.track_index,
                "grabbing": arm.grabbing,
                "heldBranches": tuple(sorted(arm.held_atoms)),
            }
            if any(actual[field] != value for field, value in fields.items()):
                return False
        return True

    return guard


def compile_reference_macro(data: Mapping[str, Any]) -> MechanicalMacro:
    """Compile a versioned human-reference macro document.

    Cycle numbers are metadata only; the compiled macro preserves every cycle,
    including empty instruction frames, so synchronized timing remains exact.
    Optional mechanical guards prevent a source-specific macro from appearing
    legal in unrelated states where its instructions merely move empty arms.
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
    return MechanicalMacro.from_actions(name, actions, tags=tags, guard=_compile_guard(data))


def load_reference_macro(path: str | Path) -> MechanicalMacro:
    return compile_reference_macro(json.loads(Path(path).read_text(encoding="utf-8")))
