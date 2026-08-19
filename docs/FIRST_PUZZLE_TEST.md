# First autonomous puzzle test

The repository is ready to accept a `.puzzle` file through one command:

```bash
python tools/solve_test_puzzle.py path/to/puzzle.puzzle --output-dir reports/generated
```

The intake pipeline:

1. parses the native puzzle;
2. builds a manufacturing plan;
3. generates a native version-7 `.solution` when a registered strategy supports the puzzle;
4. validates six products with the local engine;
5. serializes and reparses the file, then validates it again;
6. runs OMSim when an `omsim` executable is on `PATH` or supplied with `--omsim`;
7. writes `<puzzle>-auto.solution` and `<puzzle>-solver-report.json`.

The first registered autonomous strategy is `bonded-pair-v1`: a two-atom normal-bond product made from two single-atom reagents, with one reagent transformed through calcification.

The first public corpus-derived strategy is `corpus-derived-fragment-extraction-v1`. It recognizes the reagent/product topology of the Critelli “Salt of Saturn by Vinegar” exercise, rebuilds a learned legal mechanism with fresh part identities, applies a global geometric transformation, and requires both local round-trip validation and OMSim validation. This is reported as corpus-derived reuse, not as an independently discovered architecture.

Unsupported puzzles produce a structured report and remain available for the next solver strategy instead of being mistaken for engine failures.

Acceptance is covered by `tests/test_solve_test_puzzle.py` and the native fixture `samples/solver/P007.puzzle`.

## Objective architecture portfolio

The Critelli corpus strategy now has a separate oracle-scored portfolio path:

```bash
python tools/solve_objective_portfolio.py path/to/puzzle.puzzle \
  --omsim path/to/omsim \
  --output-dir reports/generated/objective-portfolio
```

This path materializes independent sequential-piston, periodic-pipeline,
balanced-cell, and parallel-throughput architectures. OMSim validates and
scores every candidate with a 60-second default timeout, then selects winners
independently for cost, area, cycles, rate, instructions, CostArea,
Cost+Cycles, and Sum4. The report preserves local-engine disagreements as
diagnostics instead of rejecting an OMSim-valid architecture.

The normalized blueprints are public-corpus-derived reuse. They demonstrate
metric-directed generation and objective selection; they are not presented as
new mechanisms discovered without examples.

On the Salt of Saturn reference corpus, the checked-in portfolio reproduces
the corpus winners for all eight configured objectives: cost 50, area 25,
cycles 53, rate 1, instructions 15, CostArea 2250, Cost+Cycles 240, and
Sum4 343.
