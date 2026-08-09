# Temporal candidate search

Generated composed assemblies can be structurally complete and serializable while still failing the engine because the historically preferred relative timing is not transferable to the target puzzle.

The temporal search layer keeps geometry and every fragment-local program unchanged. It only shifts complete `branch-N` and `tail-N` instance groups relative to the convergence anchor, then normalizes the resulting start cycles so no instruction begins before cycle zero.

Variants are enumerated from the historical timing outward by total absolute displacement. Engine validation records the normalized failure mode, first simulation error, product delivery counts, output deficits and completed cycles. Ranking prefers a complete solve first, then candidates that avoid simulation termination, deliver more products, leave a smaller deficit, execute farther, and finally require less timing displacement.

Example:

```powershell
python tools/generate_composed_candidates.py P007.puzzle --temporal-radius 2 --temporal-variants 81 --temporal-results 10 --write-best candidate.solution
```

This search is intentionally local. It is the first repair layer after empirical assembly generation; candidates that remain invalid should feed the next search layer for alternate relative transforms/geometry rather than increasing the timing radius indefinitely.
