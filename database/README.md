# Canonical puzzle/solution database

The Codex database is metadata-first. Binary `.puzzle` and `.solution` files are not required to live in GitHub.

## Layers

1. `datasets/registry.json` records provenance, authorship, licensing and redistribution policy.
2. Source manifests such as `fixtures/reference/campaign-p007-p015.manifest.json` record trusted puzzle/solution pairs and hashes.
3. `database/schema.json` defines the canonical puzzle and solution records.
4. `tools/build_catalog.py` converts trusted manifests into `database/catalog.json` when a materialized catalog is wanted.

## Identity

Puzzle and solution identity is content-addressed from SHA-256 (`puz-<16 hex>` / `sol-<16 hex>`). Filenames and titles are descriptive metadata and may change without creating duplicates.

## Relationship model

A puzzle may have zero, one or many solutions. Every solution points to exactly one canonical puzzle ID. Metrics belong to the solution, while provenance and redistribution policy are retained on every imported record.

## Validation

Validation is deliberately multi-dimensional. Parser cleanliness, OMSim validation and replay equivalence are independent fields rather than one ambiguous `valid` boolean.

## Next imports

Future corpus importers should emit the same canonical records. This lets campaign fixtures, community datasets, Critelli events and solver-generated solutions coexist in one searchable index without losing provenance.
