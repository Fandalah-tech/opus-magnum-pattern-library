# Opus Analysis

`opus_analysis` converts the canonical parsed solution into analysis-oriented data.

## Structural graph

```python
from packages.opus_parser import parse_solution
from packages.opus_analysis import build_solution_graph

graph = build_solution_graph(parse_solution("example.solution"))
```

The graph contains:

- one node per arm, glyph, track, input and output;
- part positions and footprints;
- compact program statistics;
- shared-hex relationships;
- parts located within an arm's approximate reach;
- candidate arm workspace overlaps;
- node degrees and weakly connected components.

## Important limitation

This is a static structural graph. A `within-arm-reach` or `workspace-overlap` edge is a candidate interaction, not proof that a molecule is transferred at runtime. Confirmed dependencies will be added later from cycle-accurate omsim traces.

## API

Upload a `.solution` file to:

```text
POST /analyze/graph
```

The endpoint returns the graph as deterministic JSON conforming to `schemas/solution-graph.schema.json`.
