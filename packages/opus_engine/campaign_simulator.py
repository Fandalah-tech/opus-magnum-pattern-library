from __future__ import annotations

from .final_simulator import Simulator as FinalSimulator


class Simulator(FinalSimulator):
    """Final simulator with OMSim-compatible recent-bond motion semantics."""

    def molecule_atom_ids(self, atom_id: str) -> set[str]:
        if atom_id not in self.world.atoms:
            return {atom_id}

        adjacency: dict[str, set[str]] = {
            item: set() for item in self.world.atoms
        }
        for key, bond in self.world.bonds.items():
            # Bonds created from an overlap on a bonder are RECENT_BONDS in
            # OMSim. They exist chemically, but do not transmit motion during
            # the immediately following motion phase.
            if key in self.floating_bond_roots:
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

    def _settle_floating_bonds(self) -> None:
        # Recent bonds remain excluded through exactly one physical motion.
        # They are normalized immediately after that motion below.
        return

    def _apply_without_wheel_colliders(self, proposals) -> None:
        super()._apply_without_wheel_colliders(proposals)
        if self.floating_bond_roots:
            for key, root_id in list(self.floating_bond_roots.items()):
                bond = self.world.bonds.get(key)
                if bond is not None:
                    self.world.events.append(self._recent_bond_settled_event(bond, root_id))
            self.floating_bond_roots.clear()

    def _recent_bond_settled_event(self, bond, root_id):
        from .world import WorldEvent

        return WorldEvent("floating-bond-settled", self.world.cycle, {
            "fromAtomId": bond.a,
            "toAtomId": bond.b,
            "rootAtomId": root_id,
            "type": bond.kind,
        })
