from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .rotor_blueprint import RotorBlueprint, build_rotor_blueprint


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


def build_rotor_schedule(puzzle: dict[str, Any]) -> RotorSchedule:
    """Build a serial, deliberately unoptimized operation schedule.

    The schedule is an executable-planning intermediate representation.  It
    avoids spatial assumptions: every source atom receives a stable token,
    Van Berlo conversions happen before final bonding, and the six product
    dimers are bonded in an order that progressively connects reagent pulls.
    A later layout compiler maps these operations onto arms and glyphs.
    """
    blueprint: RotorBlueprint = build_rotor_blueprint(puzzle)
    if not blueprint.supported:
        return RotorSchedule(False, blueprint.reason, (), (), (), 0, 0)

    steps: list[RotorStep] = []
    available: set[str] = set()
    source_tokens: list[str] = []

    pulls = sorted({assignment.source.pull_id for assignment in blueprint.assignments})
    for pull_id in pulls:
        assignments = [item for item in blueprint.assignments if item.source.pull_id == pull_id]
        outputs = tuple(
            f"source:{item.source.pull_id}:{item.source.atom_index}"
            for item in sorted(assignments, key=lambda item: item.source.atom_index)
        )
        steps.append(RotorStep(
            len(steps),
            "pull",
            f"Spawn {pull_id}",
            (),
            outputs,
            {"pullId": pull_id, "reagentIndex": assignments[0].source.reagent_index},
        ))
        available.update(outputs)
        source_tokens.extend(outputs)

    target_tokens: dict[str, str] = {}
    for assignment in sorted(blueprint.assignments, key=lambda item: item.target.atom_id):
        source_token = f"source:{assignment.source.pull_id}:{assignment.source.atom_index}"
        target_token = f"target:{assignment.target.atom_id}"
        if assignment.transformation is None:
            steps.append(RotorStep(
                len(steps),
                "route",
                f"Route {source_token} to {assignment.target.atom_id}",
                (source_token,),
                (target_token,),
                {"targetPosition": list(assignment.target.position), "element": assignment.target.target_element},
            ))
        else:
            steps.append(RotorStep(
                len(steps),
                "transform",
                f"Transform {source_token} with Van Berlo",
                (source_token,),
                (target_token,),
                {
                    "glyph": "baron",
                    "targetPosition": list(assignment.target.position),
                    "targetElement": assignment.target.target_element,
                },
            ))
        available.remove(source_token)
        available.add(target_token)
        target_tokens[assignment.target.atom_id] = target_token

    # The blueprint orders bonds so each new edge joins two provenance groups
    # whenever possible. This gives the layout compiler a serial assembly path.
    component_tokens: list[str] = []
    for bond_index, bond in enumerate(blueprint.bonds):
        first = target_tokens[bond.first_target_atom_id]
        second = target_tokens[bond.second_target_atom_id]
        output = f"dimer:{bond_index}"
        steps.append(RotorStep(
            len(steps),
            "bond",
            f"Bond product dimer {bond_index}",
            (first, second),
            (output,),
            {
                "type": "normal",
                "firstTarget": bond.first_target_atom_id,
                "secondTarget": bond.second_target_atom_id,
            },
        ))
        available.discard(first)
        available.discard(second)
        available.add(output)
        component_tokens.append(output)

    isolated = [
        token for atom_id, token in target_tokens.items()
        if all(atom_id not in {bond.first_target_atom_id, bond.second_target_atom_id} for bond in blueprint.bonds)
    ]
    product_tokens = tuple([*component_tokens, *isolated])
    steps.append(RotorStep(
        len(steps),
        "assemble-disjoint",
        "Place all seven product components in the output frame",
        product_tokens,
        ("product:0",),
        {"componentCount": len(product_tokens), "logicalMoleculeRequired": True},
    ))
    steps.append(RotorStep(
        len(steps),
        "deliver",
        "Release complete product",
        ("product:0",),
        ("output:0",),
        {"repeat": 6},
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
