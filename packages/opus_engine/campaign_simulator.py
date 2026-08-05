from __future__ import annotations

from .final_simulator import Simulator as FinalSimulator
from .world import WorldEvent


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
        self._resolve_recent_bonds_after_motion()

    def _resolve_recent_bonds_after_motion(self) -> None:
        """Convert one-half-cycle bond flags back to physical bonds.

        OMSim stores bonds as directional bits on atoms. A RECENT_BOND does not
        transmit motion; when one endpoint moves, its bit moves with it rather
        than preserving an impossible long-distance atom-to-atom edge. Our
        graph model therefore keeps the edge only when the original endpoints
        are still adjacent after the motion. Otherwise the stale edge is
        removed.
        """
        for key, root_id in list(self.floating_bond_roots.items()):
            bond = self.world.bonds.get(key)
            if bond is None:
                self.floating_bond_roots.pop(key, None)
                continue
            first = self.world.atoms.get(bond.a)
            second = self.world.atoms.get(bond.b)
            if first is None or second is None:
                self.world.bonds.pop(key, None)
                self.floating_bond_roots.pop(key, None)
                continue

            if self._adjacent_positions(first.position, second.position):
                self.world.events.append(WorldEvent(
                    "floating-bond-settled",
                    self.world.cycle,
                    {
                        "fromAtomId": bond.a,
                        "toAtomId": bond.b,
                        "rootAtomId": root_id,
                        "type": bond.kind,
                    },
                ))
            else:
                self.world.bonds.pop(key, None)
                self.world.events.append(WorldEvent(
                    "floating-bond-dissolved",
                    self.world.cycle,
                    {
                        "fromAtomId": bond.a,
                        "toAtomId": bond.b,
                        "rootAtomId": root_id,
                        "type": bond.kind,
                        "fromPosition": list(first.position),
                        "toPosition": list(second.position),
                    },
                ))
            self.floating_bond_roots.pop(key, None)
