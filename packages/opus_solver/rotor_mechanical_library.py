from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .mechanical_macros import MechanicalMacro


def _arm_id(part: dict[str, Any]) -> str:
    return str(part.get("id") or f"arm-{part.get('armNumber', 0)}")


def compile_program_window(
    solution: dict[str, Any],
    name: str,
    start_cycle: int,
    end_cycle: int,
    *,
    tags: Iterable[str] = (),
) -> MechanicalMacro:
    """Compile a synchronized instruction window into one mechanical macro.

    Empty cycles are retained as empty action frames because glyph processing
    and simultaneous arm timing are cycle-sensitive in OMSIM.
    """
    if start_cycle < 0 or end_cycle < start_cycle:
        raise ValueError("invalid macro cycle window")

    by_cycle: dict[int, dict[str, str]] = defaultdict(dict)
    for part in solution.get("parts", []):
        if part.get("type") not in {"arm", "piston", "baron", "van-berlo"}:
            continue
        arm_id = _arm_id(part)
        for instruction in part.get("program", []):
            cycle = int(instruction.get("cycle", -1))
            if start_cycle <= cycle <= end_cycle:
                opcode = instruction.get("instruction")
                if opcode:
                    by_cycle[cycle][arm_id] = str(opcode)

    actions = [by_cycle.get(cycle, {}) for cycle in range(start_cycle, end_cycle + 1)]
    return MechanicalMacro.from_actions(name, actions, tags=tags)


def learn_program_windows(
    solution: dict[str, Any],
    *,
    lengths: Iterable[int] = (2, 3, 4, 6, 8, 12),
    tag: str = "learned",
) -> tuple[MechanicalMacro, ...]:
    """Generate reusable synchronized windows from a trusted human program."""
    cycles = [
        int(instruction.get("cycle", -1))
        for part in solution.get("parts", [])
        for instruction in part.get("program", [])
        if int(instruction.get("cycle", -1)) >= 0
    ]
    if not cycles:
        return ()
    last_cycle = max(cycles)
    macros: list[MechanicalMacro] = []
    seen: set[tuple[tuple[tuple[str, str], ...], ...]] = set()
    for length in sorted(set(int(value) for value in lengths if int(value) > 0)):
        for start in range(0, last_cycle - length + 2):
            end = start + length - 1
            macro = compile_program_window(
                solution,
                f"{tag}-{start:03d}-{end:03d}",
                start,
                end,
                tags={tag, "mechanical", f"length-{length}"},
            )
            signature = tuple(tuple(sorted(frame.items())) for frame in macro.actions)
            if not any(signature) or signature in seen:
                continue
            seen.add(signature)
            macros.append(macro)
    return tuple(macros)


def build_rotor_seed_macro_library(solution: dict[str, Any]) -> tuple[MechanicalMacro, ...]:
    """Return the first Rotor-specific macro vocabulary from the A42 seed.

    The complete 13-cycle prefix captures the proven confined reorientation and
    hand-off. Short learned windows expose its reusable submotions to macro beam
    search without encoding chemistry or atom identities.
    """
    prefix = compile_program_window(
        solution,
        "rotor-confined-reorientation-prefix",
        0,
        12,
        tags={"rotor", "rotation", "confined", "handoff", "trusted"},
    )
    learned = learn_program_windows(solution, lengths=(2, 3, 4, 6, 8))
    return (prefix, *learned)
