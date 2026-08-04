# Community Rendering and Viewer Review

Status: verified 2026-08-04

This review covers public community work relevant to displaying, editing, animating, or analyzing Opus Magnum solutions. It deliberately separates reusable source code from useful behavior and from copyrighted game assets.

## Executive decision

No public project currently provides a complete, browser-embeddable, cycle-aware Opus Magnum board renderer that we can adopt as the Codex viewer backend without major architectural or licensing compromises.

The recommended approach is therefore:

1. Keep our browser-native SVG viewer.
2. Reuse public format and geometry behavior where licenses permit.
3. Use OMSim as the authoritative simulation engine.
4. Treat existing editors and viewers as UX and behavior references rather than copying their rendering code blindly.
5. Do not bundle sprites extracted from the commercial game.
6. Maintain explicit attribution for every behavior-derived or source-derived component.

This conclusion does **not** mean the ecosystem lacks visual tools. Several strong tools exist, but they solve adjacent problems, are desktop/game-integrated, are unavailable as public source, or depend on game assets that cannot safely be redistributed in a public web application.

## Projects reviewed

### Opus Magnum itself — official GIF renderer

**Availability:** commercial game, closed source  
**Rendering:** complete, authoritative, animated  
**Reusable:** no source; generated GIFs only  
**Decision:** visual reference only

The official renderer remains the fidelity benchmark. It knows all sprites, animation phases, molecule rendering, arm motion, glyph effects, and GIF loop behavior. Those implementation details are not available as a reusable library. Game sprites and extracted assets must not be bundled in this project without explicit permission.

### omclone — notgreat

**Availability:** confirmed community web application; public source repository not located  
**Technology:** WebAssembly and Canvas, according to the author's project description  
**Capabilities:** solution viewing and editing, incremental editing without replaying the complete solve, handling extremely large instruction programs  
**License:** unknown  
**Decision:** important UX/architecture reference; no code reuse until source and license are confirmed

omclone is the closest known predecessor to a true external Opus Magnum IDE. Community tournament reports confirm that it was used to program solutions with thousands of instructions that were impractical to edit in the game. Its strongest ideas for our purposes are incremental state handling, large-program ergonomics, and a Canvas-based browser editor. Because no clearly licensed public source was found, direct reuse is currently blocked.

### F43dit / OMSEKT — F43nd1r

**Availability:** public project history and online editor confirmed  
**Technology:** Kotlin; browser editor associated with Kotlin DSL tooling  
**Capabilities:** import and edit solution files, expose solution structure and instruction metrics, transform solution models to and from a Kotlin DSL  
**License:** Apache-2.0 for published parser/DSL artifacts  
**Decision:** reuse parser behavior and study editor workflows; do not assume its renderer is a reusable component

F43dit has long been used by competitive players for inspecting and editing large solutions. It is valuable prior art for raw solution editing and metrics, but it is not a modern simulation-synchronized board viewer. Its parser lineage remains directly relevant.

### OMSP — F43nd1r

**Availability:** public and actively published  
**Technology:** Kotlin Multiplatform  
**Capabilities:** parse and write `.puzzle` and `.solution` files  
**License:** Apache-2.0  
**Decision:** authoritative format reference and reusable test oracle

OMSP is a strong source for file-format behavior. It does not render or simulate solutions. The current published artifacts demonstrate that it remains maintained and available for JVM and native targets. Our parser should continue to be tested against OMSP-compatible behavior, with attribution.

### OMSim — Ian Henderson and contributors

**Availability:** public  
**Technology:** C  
**Capabilities:** execute and validate solutions, calculate metrics, expose simulation behavior and geometry rules  
**License:** upstream COPYING notice; preserve separately  
**Decision:** authoritative simulation backend and primary behavioral source for dynamic geometry

OMSim is the most important foundation for animation and correctness. It does not provide a polished board renderer, but its state transitions, collision behavior, part geometry, and metric calculations should drive our viewer rather than visual guesses. Future animation should consume explicit trace/state output derived from OMSim.

### OpusSolver — gtw123

**Availability:** public and actively developed  
**Technology:** C# / .NET 8  
**Capabilities:** parse puzzles, generate `.solution` files, validate through OMSim/libverify, model grid occupancy, pathfind arm and molecule movement, detect rotation collisions  
**License:** MIT  
**Decision:** reuse algorithms or port well-isolated geometry/pathfinding concepts with attribution; not a renderer

OpusSolver contains mature spatial concepts: grid state, access points, molecule orientation, rotation collision detection, and A* arm pathfinding. These are highly relevant to future overlays and optimization, but its visual output is not a reusable web renderer.

### Opus Magnum Record Viewer — Galandustry

**Availability:** public, current  
**Technology:** Vue 3 + TypeScript, Tauri 2 + Rust, bundled OMSim C snapshot, SQLite  
**Capabilities:** leaderboard browsing, Pareto analysis, local solution import, complete metric simulation, GIF preview/capture/reversal, 2D/3D score visualizations  
**License:** MIT for project code; third-party materials retain upstream licenses  
**Decision:** strong architecture, attribution, localization, and metrics UX reference; no evidence of a full machine-board renderer to adopt

This is the strongest modern adjacent application found. It demonstrates excellent separation between UI, codecs, simulator, persistence, and analysis. Its acknowledgements model is worth following. Its visualizations primarily concern records, Pareto frontiers, radar charts, and GIF assets rather than an interactive cycle-by-cycle machine board.

### Opus Magnum Glyph Tool — Iris-xii

**Availability:** public  
**Technology:** Godot / C#  
**Capabilities:** draw custom glyph tile shapes and export base/glow/stroke sprites for mods  
**License:** no explicit reusable license found in the reviewed repository  
**Decision:** workflow reference only; do not copy generated graphics or source without permission

OMGT confirms how mod authors produce game-compatible glyph sprite layers. It may help validate sprite dimensions and multi-tile composition, but its lack of a clear license prevents direct reuse. It also targets mod sprite production, not semantic SVG icons.

### Quintessential / Opus Mutatum ecosystem

**Availability:** public  
**Technology:** game mod loader and mods  
**Capabilities:** alter game UI and mechanics, add glyphs and mechanisms, improve in-game workflows  
**Decision:** source of UI and integration ideas; unsuitable as the web viewer runtime

Quintessential can access the game's own renderer and assets because it runs inside the installed game. This gives mods visual fidelity that a public web application cannot legally or technically inherit. It remains useful for understanding community UX expectations and custom-part metadata.

### OM leaderboard ecosystem — F43nd1r

**Availability:** public  
**Capabilities:** leaderboard data, community metric conventions, solution resources and GIF references  
**Licenses:** `om-leaderboard` is Unlicense; related bot/parser projects use their own licenses  
**Decision:** future record comparison and corpus integration; not a machine renderer

The leaderboard ecosystem is the authoritative public source for extended metrics such as rate, height, width, bounding hexagon, instructions, and community modifiers. It should eventually feed comparison views in the Inspector.

### Legacy generic raw editors

Examples include the browser editor historically hosted at `fazzone.github.io/opus/` and advanced puzzle editors used to edit serialized fields directly.

**Decision:** useful evidence that browser-side binary/text manipulation is viable, but not suitable rendering foundations.

### `liewdl/opus-gif`

**Availability:** public repository  
**Content:** a personal collection of official game-generated GIF files  
**Decision:** not a renderer and not reusable as source code

The repository name suggested a renderer, but commit inspection confirmed that it contains exported solution GIFs only.

## Capability matrix

| Project | Parse/write | Simulate | Static board view | Animated machine view | Edit solution | Browser-native | Reusable status |
|---|---:|---:|---:|---:|---:|---:|---|
| Official game | Yes | Yes | Yes | Yes | Yes | No | Visual reference only |
| omclone | Yes | Yes/partial | Yes | Yes | Yes | Yes | Blocked by source/license uncertainty |
| F43dit | Yes | No/limited | Editor-oriented | No confirmed full replay | Yes | Yes | Parser/UX reference |
| OMSP | Yes | No | No | No | Model only | Multiplatform | Apache-2.0 format reference |
| OMSim | Reads | Yes | No | Trace foundation | No | Backend/WASM possible | Core behavioral dependency |
| OpusSolver | Yes | Yes | Debug/model | No polished renderer | Generates | No | MIT algorithms and geometry reference |
| Record Viewer | Yes | Yes | Record/metric views | GIF tools | Limited import workflow | Desktop web stack | MIT architecture/UX reference |
| OMGT | No | No | Glyph editor | No | Custom glyph assets | Desktop | No direct reuse without license |
| Quintessential | Game-native | Game-native | Game-native | Game-native | Modded game | No | In-game reference only |

## Rendering implications

### Geometry

Geometry must be data-driven and tested independently from appearance. Our `opus-geometry.js` layer should eventually contain:

- axial coordinate conversion;
- canonical direction and rotation tables;
- complete part footprints;
- activation cells and semantic anchors;
- track topology;
- arm base, pivot, grabber, piston and Van Berlo reach models;
- molecule transforms and bond geometry.

OMSim and OpusSolver are the preferred behavioral references. OMSP is the preferred serialized-format reference.

### Symbols and visual appearance

We should create original semantic SVG symbols rather than redistributing game sprites. The symbols should be recognizable to players but not pixel-for-pixel copies of commercial assets. Multi-cell pieces should be rendered as connected assemblies, not independent labeled hexagons.

The component system should separate:

- footprint / hit area;
- structural outline;
- semantic icon;
- selection and diagnostic overlays;
- dynamic simulation layer.

### SVG versus Canvas

SVG remains appropriate for the current static and interactive Inspector because it provides accessible selection, crisp zooming, easy overlays, and DOM inspection. omclone demonstrates that Canvas can handle large dynamic programs effectively, but we do not yet need to abandon SVG.

Recommended threshold:

- SVG for static layout, selection, footprints, relations and moderate animation;
- hybrid SVG + Canvas if atom animation or very large solutions become CPU-bound;
- WebGL only if profiling shows a real need.

### Animation

Animation must not be inferred solely from written arm programs. The correct architecture is:

`OMSim trace -> canonical cycle state -> viewer scene state -> renderer`

This permits exact arm positions, held molecules, bonds, glyph reactions, collisions and output events. It also prevents the static timeline's simplifying assumptions from leaking into the visual simulation.

## Credits and licensing policy

Before importing code or porting non-trivial behavior:

1. Record the upstream project, author, exact file or behavior, revision, and license.
2. Preserve required notices in `THIRD_PARTY_NOTICES.md`.
3. Mark behavior-derived ports separately from copied source.
4. Never assume that a public repository without a license grants reuse rights.
5. Do not commit extracted Opus Magnum sprites, fonts, sounds, puzzle corpus, or other commercial assets.
6. User-provided game files may be processed transiently or locally, but are not redistributed.

## Concrete next implementation

The next viewer block should remain ours, but informed by this review:

1. Build an original SVG part-symbol library.
2. Connect multi-cell footprints into unified piece silhouettes.
3. Add canonical anchors for arms, glyph activation cells, inputs and outputs.
4. Add layer controls: grid, footprints, reach, relations, labels.
5. Add snapshot tests against known `.solution` fixtures.
6. Begin an OMSim trace contract before implementing cycle playback.

## Primary references

- Ian Henderson, `omsim`
- gtw123, `OpusSolver`
- F43nd1r, `omsp`, F43dit/OMSEKT and leaderboard projects
- notgreat, `omclone` (community and author descriptions; source/license not located)
- Galandustry, `Opus_Magnum_Record_Viewer`
- Iris-xii, `omgt`
- QuintessentialOM, `Quintessential` and related mods
- biggiemac42's technical and tournament articles documenting community usage
