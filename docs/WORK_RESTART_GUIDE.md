# Work restart guide

## Current checkpoint

- Branch: `feature/critelli-2026-public-corpus`
- Restored engine capabilities: deterministic overlap layers, OMSim half-cycles, recent bonds, `bonder-speed`, rejection, division, unification, proliferation and paired conduits.
- First autonomous strategy: `bonded-pair-v1`.
- Intake command: `tools/solve_test_puzzle.py`.
- Acceptance fixture: `samples/solver/P007.puzzle`.

## Verification

```bash
PYTHONPATH=/tmp/opus-pydeps:. python -m pytest -q
python tools/solve_test_puzzle.py samples/solver/P007.puzzle --output-dir /tmp/opus-first-test
```

The test is ready only when the suite passes, the intake report sets `readyForGameTest` to `true`, the binary round-trip is clean and six products are delivered. OMSim remains the independent oracle whenever its executable is available.

## Next input

Accept one user-supplied `.puzzle`, run the intake command, and inspect its report. If supported, independently validate the generated `.solution` with OMSim and then return it for an in-game test. If unsupported, use the manufacturing-plan diagnostic to add the narrowest missing generation strategy; do not weaken engine validation.
