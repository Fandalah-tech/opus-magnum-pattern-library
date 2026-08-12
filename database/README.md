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
10. `tools/audit_triplex_corpus.py` classifies collision-aware engine outcomes and exposes durable failure categories.
11. `tools/build_engine_fragment_flow_index.py` promotes only engine-complete traces into reusable, channel-aware fragment transitions.

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

The structural fragment layer identifies plausible reusable neighborhoods without claiming that a molecule traverses every structural edge. The engine fragment-flow layer now promotes only collision-aware, output-complete traces. Its transitions retain geometry, timing, solution breadth and exact red/black/yellow triplex events. The composition planner can require a minimum number of engine-validated source solutions, so unvalidated structural frequency cannot outrank proven evidence by accident.

## Building the database layers

```powershell
python tools/build_puzzle_feature_index.py
python tools/analyze_solution_archive.py
python tools/build_solver_index.py
python tools/build_fragment_index.py
python tools/audit_triplex_corpus.py --puzzle-root <puzzles> --solution-root <solutions> --output <audit.json> --report <audit.txt>
python tools/build_engine_fragment_flow_index.py --audit <audit.json> --output <engine-flow.json>
python tools/retrieve_mechanisms.py path\to\target.puzzle --limit 25
```

Default generated outputs are `database/puzzle-feature-index.json`, `database/solver-index.json` and `database/fragment-index.json`. Large indexes may remain outside Git and be rebuilt from source corpora.

## Next database step

The next major milestone is **closed-loop fragment assembly**: materialize the engine-validated chains as candidate layouts, replay them, and feed their outcomes back into geometry and scheduling repair. The evidence and ranking layers are now in place; the remaining step is autonomous layout mutation rather than additional structural indexing.
