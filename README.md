# Opus Magnum Pattern Library

A reusable knowledge base and engineering toolkit for **Opus Magnum** mechanisms, solution analysis, exact simulation, and automated solving.

## Current status

The project has moved beyond the original static pattern explorer and now includes a complete Python toolchain:

- binary `.puzzle` and `.solution` parsers;
- a version 7 `.solution` serializer;
- an experimental simulator covering the campaign mechanics used by the corpus;
- program-tape decoding, including repeats and physical reset expansion;
- collision, glyph, output, repeating-product, track, and Van Berlo semantics;
- a bounded manufacturing planner and autonomous solution generator;
- command-line tools and GitHub Actions regression workflows.

### Validated milestones

- **108/108** imported campaign solutions complete in `opus_engine`;
- **0** incomplete simulations;
- **0** engine errors;
- **0** semantic gaps reported by the campaign audit;
- first autonomous solve completed for **P007 — Stabilized Water**;
- generated P007 solution validated by both `opus_engine` and [OMSim](https://github.com/ianh/omsim);
- generated binary reparses successfully and is distinct from the downloaded reference solution files.

The 108-solution result is a regression milestone for the current campaign corpus, not a claim that every custom, production, conduit, or community edge case is already implemented.

## First solver strategy

`bonded-pair-v1` is intentionally narrow. It currently accepts puzzles with:

- exactly two singleton reagents;
- exactly one standard two-atom product;
- one normal bond in the product;
- one atom supplied directly;
- one classical atom converted to salt through calcification;
- a standard bonder and a single-arm production pattern.

The solver builds a manufacturing graph, assigns reagent atoms to product atoms, instantiates a fresh rotated and translated mechanism, simulates six products, serializes the result, reparses it, and validates it again.

## Command-line use

Generate a solution from a supported puzzle:

```bash
python tools/solve_puzzle.py \
  path/to/P007.puzzle \
  generated/P007-auto.solution \
  --report generated/P007-auto.json
```

Audit the first autonomous campaign solve against the imported corpus:

```bash
python tools/audit_first_solver.py \
  --root .datasets/campaign-corpus \
  --output-dir reports/generated
```

Run the full campaign regression:

```bash
python tools/audit_campaign_corpus.py \
  --root .datasets/campaign-corpus \
  --output reports/campaign-corpus-audit.json
```

## Repository structure

```text
packages/
  opus_parser/      Binary puzzle/solution parsing and solution serialization
  opus_analysis/    Program decoding, timelines, metrics, and analysis
  opus_engine/      Experimental simulation engine
  opus_solver/      Manufacturing planning and autonomous generation
services/
  validator/        Validation service
fixtures/           Public regression manifests and fixtures
reports/            Generated regression summaries
scripts/            Web and data utilities
tools/              Import, audit, comparison, and solver CLIs
assets/, data/      Pattern explorer assets and catalogue data
```

## Development direction

1. Generalize the manufacturing graph beyond the first bonded pair.
2. Add reusable transport and assembly operators instead of one fixed arm pattern.
3. Generate multiple candidate layouts and select them through simulation.
4. Expand autonomous coverage across the early campaign.
5. Separate valid-solution generation from cost, cycles, area, and instruction optimization.
6. Extract reusable mechanisms from the validated corpus into the pattern library.

## Credits

- **Zachtronics** — creator of *Opus Magnum*.
- **OMSim** by Ian Henry — independent simulator used as an external validation oracle.
- Community campaign solutions imported by the corpus workflow remain credited to their original sources and authors; they are used for regression and comparative analysis, not silently republished as generated work.
