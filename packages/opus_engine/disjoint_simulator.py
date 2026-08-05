from __future__ import annotations

from .campaign_simulator import Simulator as CampaignSimulator


class Simulator(CampaignSimulator):
    """Campaign simulator with native disjoint-molecule identity.

    Parsed reagent and product molecules may contain several disconnected bond
    components. The whole logical molecule moves as one object until a
    successful debond asks ``World`` to rebuild it from the remaining bond
    graph. Recent bonder-overlap bonds retain the existing one-motion
    exception.
    """

    def molecule_atom_ids(self, atom_id: str) -> set[str]:
        logical = self.world.molecule_atom_ids(atom_id)
        if not logical:
            return {atom_id}

        recent_keys = {
            key for key in self.floating_bond_roots
            if key in self.world.bonds
            and self.world.bonds[key].a in logical
            and self.world.bonds[key].b in logical
        }
        if not recent_keys:
            return logical

        adjacency: dict[str, set[str]] = {item: set() for item in logical}
        for key, bond in self.world.bonds.items():
            if key in recent_keys or bond.a not in logical or bond.b not in logical:
                continue
            adjacency[bond.a].add(bond.b)
            adjacency[bond.b].add(bond.a)

        component = {atom_id}
        stack = [atom_id]
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, ()):
                if neighbor not in component:
                    component.add(neighbor)
                    stack.append(neighbor)
        return component
