from pathlib import Path

PATH = Path("packages/opus_engine/final_simulator.py")
MARKER = '''    def _before_motion(self) -> None:
'''
INSERT = '''    def _disjoint_output_atom_ids(self, expected_atoms, expected_bonds):
        expected_by_position = dict(expected_atoms)
        selected = {}
        for position, element in expected_by_position.items():
            candidates = [
                atom for atom in self._atoms_at(position)
                if not self._is_wheel_atom_id(atom.id)
            ]
            if len(candidates) != 1 or candidates[0].element != element:
                return None
            atom = candidates[0]
            if atom.held_by:
                return None
            selected[position] = atom
        selected_ids = {atom.id for atom in selected.values()}
        expected = {
            (kind, tuple(sorted((start, end))))
            for kind, start, end in expected_bonds
        }
        actual = set()
        for bond in self.world.bonds.values():
            touches = bond.a in selected_ids or bond.b in selected_ids
            if not touches:
                continue
            if bond.a not in selected_ids or bond.b not in selected_ids:
                return None
            first = self.world.atoms[bond.a].position
            second = self.world.atoms[bond.b].position
            actual.add((bond.kind, tuple(sorted((first, second)))))
        if actual != expected:
            return None
        return selected_ids

    def _process_consumers(self) -> None:
        delivered_ids = set()
        for output_id, product_index, expected_atoms, expected_bonds in self.output_patterns:
            atom_ids = self._disjoint_output_atom_ids(expected_atoms, expected_bonds)
            if not atom_ids:
                continue
            delivered_ids.update(atom_ids)
            self.delivered_products[output_id] = self.delivered_products.get(output_id, 0) + 1
            self.world.events.append(WorldEvent("product-delivered", self.world.cycle, {
                "consumerType": "output",
                "consumerPartId": output_id,
                "productIndex": product_index,
                "atomIds": sorted(atom_ids),
                "disjoint": True,
            }))
        if delivered_ids:
            self._remove_molecule(delivered_ids)
        super()._process_consumers()

'''
text = PATH.read_text(encoding="utf-8")
if "def _disjoint_output_atom_ids" in text:
    print("disjoint output patch already present")
elif MARKER not in text:
    raise SystemExit("insertion marker not found")
else:
    PATH.write_text(text.replace(MARKER, INSERT + MARKER, 1), encoding="utf-8")
    print("patched disjoint output consumption")
