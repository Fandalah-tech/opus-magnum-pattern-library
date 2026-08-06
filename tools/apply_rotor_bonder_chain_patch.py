from pathlib import Path

PATH = Path("packages/opus_engine/final_simulator.py")
OLD = '''    def _translate_stationary_component(self, stationary_id, occupied_pos, free_pos, moving_atoms):
        component = self.molecule_atom_ids(stationary_id)
        if component & moving_atoms:
            return False
        dq = free_pos[0] - occupied_pos[0]
        dr = free_pos[1] - occupied_pos[1]
        targets = {atom_id: (self.world.atoms[atom_id].position[0] + dq, self.world.atoms[atom_id].position[1] + dr) for atom_id in component}
        outsiders = {
            atom.position: atom.id
            for atom in self.world.atoms.values()
            if atom.id not in component and atom.id not in moving_atoms and not self._is_wheel_atom_id(atom.id)
        }
        if any(position in outsiders for position in targets.values()):
            return False
        for atom_id, position in targets.items():
            self.world.atoms[atom_id].position = position
        return True
'''
NEW = '''    def _translate_stationary_component(self, stationary_id, occupied_pos, free_pos, moving_atoms):
        dq = free_pos[0] - occupied_pos[0]
        dr = free_pos[1] - occupied_pos[1]
        queued = [stationary_id]
        components: list[set[str]] = []
        selected: set[str] = set()
        while queued:
            root = queued.pop()
            if root in selected:
                continue
            component = self.molecule_atom_ids(root)
            if component & moving_atoms:
                return False
            components.append(component)
            selected.update(component)
            targets = {
                (self.world.atoms[atom_id].position[0] + dq, self.world.atoms[atom_id].position[1] + dr)
                for atom_id in component
            }
            for atom in self.world.atoms.values():
                if atom.id in selected or atom.id in moving_atoms or self._is_wheel_atom_id(atom.id):
                    continue
                if atom.position in targets:
                    queued.append(atom.id)
        destinations = {
            atom_id: (
                self.world.atoms[atom_id].position[0] + dq,
                self.world.atoms[atom_id].position[1] + dr,
            )
            for component in components
            for atom_id in component
        }
        if len(set(destinations.values())) != len(destinations):
            return False
        for atom_id, position in destinations.items():
            self.world.atoms[atom_id].position = position
        self.world.events.append(WorldEvent("bonder-chain-shifted", self.world.cycle, {
            "rootAtomId": stationary_id,
            "atomIds": sorted(destinations),
            "delta": [dq, dr],
        }))
        return True
'''
text = PATH.read_text(encoding="utf-8")
if OLD not in text:
    raise SystemExit("target helper block not found")
PATH.write_text(text.replace(OLD, NEW), encoding="utf-8")
print("patched recursive bonder chain displacement")
