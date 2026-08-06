from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Atom, Bond, Hex
from .world import World, WorldEvent

DIRECTIONS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


def add_hex(a: Hex, b: Hex) -> Hex:
    return a[0] + b[0], a[1] + b[1]


def rotate_hex(position: Hex, steps: int) -> Hex:
    q, r = position
    for _ in range(steps % 6):
        q, r = -r, q + r
    return q, r


@dataclass(slots=True)
class InputSource:
    id: str
    atom_templates: tuple[tuple[str, Hex], ...]
    bond_templates: tuple[tuple[int, int, str], ...]
    spawn_count: int = 0

    @property
    def footprint(self) -> tuple[Hex, ...]:
        return tuple(position for _, position in self.atom_templates)

    def is_clear(self, world: World) -> bool:
        return all(world.atom_at(position) is None for position in self.footprint)

    def _components(self) -> tuple[tuple[int, ...], ...]:
        adjacency = {index: set() for index in range(len(self.atom_templates))}
        for first, second, _ in self.bond_templates:
            adjacency[first].add(second)
            adjacency[second].add(first)

        components: list[tuple[int, ...]] = []
        unseen = set(adjacency)
        while unseen:
            root = min(unseen)
            stack = [root]
            component: set[int] = set()
            while stack:
                current = stack.pop()
                if current in component:
                    continue
                component.add(current)
                unseen.discard(current)
                stack.extend(adjacency[current] - component)
            components.append(tuple(sorted(component)))
        return tuple(components)

    def spawn(self, world: World) -> bool:
        clear_components = [
            component
            for component in self._components()
            if all(world.atom_at(self.atom_templates[index][1]) is None for index in component)
        ]
        if not clear_components:
            return False

        generation = self.spawn_count
        spawned_ids: list[str] = []
        for component in clear_components:
            atom_ids: dict[int, str] = {}
            for index in component:
                element, position = self.atom_templates[index]
                atom_id = f"{self.id}-spawn-{generation}-atom-{index}"
                world.add_atom(Atom(atom_id, element, position))
                atom_ids[index] = atom_id
                spawned_ids.append(atom_id)

            for first, second, kind in self.bond_templates:
                if first in atom_ids and second in atom_ids:
                    world.add_bond(Bond(atom_ids[first], atom_ids[second], kind))

        # A reagent may contain several disconnected molecules. Each connected
        # component respawns as soon as its own source cells are clear, matching
        # the game's independent component behaviour.
        self.spawn_count += 1
        world.events.append(WorldEvent("input-spawned", world.cycle, {
            "inputId": self.id,
            "generation": generation,
            "atomIds": spawned_ids,
        }))
        return True


def build_input_sources(puzzle: dict[str, Any], solution: dict[str, Any]) -> list[InputSource]:
    reagents = puzzle.get("reagents", [])
    sources: list[InputSource] = []

    for part in solution.get("parts", []):
        if part.get("type") != "input":
            continue
        reagent_index = int(part.get("which") or 0)
        if reagent_index < 0 or reagent_index >= len(reagents):
            continue

        reagent = reagents[reagent_index]
        origin = tuple(part.get("position") or (0, 0))
        rotation = int(part.get("rotation") or 0)
        local_atoms = list(reagent.get("atoms", []))
        local_index = {
            tuple(atom.get("position") or (0, 0)): index
            for index, atom in enumerate(local_atoms)
        }
        atom_templates = tuple(
            (
                str(atom.get("element")),
                add_hex(origin, rotate_hex(tuple(atom.get("position") or (0, 0)), rotation)),
            )
            for atom in local_atoms
        )
        bond_templates = tuple(
            (
                local_index[tuple(bond.get("from") or (0, 0))],
                local_index[tuple(bond.get("to") or (0, 0))],
                str(bond.get("type") or "normal"),
            )
            for bond in reagent.get("bonds", [])
            if tuple(bond.get("from") or (0, 0)) in local_index
            and tuple(bond.get("to") or (0, 0)) in local_index
        )
        sources.append(InputSource(
            id=str(part.get("id") or f"input-{len(sources)}"),
            atom_templates=atom_templates,
            bond_templates=bond_templates,
        ))

    return sources


def build_initial_world(puzzle: dict[str, Any], solution: dict[str, Any]) -> World:
    """Create cycle-zero atoms for every input from canonical parser models."""
    world = World()
    for source in build_input_sources(puzzle, solution):
        source.spawn(world)
    world.events = []
    return world
