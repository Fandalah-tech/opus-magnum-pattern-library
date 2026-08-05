from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .rotor_blueprint import RotorBlueprint, build_connected_rotor_blueprint


@dataclass(frozen=True, slots=True)
class RotorStep:
    index: int
    kind: str
    label: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RotorSchedule:
    supported: bool
    reason: str | None
    steps: tuple[RotorStep, ...]
    source_tokens: tuple[str, ...]
    product_tokens: tuple[str, ...]
    transformation_steps: int
    bond_steps: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pos(value: Any) -> tuple[int, int]:
    raw = value or (0, 0)
    return int(raw[0]), int(raw[1])


def build_rotor_schedule(puzzle: dict[str, Any]) -> RotorSchedule:
    """Build a serial, deliberately unoptimized operation schedule.

    This is the bridge between the chemistry blueprint and a future spatial
    compiler. It names every source atom, every Van Berlo conversion, each of
    the six final dimers, and the final seven-component output placement.
    """
    blueprint: RotorBlueprint = build_connected_rotor_blueprint(puzzle)
    if not blueprint.supported:
        return RotorSchedule(False, blueprint.reason, (), (), (), 0, 0)

    products = list(puzzle.get("products") or [])
    if len(products) != 1:
        return RotorSchedule(False, "Rotor schedule requires exactly one product", (), (), (), 0, 0)
    product = products[0]

    steps: list[RotorStep] = []
    source_tokens: list[str] = []
    pulls = sorted({atom.pull_id for atom in blueprint.atoms})
    for pull_id in pulls:
        atoms = sorted(
            (atom for atom in blueprint.atoms if atom.pull_id == pull_id),
            key=lambda item: item.source_atom_index,
        )
        outputs = tuple(f"source:{pull_id}:{atom.source_atom_index}" for atom in atoms)
        reagent_index = int(pull_id[1])
        steps.append(RotorStep(
            len(steps), "pull", f"Spawn {pull_id}", (), outputs,
            {"pullId": pull_id, "reagentIndex": reagent_index},
        ))
        source_tokens.extend(outputs)

    target_by_position: dict[tuple[int, int], str] = {}
    for index, atom in enumerate(sorted(blueprint.atoms, key=lambda item: item.target_position)):
        source = f"source:{atom.pull_id}:{atom.source_atom_index}"
        target = f"target:{index}"
        kind = "transform" if atom.transformation else "route"
        steps.append(RotorStep(
            len(steps),
            kind,
            f"{'Transform' if atom.transformation else 'Route'} {source}",
            (source,),
            (target,),
            {
                "pullId": atom.pull_id,
                "sourceAtomIndex": atom.source_atom_index,
                "targetPosition": list(atom.target_position),
                "targetElement": atom.target_element,
                "glyph": "baron" if atom.transformation else None,
            },
        ))
        target_by_position[atom.target_position] = target

    bonded_positions: set[tuple[int, int]] = set()
    dimers: list[str] = []
    for bond_index, bond in enumerate(product.get("bonds") or []):
        first_position = _pos(bond.get("from"))
        second_position = _pos(bond.get("to"))
        first = target_by_position[first_position]
        second = target_by_position[second_position]
        output = f"dimer:{bond_index}"
        steps.append(RotorStep(
            len(steps), "bond", f"Bond final dimer {bond_index}",
            (first, second), (output,),
            {
                "type": str(bond.get("type") or "normal"),
                "firstPosition": list(first_position),
                "secondPosition": list(second_position),
            },
        ))
        bonded_positions.update((first_position, second_position))
        dimers.append(output)

    isolated = [
        token for position, token in target_by_position.items()
        if position not in bonded_positions
    ]
    product_tokens = tuple([*dimers, *isolated])
    steps.append(RotorStep(
        len(steps), "assemble-disjoint",
        "Place all seven product components in the output frame",
        product_tokens, ("product:0",),
        {"componentCount": len(product_tokens), "logicalMoleculeRequired": True},
    ))
    steps.append(RotorStep(
        len(steps), "deliver", "Release complete product",
        ("product:0",), ("output:0",), {"repeat": 6},
    ))

    return RotorSchedule(
        True,
        None,
        tuple(steps),
        tuple(source_tokens),
        product_tokens,
        sum(step.kind == "transform" for step in steps),
        sum(step.kind == "bond" for step in steps),
    )
