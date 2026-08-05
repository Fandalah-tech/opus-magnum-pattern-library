# Disjoint solver readiness

This document defines the minimum engine guarantees required before the solver may search puzzles whose logical products contain physically disconnected components.

## Engine invariants

1. Disconnected atoms are independent mechanical components.
2. Grabbing one component never moves another disconnected component.
3. A recent/floating bonder link may exist chemically while remaining excluded from the next physical motion.
4. Once the recent flag is resolved, an ordinary bond transmits motion normally.
5. Product validation must compare the complete logical product, including disconnected components.
6. Search-state hashing must preserve atom identity, element, position, ordinary bonds, and recent/floating bond state.

## Current status

The campaign simulator already models recent/floating bonder links through `floating_bond_roots` and excludes them from `molecule_atom_ids()` during the immediate motion phase.

The first focused regression suite lives in `tests/test_engine_disjoint.py`.

## Remaining work before Van Berlo's Rotor search

- Add a parsed puzzle fixture containing a native three-atom disjoint reagent and disjoint output.
- Confirm output validation accepts the complete disconnected product and rejects partial delivery.
- Add state serialization/hash coverage for recent bonds and disconnected components.
- Add Van Berlo interaction tests where only one disconnected component overlaps a wheel grabber.
- Run the full reference regression and resolve any arm-kinematics/reset divergence before trusting generated paths.
