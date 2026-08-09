# Canonical puzzle/solution database

The Codex database is metadata-first. Binary `.puzzle` and `.solution` files are not required to live in GitHub.

## Layers

1. `datasets/registry.json` records provenance, authorship, licensing and redistribution policy.
2. Source manifests such as `fixtures/reference/campaign-p007-p015.manifest.json` record trusted puzzle/solution pairs and hashes.
3. `database/schema.json` defines the canonical puzzle, solution and retrieval records.
4. `tools/build_catalog.py` converts trusted manifests into `database/catalog.json` when a materialized exact-file catalog is wanted.
5. `tools/analyze_solution_archive.py` parses external solution corpora and computes canonical structural/mechanism hashes.
6. `tools/build_solver_index.py` condenses that analysis into `database/solver-index.json`, grouped by puzzle and reusable mechanism.
7. `tools/build_puzzle_feature_index.py` creates a comparable puzzle-side index from chemistry, molecule topology, available parts and Production constraints.
8. `tools/retrieve_mechanisms.py` joins both retrieval indexes and ranks known mechanisms for a target `.puzzle`.

## Identity

Puzzle and exact-solution identity is content-addressed from SHA-256 (`puz-<16 hex>` / `sol-<16 hex>`). Filenames and titles are descriptive metadata and may change without creating duplicates.

Three additional identities are intentionally solver-oriented:

- `canonicalStructuralHash` ignores global translation/rotation while preserving program timing. It identifies the same physical/programmed solution layout in another orientation or position.
- `canonicalMechanismHash` also normalizes program timing. It groups structural/timing variants that implement the same reusable mechanism.
- `puzzleFeatureFingerprint` hashes the solver-relevant puzzle description: reagent/product chemistry, canonical molecule topology, available arms/glyphs, output scale and Production flag.

Molecule fingerprints are invariant to translation and 60-degree rotations on the hex grid. Reflection is intentionally **not** normalized because mirrored molecular topology is not automatically equivalent in Opus Magnum.

## Relationship model

A puzzle may have zero, one or many exact solutions. Every canonical catalog solution points to exactly one canonical puzzle ID. Metrics belong to the solution, while provenance and redistribution policy are retained on every imported record.

The solver index is a retrieval layer rather than a replacement for the exact catalog. For every puzzle/mechanism pair it retains structural diversity, part/arm/instruction ranges, the best known representative for each major metric, and the non-dominated Pareto representatives.

The puzzle feature index is the complementary retrieval layer. It provides a comparable representation for exact feature matches and weighted nearest-neighbour retrieval across different puzzles.

Cross-puzzle retrieval ranks a mechanism in two stages:

1. **Puzzle similarity** compares product and reagent chemistry, molecule identities and sizes, bond structure, available parts, output scale and Production mode.
2. **Mechanism compatibility** checks known required arms/glyphs and Production conduit requirements against the target puzzle. Incompatible candidates are filtered by default.

The returned score is intentionally explainable: every result includes its component similarity scores and any missing required parts.

## Validation

Validation is deliberately multi-dimensional. Parser cleanliness, OMSim validation and replay equivalence are independent fields rather than one ambiguous `valid` boolean.

## Building and using the retrieval indexes

After importing the campaign/reference puzzle corpus and a solution archive:

```powershell
python tools/build_puzzle_feature_index.py
python tools/analyze_solution_archive.py
python tools/build_solver_index.py
python tools/retrieve_mechanisms.py path\to\target.puzzle --limit 25
```

The default materialized indexes are `database/puzzle-feature-index.json` and `database/solver-index.json`. Large generated indexes may be kept outside Git and rebuilt from the source corpora; the schema and builders are the authoritative contract.

## Next database step

Future corpus importers should emit the same canonical records. This lets campaign fixtures, community datasets, Critelli events and solver-generated solutions coexist without losing provenance.

The next useful layer is **mechanism decomposition**: split a canonical solution mechanism into reusable functional fragments (feed, conversion, bonding, transfer, output) so the solver can retrieve and compose sub-mechanisms instead of treating every historical solution as one indivisible template.
