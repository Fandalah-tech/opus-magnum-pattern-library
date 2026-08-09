# Canonical puzzle/solution database

The Codex database is metadata-first. Binary `.puzzle` and `.solution` files are not required to live in GitHub.

## Layers

1. `datasets/registry.json` records provenance, authorship, licensing and redistribution policy.
2. Source manifests such as `fixtures/reference/campaign-p007-p015.manifest.json` record trusted puzzle/solution pairs and hashes.
3. `database/schema.json` defines the canonical puzzle, solution and solver-index records.
4. `tools/build_catalog.py` converts trusted manifests into `database/catalog.json` when a materialized exact-file catalog is wanted.
5. `tools/analyze_solution_archive.py` parses external solution corpora and computes canonical structural/mechanism hashes.
6. `tools/build_solver_index.py` condenses that analysis into `database/solver-index.json`, grouped by puzzle and reusable mechanism.

## Identity

Puzzle and exact-solution identity is content-addressed from SHA-256 (`puz-<16 hex>` / `sol-<16 hex>`). Filenames and titles are descriptive metadata and may change without creating duplicates.

Two additional identities are intentionally solver-oriented:

- `canonicalStructuralHash` ignores global translation/rotation while preserving program timing. It identifies the same physical/programmed solution layout in another orientation or position.
- `canonicalMechanismHash` also normalizes program timing. It groups structural/timing variants that implement the same reusable mechanism.

## Relationship model

A puzzle may have zero, one or many exact solutions. Every canonical catalog solution points to exactly one canonical puzzle ID. Metrics belong to the solution, while provenance and redistribution policy are retained on every imported record.

The solver index is a retrieval layer rather than a replacement for the exact catalog. For every puzzle/mechanism pair it retains structural diversity, part/arm/instruction ranges, the best known representative for each major metric, and the non-dominated Pareto representatives.

## Validation

Validation is deliberately multi-dimensional. Parser cleanliness, OMSim validation and replay equivalence are independent fields rather than one ambiguous `valid` boolean.

## Building the solver index

After importing and analyzing a solution archive:

```powershell
python tools/analyze_solution_archive.py
python tools/build_solver_index.py
```

The default output is `database/solver-index.json`. Large generated indexes may be kept outside Git and rebuilt from the source analysis; the schema and builder are the authoritative contract.

## Next imports

Future corpus importers should emit the same canonical records. This lets campaign fixtures, community datasets, Critelli events and solver-generated solutions coexist in one searchable index without losing provenance. The next database layer should add puzzle-side feature fingerprints so mechanisms can be retrieved across *similar* puzzles, not only by exact puzzle identity.
