# Implementation Plan

## Milestone 1 — Validation vertical slice

Goal: transform a `.puzzle` and `.solution` pair into a deterministic canonical result.

### Work packages

1. **External tool audit**
   - Pin omsim commit.
   - Compile on Windows and Linux.
   - Record CLI output, exit codes and known divergences.
   - Compile OpusSolver with .NET 8 and its native dependencies.

2. **Canonical contracts**
   - Puzzle schema.
   - Solution schema.
   - Validation-result schema.
   - Stable identifiers and source hashes.

3. **Adapters**
   - Puzzle import adapter.
   - Solution import adapter.
   - omsim process adapter.
   - Structured error normalization.

4. **Reference corpus**
   - Valid campaign examples.
   - Invalid collision examples.
   - Incorrect-output examples.
   - Track and piston edge cases.
   - Known omsim divergence cases.

5. **Frontend bridge**
   - Load canonical JSON in OpusJS.
   - Static board rendering first.
   - Validation and metrics panel.

## Repository boundaries

```text
schemas/        Canonical public contracts
adapters/       External format and tool adapters
core/           Tool-independent domain logic
fixtures/       Reference puzzles, solutions and expected results
opusjs/         Visualization only
docs/           Architecture, audits and decisions
```

## Deferred

- Full browser simulation.
- Automatic solving UI.
- Evolutionary search.
- Pixel-perfect asset reconstruction.
- Production puzzle support beyond imported display.

## Definition of done

A command or test can accept one puzzle and one solution, call the pinned validator, and emit JSON conforming to `validation-result.schema.json` with deterministic metrics and normalized errors.
