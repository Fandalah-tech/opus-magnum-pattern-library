from __future__ import annotations

from .final_simulator import Simulator as FinalSimulator
from .simulator import Simulator as BaseSimulator
from .world import WorldEvent


class Simulator(FinalSimulator):
    """Final simulator with OMSim-compatible half-cycle and recent-bond semantics."""

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

    def _run_campaign_glyph_phase(self, *, allow_conversion_inputs: bool) -> None:
        """Apply one OMSim half-cycle of inputs, glyphs and consumers.

        Inputs, instantaneous glyphs, disposal and outputs update in both
        half-cycles. Animismus and purification only accept fresh conversion
        inputs in the first half-cycle; their products are created immediately
        by this object model, so the second phase must not consume another pair.
        """
        BaseSimulator._respawn_inputs(self)
        self._process_calcification()
        self._process_duplication()
        if allow_conversion_inputs:
            self._process_animismus()
        self._process_basic_glyphs()
        self._mark_pending_floating_bonds()
        self._process_projection()
        self._process_rejection()
        if allow_conversion_inputs:
            self._process_purification()
            self._process_division()
            self._process_unification()
            self._process_proliferation()
        self._latch_repeating_outputs()
        self._process_consumers()

    def _before_motion(self) -> None:
        # OMSim's first half-cycle occurs after grab/drop and before physical
        # arm motion. This is essential for solutions that produce or consume
        # atoms between those two instruction phases.
        self._settle_floating_bonds()
        self._run_campaign_glyph_phase(allow_conversion_inputs=True)

    def _respawn_inputs(self) -> None:
        # The second half-cycle runs after physical motion. Conversion glyphs
        # cannot accept a second input pair here, but all instantaneous glyphs,
        # inputs and consumers update again.
        self._run_campaign_glyph_phase(allow_conversion_inputs=False)
