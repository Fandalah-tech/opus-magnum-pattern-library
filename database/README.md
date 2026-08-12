# Canonical puzzle/solution database

The Codex database is metadata-first. Binary `.puzzle` and `.solution` files are not required to live in GitHub.

## Layers

1. `datasets/registry.json` records provenance, authorship, licensing and redistribution policy.
2. Source manifests record trusted puzzle/solution pairs and hashes.
3. `database/schema.json` defines canonical puzzle, solution and retrieval records.
4. `tools/build_catalog.py` materializes exact-file metadata.
5. `tools/analyze_solution_archive.py` computes canonical full-solution hashes.
6. `tools/build_solver_index.py` groups full reusable mechanisms.
7. `tools/build_puzzle_feature_index.py` creates comparable puzzle-side fingerprints.
8. `tools/retrieve_mechanisms.py` ranks full mechanisms for a target puzzle.
9. `tools/build_fragment_index.py` decomposes historical solutions into reusable local functional fragments.

## Solver-oriented identities

- `canonicalStructuralHash` ignores global translation/rotation while preserving program timing.
- `canonicalMechanismHash` also normalizes program timing.
- `puzzleFeatureFingerprint` hashes solver-relevant reagent/product chemistry, canonical molecule topology, available parts, output scale and Production constraints.

Molecule fingerprints are invariant to translation and 60-degree rotations; reflection is intentionally preserved. Triplex red, black and yellow channels are part of the molecule identity, so feature indexes created before schema `0.2.0` should be rebuilt.

## Cross-puzzle retrieval

Cross-puzzle retrieval combines **puzzle similarity** with **mechanism compatibility**. Similarity compares chemistry, molecular topology, atom/bond counts and puzzle constraints. Compatibility checks known required parts and Production conduits. Incompatible mechanisms are filtered by default, and every score remains explainable through its component scores.

## Functional fragment index

Whole historical solutions are useful references but are too coarse for composition. The fragment index therefore extracts local sub-mechanisms around semantic anchors:

- `feed`: input handling;
- `output`: delivery to product outputs;
- `bonding`: bonders/unbonders/multibonders/triplex bonders;
- `conversion`: calcification, duplication, projection, purification, animismus, unification and dispersion;
- `disposal`: disposal glyph interactions;
- `conduit`: Production pipes;
- `process`: future or currently unclassified functional parts.

Each anchor is bundled with arms structurally capable of reaching it and the local rails used by those arms. The resulting fragment is canonicalized independently of its source puzzle and grouped by `(role, canonicalMechanismHash)`. The index tracks occurrence frequency, source-puzzle diversity, structural variants and source samples.

This first fragment layer is intentionally structural. It identifies plausible reusable neighborhoods without claiming that a molecule actually traverses every structural edge. Cycle-accurate simulation traces will later promote structural candidates into confirmed flow fragments.

## Building the database layers

```powershell
python tools/build_puzzle_feature_index.py
python tools/analyze_solution_archive.py
python tools/build_solver_index.py
python tools/build_fragment_index.py
python tools/retrieve_mechanisms.py path\to\target.puzzle --limit 25
```

Default generated outputs are `database/puzzle-feature-index.json`, `database/solver-index.json` and `database/fragment-index.json`. Large indexes may remain outside Git and be rebuilt from source corpora.

## Next database step

The next major milestone is **trace-confirmed fragment learning**: feed real simulator/replay traces into the fragment layer to identify actual molecule transfers between input, conversion, bonding, transfer and output stages. Once those dynamic edges exist, the solver can begin composing candidate solution graphs from independently reusable fragments rather than cloning historical layouts.
