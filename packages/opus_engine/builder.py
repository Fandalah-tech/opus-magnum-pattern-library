from __future__ import annotations

from itertools import count
from typing import Any

from .model import Atom, Bond
from .world import World

DIRECTIONS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


def add_hex(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    return a[0] + b[0], a[1] + b[1]


def rotate_hex(position: tuple[int, int], steps: int) -> tuple[int, int]:
    q, r = position
    for _ in range(steps % 6):
        q, r = -r, q + r
    return q, r


def build_initial_world(puzzle: dict[str, Any], solution: dict[str, Any]) -> World:
    """Create cycle-zero atoms for every input from canonical parser models."""
    world = World()
    serial = count()
    reagents = puzzle.get("reagents", [])

    for part in solution.get("parts", []):
        if part.get("type") != "input":
            continue
        reagent_index = int(part.get("which") or 0)
        if reagent_index < 0 or reagent_index >= len(reagents):
            continue

        reagent = reagents[reagent_index]
        origin = tuple(part.get("position") or (0, 0))
        rotation = int(part.get("rotation") or 0)
        local_to_id: dict[tuple[int, int], str] = {}

        for source_atom in reagent.get("atoms", []):
            local = tuple(source_atom.get("position") or (0, 0))
            position = add_hex(origin, rotate_hex(local, rotation))
            atom_id = f"atom-{next(serial)}"
            world.add_atom(Atom(atom_id, str(source_atom.get("element")), position))
            local_to_id[local] = atom_id

        for source_bond in reagent.get("bonds", []):
            local_a = tuple(source_bond.get("from") or (0, 0))
            local_b = tuple(source_bond.get("to") or (0, 0))
            if local_a in local_to_id and local_b in local_to_id:
                world.add_bond(Bond(
                    local_to_id[local_a],
                    local_to_id[local_b],
                    str(source_bond.get("type") or "normal"),
                ))

    return world
