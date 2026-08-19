from __future__ import annotations

import math

from .final_simulator import Simulator as FinalSimulator
from .simulator import SimulationError, Simulator as BaseSimulator
from .world import WorldEvent


_HEX_SIZE_X = 82.0
_HEX_SIZE_Y = 71.0
_ATOM_RADIUS = 29.0
_PRODUCED_ATOM_RADIUS = 15.0
_LINEAR_MOTION = {"track_plus", "track_minus", "extend", "retract", "reset"}


def _to_xy(position) -> tuple[float, float]:
    u, v = int(position[0]), int(position[1])
    return _HEX_SIZE_X * (u + 0.5 * v), _HEX_SIZE_Y * v


def _segment_point_distance(start, end, point) -> float:
    sx, sy = start
    ex, ey = end
    px, py = point
    dx, dy = ex - sx, ey - sy
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(px - sx, py - sy)
    t = ((px - sx) * dx + (py - sy) * dy) / length2
    t = max(0.0, min(1.0, t))
    nearest = (sx + t * dx, sy + t * dy)
    return math.hypot(px - nearest[0], py - nearest[1])


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

    def _freshly_produced_atom_ids(self) -> set[str]:
        """Atoms created in the first half-cycle are smaller motion colliders.

        OMSim does not place conversion products on the board until the second
        half-cycle. During motion it nevertheless inserts a temporary collider
        with radius 15 rather than the normal atom radius 29. Our graph world
        materializes those atoms immediately, so retain their event identities
        and use the authoritative smaller radius during continuous collision
        preflight.
        """
        result: set[str] = set()
        for event in self.world.events:
            data = event.data
            if event.kind in {"atom-purified", "atom-rejected"}:
                atom_id = str(data.get("producedAtomId") or "")
                if atom_id:
                    result.add(atom_id)
            for atom_id in data.get("producedAtomIds", []) or []:
                if atom_id:
                    result.add(str(atom_id))
        return result

    def _validate_continuous_linear_motion(self, proposals) -> None:
        """Check swept atom disks for translational arm motions.

        The older engine only compared final hex occupancy. OMSim samples the
        entire physical movement curve; a carried atom can therefore hit a
        stationary or just-produced atom between legal start/end hexes. Track,
        piston and reset translations are straight lines, so their exact swept
        distance to a fixed atom is cheap to compute here.
        """
        linear = [proposal for proposal in proposals if proposal.instruction in _LINEAR_MOTION]
        if not linear:
            return
        moving_ids = {atom_id for proposal in proposals for atom_id in proposal.atom_ids}
        fresh = self._freshly_produced_atom_ids()
        stationary = [atom for atom in self.world.atoms.values() if atom.id not in moving_ids]

        for proposal in linear:
            for atom_id, destination in proposal.destinations.items():
                atom = self.world.atoms.get(atom_id)
                if atom is None or tuple(atom.position) == tuple(destination):
                    continue
                start_xy = _to_xy(atom.position)
                end_xy = _to_xy(destination)
                for blocker in stationary:
                    blocker_xy = _to_xy(blocker.position)
                    blocker_radius = _PRODUCED_ATOM_RADIUS if blocker.id in fresh else _ATOM_RADIUS
                    threshold = _ATOM_RADIUS + blocker_radius
                    distance = _segment_point_distance(start_xy, end_xy, blocker_xy)
                    if distance + 1e-6 < threshold:
                        label = "freshly produced atom" if blocker.id in fresh else "stationary atom"
                        raise SimulationError(
                            f"Atom {atom_id} sweeps into {label} {blocker.id} at {blocker.position}; "
                            f"instruction={proposal.instruction}; distance={distance:.3f}; threshold={threshold:.3f}"
                        )

    def _validate_and_apply(self, proposals) -> None:
        self._validate_continuous_linear_motion(proposals)
        super()._validate_and_apply(proposals)

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
            self._capture_conduits()
        else:
            self._emit_conduits()
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
