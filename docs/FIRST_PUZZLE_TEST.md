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
