# Solver outcome learning

The solver can now persist compact results from composed-generation runs into `database/solver-outcomes.json` (or another path supplied by the caller).

Each outcome records the target puzzle feature fingerprint, manufacturing strategy, canonical assembly identity, initial engine progress, layout diagnostic signals, selected repair route, bounded searches that were attempted, best progress reached and whether the candidate was solved. Full generated solution geometry and arm programs are deliberately excluded.

Two entry points are supported:

```powershell
python tools/generate_composed_candidates.py P007.puzzle --temporal-radius 2 --transform-variants 81 --outcome-index database/solver-outcomes.json
```

or, for an already-generated report:

```powershell
python tools/record_solver_outcomes.py P007.puzzle reports/composed-candidates.json --output database/solver-outcomes.json
```

Stable outcome IDs deduplicate repeated equivalent attempts; when the same outcome is observed again, the observation with better engine progress is retained. The index also materializes repair priors grouped by base failure mode and first repair dimension, including solve rate and first-repair success rate.

These priors are evidence for future routing, not yet authority. The next policy layer should require a minimum observation count before empirical priors can override the deterministic diagnostic router.
