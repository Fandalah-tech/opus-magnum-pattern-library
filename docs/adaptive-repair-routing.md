# Adaptive repair routing

Composed candidate generation now chooses its first repair dimension from observed diagnostics instead of always trying timing before geometry.

Geometry is preferred when a reagent is blocked at cycle zero, the materialized layout has an exact static footprint conflict, the standard output is missing, or the engine reports a collision-like error. Timing is preferred when the candidate runs without those geometry signals but produces no product or insufficient throughput. Unknown/non-collision engine errors also start with timing because it is the smaller local perturbation.

The policy is deterministic and explainable: every failed candidate records `repairPolicy` with the preferred dimension, actual enabled order, reason, geometry signals and timing signals. If the preferred search is disabled, the available alternative is used. If the first search finds a complete solution, the second search is skipped.

This routing is still heuristic rather than learned. The report-level `repairRoutes` counts are intentionally retained so future corpus runs can measure which diagnostic routes actually repair candidates and replace hand-authored priors with empirical ones.
