# Geometric candidate search

The preferred relative transform for a fragment transition is the most frequently observed placement in the corpus, but it is not guaranteed to transplant cleanly to a different target puzzle or to a different combination of neighboring fragments.

The geometric repair layer therefore searches only alternate transforms that were actually observed in replay-backed source solutions. It does not invent arbitrary placements.

Each materialization join receives a stable slot name:

- `branch-N:convergence-input`
- `branch-N:edge-M`
- `tail-N:edge`

Variant zero is the preferred historical combination. Additional candidates replace as few slots as possible, and ties prefer transform choices with broader observation support. The resulting layout keeps the existing relative timing schedule, is serialized normally, and is ranked with the same engine-progress diagnostics used by temporal search.

Example:

```powershell
python tools/generate_composed_candidates.py P007.puzzle --temporal-radius 2 --transform-variants 81 --transform-per-slot 3 --write-best candidate.solution
```

Search order is intentionally staged: preferred empirical candidate, local timing repair, then observed geometry repair. A future combined search should only be enabled after independent timing and geometry repair effectiveness is measured, because their Cartesian product grows quickly.
