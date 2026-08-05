from __future__ import annotations

from collections.abc import Hashable
from typing import Any


def _atom_rows(simulator: Any) -> tuple[tuple[Hashable, ...], dict[str, int]]:
    """Return identity-independent atom rows and an atom-id to row-index map.

    Solver deduplication must not depend on generated atom ids. Two states with
    the same board geometry, chemistry, grabs, and special wheel layer should
    compare equal even when their atoms were spawned in a different order.
    """
    decorated = []
    for atom in simulator.world.atoms.values():
        decorated.append((
            (
                int(atom.position[0]),
                int(atom.position[1]),
                str(atom.element),
                tuple(sorted(str(item) for item in atom.held_by)),
                bool(getattr(simulator, "_is_wheel_atom_id", lambda _item: False)(atom.id)),
            ),
            str(atom.id),
        ))
    decorated.sort(key=lambda item: (item[0], item[1]))

    rows: list[tuple[Hashable, ...]] = []
    id_to_index: dict[str, int] = {}
    for index, (row, atom_id) in enumerate(decorated):
        rows.append(row)
        id_to_index[atom_id] = index
    return tuple(rows), id_to_index


def canonical_state_key(simulator: Any) -> tuple[Hashable, ...]:
    """Build a deterministic search key for a simulator state.

    The key captures both chemical and mechanical state. In particular, recent
    or floating bonds are represented separately from ordinary bonds: they are
    chemically present but do not transmit motion during the next movement.
    This distinction is required for safe state deduplication around disjoint
    bonder interactions.
    """
    atoms, atom_index = _atom_rows(simulator)

    bonds = []
    for key, bond in simulator.world.bonds.items():
        first = atom_index[str(bond.a)]
        second = atom_index[str(bond.b)]
        bonds.append((min(first, second), max(first, second), str(bond.kind)))
    bonds.sort()

    recent = []
    for key, root_id in getattr(simulator, "floating_bond_roots", {}).items():
        bond = simulator.world.bonds.get(key)
        if bond is None or root_id not in atom_index:
            continue
        first = atom_index[str(bond.a)]
        second = atom_index[str(bond.b)]
        recent.append((
            min(first, second),
            max(first, second),
            str(bond.kind),
            atom_index[str(root_id)],
        ))
    recent.sort()

    pending = []
    for pair, root_id in getattr(simulator, "pending_floating_pairs", {}).items():
        pair_ids = sorted(str(item) for item in pair if str(item) in atom_index)
        if len(pair_ids) != 2 or str(root_id) not in atom_index:
            continue
        first = atom_index[pair_ids[0]]
        second = atom_index[pair_ids[1]]
        pending.append((min(first, second), max(first, second), atom_index[str(root_id)]))
    pending.sort()

    arms = []
    for arm in sorted(simulator.arms.values(), key=lambda item: str(item.id)):
        held = tuple(
            (int(branch), atom_index[str(atom_id)])
            for branch, atom_id in sorted(arm.held_atoms.items())
            if str(atom_id) in atom_index
        )
        arms.append((
            str(arm.id),
            str(arm.part_type),
            (int(arm.origin[0]), int(arm.origin[1])),
            int(arm.rotation) % 6,
            int(arm.length),
            bool(arm.grabbing),
            held,
            int(arm.track_index),
        ))

    inputs = tuple(
        (
            str(source.id),
            int(getattr(source, "spawn_count", 0)),
        )
        for source in sorted(getattr(simulator, "inputs", ()), key=lambda item: str(item.id))
    )
    delivered = tuple(sorted(
        (str(part_id), int(count))
        for part_id, count in getattr(simulator, "delivered_products", {}).items()
    ))
    repeating = tuple(sorted(str(item) for item in getattr(
        simulator, "completed_repeating_outputs", set()
    )))

    return (
        atoms,
        tuple(bonds),
        tuple(recent),
        tuple(pending),
        tuple(arms),
        inputs,
        delivered,
        repeating,
        int(getattr(simulator, "_glyph_generation", 0)),
    )
