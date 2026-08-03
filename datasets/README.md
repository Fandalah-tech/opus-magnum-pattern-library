# Dataset intake

The dataset directory is a provenance registry, not a blanket mirror of community files.

## Rules

1. Every imported puzzle or solution must identify its source and author when known.
2. License status must be recorded before redistribution.
3. Sources without explicit redistribution terms remain external and are downloaded only in controlled development or CI environments.
4. Every imported binary file receives a SHA-256 hash and stable dataset identifier.
5. Generated derivatives retain links to the source puzzle, generator, validator version and generation parameters.
6. Game-owned campaign or journal data is never assumed to be freely redistributable.

## Status values

- `source-confirmed-download-pending`: source exists, archive not yet ingested.
- `repository-confirmed-inventory-pending`: repository exists, individual files still require review.
- `external-ready`: downloader and checksums are available, but files are not committed.
- `redistributable`: license review permits committing the files with required notices.
- `blocked`: source, permission, integrity or format problem prevents use.

## Initial strategy

The 24 Hour Challenge archives are the best public benchmark candidates because they were explicitly created for automated solving and validation. Until an explicit redistribution license is located, the project will reference and optionally download them rather than store their contents in this repository.

omsim and OpusSolver repositories will provide behavior and regression references. Code-license permission does not automatically settle the status of any bundled Zachtronics puzzle data, so each fixture is reviewed separately.
