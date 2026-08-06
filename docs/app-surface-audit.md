# Application surface audit

## Public destinations

| Surface | Status | Public role | Decision |
|---|---|---|---|
| `project.html` | Active | Canonical project map, maturity labels, roadmap | Keep as primary entry point |
| `index.html` | Preliminary prototype | Early Codex content and visual research archive | Keep visible, explicitly non-canonical; rebuild later from OMSIM and corpus |
| `inspector.html` | Alpha | Puzzle/solution analysis and replay | Keep; standardize header and language controls |
| `solver-lab.html` | Research active | Validated autonomous results and embedded campaign status | Keep |
| `research-monitor.html` | Research utility | Full-screen live campaign monitor | Keep as secondary destination linked from Solver Lab |

## Internal or future-facing surfaces

| Surface | Status | Decision |
|---|---|---|
| `opusjs/` demos and component pages | Development material | Remove from primary navigation; retain until snapshot renderer replaces them |
| asset-gallery content inside Codex | Historical visual archive | Rename as visual archives; do not present as validated assets |
| standalone technical test pages | Internal | Keep out of public navigation; delete only after dependency audit |
| duplicate monitor UI inside Solver Lab and `research-monitor.html` | Intentional | Compact embedded monitor plus full-screen operational view |

## Shared interface rules

1. Primary navigation order: Project, Codex, Laboratory, Solver.
2. Research Monitor is a secondary Solver destination, not a fifth product area.
3. Every destination must show one maturity label: Prototype, Alpha, Research active, or Future development.
4. French Canadian is the default public language.
5. A language selector appears only where both translations are actually wired. A decorative or non-functional selector must not be shown.
6. Product names remain stable across pages: `Projet`, `Codex`, `Laboratoire`, `Solver`.
7. Headers must use the same brand destination and navigation order before visual unification work begins.

## Next cleanup sequence

1. Standardize Inspector header and locale behavior.
2. Standardize Solver Lab and Research Monitor headers.
3. Identify legacy HTML/demo pages not reachable from the four public destinations.
4. Move obsolete public links to an internal development index.
5. Replace duplicated visual renderers with the OMSIM snapshot to OpusJS adapter.
6. Rebuild Codex content from verified engine data and corpus evidence.
