# Opus graphics engine architecture

Status: canonical Scene/SVG pipeline active; consumers still expanding

## Goal

The graphics stack must render and annotate an Opus Magnum state without owning simulation, validation, parsing, or optimization logic.

Canonical direction:

```text
.puzzle + .solution
        |
        v
parser / analyzer / simulator
        |
        v
     OpusScene
        |
        +----------------------+---------------------+
        |                      |                     |
        v                      v                     v
 OpusSvgRenderer          OpusSceneDiff       Scene annotations
        |                      |               diagnostics/patterns
        |                      v                     |
        |              OpusSvgDiffOverlay            v
        |                      |          OpusSvgDiagnosticsOverlay
        +-----------+----------+---------------------+
                    |
                    v
             OpusSvgOverlayHost
                    |
                    v
 Viewer / Inspector / Solver diagnostics / Diff tools
```

## 1. OpusRendererCore

`assets/js/opus-renderer-core.js`

Pure/shared graphical primitives and canonical geometry:

- axial hex -> pixel conversion;
- canonical arm branch offsets;
- arm-tip geometry;
- hex polygon generation;
- piece-kind classification;
- SVG element helper for the SVG backend;
- interpolation/easing primitives.

It must not know about Viewer controls, files, APIs, validation, or simulation.

## 2. OpusScene

`assets/js/opus-scene.js`

A scene is the normalized state passed from domain code to graphics code.

Current shape:

```text
scene
  schemaVersion
  kind = opus-scene
  source
    puzzle
    solution
    graph
    validation
    replay
  meta
    puzzleName
    solutionName
    metrics
    validationStatus
  static
    parts
      kind
      occupiedCells
      armTips
    occupiedCells
    graph
    relations
  annotations
    diagnostics
      summary
      items
        id
        severity
        confidence
        targets
        evidence
    patterns
      summary
      findings
  timeline
    frames
    frameIndex
    frame
    cycleCount
    capabilities
```

`OpusScene.atFrame(scene, n)` returns a new scene view for a replay frame and does not mutate the source scene.

### Scene rules

A scene may contain already-derived display geometry such as canonical occupied cells and arm tips. It must not contain DOM nodes or browser UI state.

`annotations` contains normalized analysis results, not newly inferred graphical conclusions. The Python analyzer remains responsible for determining diagnostics and patterns; graphical consumers only present them.

A renderer must not need to know how `.solution` binary fields were parsed or how OMSIM reached a cycle state.

## 3. OpusSvgRenderer

`assets/js/opus-svg-renderer.js`

The first concrete rendering backend.

Responsibilities:

- own the canonical base SVG layers;
- draw grid;
- draw static tracks;
- draw arms from canonical scene arm tips;
- draw station/glyph footprints;
- delegate piece symbols to the symbol library;
- expose rendered part nodes through stable `data-*` attributes for interaction and animation.

Non-responsibilities:

- validation;
- metrics;
- replay simulation;
- loading files;
- calling `/api/v1/analyze`;
- maintaining Viewer zoom/pan/selection UI;
- calculating diagnostics or diff semantics.

## 4. OpusSvgOverlayHost

`assets/js/opus-svg-overlay-host.js`

The overlay host standardizes optional composited layers without changing the base renderer.

It owns:

- named overlay creation through `data-opus-overlay`;
- stable ordering before/after canonical renderer layers;
- layer reuse;
- clear/remove operations;
- overlay enumeration.

An overlay must not use base-renderer DOM contracts such as `data-part-id` for decorative nodes. Overlay-specific identifiers use their own namespace (`data-diff-*`, `data-opus-diagnostic-*`, etc.).

This host is the common insertion point for diff, diagnostics, future collision visualization, solver telemetry, and other optional graphics.

## 5. OpusSceneDiff

`assets/js/opus-scene-diff.js`

`OpusSceneDiff.diff(beforeScene, afterScene)` is a pure Scene consumer. It does not draw anything and does not depend on the Viewer.

It returns:

- added parts;
- removed parts;
- moved parts;
- changed configuration/program parts;
- unchanged pairs;
- added/removed/shared occupied hexes;
- numeric metric deltas;
- a compact summary.

Matching prefers stable part IDs. When IDs differ between two solutions, the diff falls back to a semantic signature composed from part type, `which`, and arm number. This is intentionally conservative: the two scenes should represent the same puzzle or otherwise comparable machine context.

## 6. OpusSvgDiffOverlay

`assets/js/opus-svg-diff-overlay.js`

A rendering backend for an `opus-scene-diff`. It draws only the comparison overlay:

- added footprint cells;
- removed footprint cells;
- moved-part origin/target paths;
- changed-part rings.

It does not render the underlying machine. The Scene Diff Lab composes it through `OpusSvgOverlayHost` with a normal `OpusSvgRenderer` instance.

## 7. OpusSvgDiagnosticsOverlay

`assets/js/opus-svg-diagnostics-overlay.js`

A pure presentation layer for `scene.annotations.diagnostics.items`.

It:

- groups targeted diagnostics by part;
- renders a footprint highlight and count badge;
- applies a stable severity priority (`warning > opportunity > info`);
- reports global diagnostics without inventing a board target;
- accepts optional severity filtering.

It explicitly does **not** infer optimization opportunities. If a diagnostic has no `targets`, it remains a global Inspector finding rather than being attached to an arbitrary machine element.

`assets/js/inspector-diagnostics-overlay.js` composes this renderer into the Inspector and exposes an optional Diagnostics toggle.

## 8. OpusViewerRuntime

The runtime is an adapter between analyzed payloads and graphical consumers.

```text
payload -> OpusScene.build(payload) -> graphical consumer
```

It retains the current scene and exposes `sceneAtFrame(n)` so tools can inspect a replay state without coupling themselves to replay-control DOM.

The Viewer and Inspector route analysis explicitly through this runtime. The legacy Viewer bridge no longer intercepts `window.fetch`.

## 9. Viewer

The Viewer is a controller rather than the owner of static drawing.

Its responsibilities are limited to:

- zoom / pan / fit;
- selection;
- inspector/details UI;
- replay controls;
- user interaction;
- choosing a renderer backend.

Static drawing is delegated to `OpusSvgRenderer`. Replay controls and physical animation consume canonical Scene timeline frames.

## 10. Scene Diff Lab

`scene-diff.html`

The Scene Diff Lab is the first graphical product built on the engine that does not instantiate `SolutionViewer`.

Flow:

```text
Puzzle + Solution A ----> analyze ----> Scene A --+
                                                   +--> OpusSceneDiff --> diff overlay
Puzzle + Solution B ----> analyze ----> Scene B --+          |
                                      |                       |
                                      +--> OpusSvgRenderer <--+
                                                  |
                                          OpusSvgOverlayHost
```

This proves that `OpusScene`, `OpusSvgRenderer`, and overlay composition are reusable independently of Viewer controls and Inspector UI.

## Migration safety

The graphics stack is guarded by separate browser contracts:

- `.github/workflows/scene-renderer-smoke.yml` — Scene/static renderer parity;
- `.github/workflows/viewer-smoke.yml` — historical Viewer visual/replay behavior;
- `.github/workflows/viewer-scene-integration-smoke.yml` — Scene-driven peripheral graphics;
- `.github/workflows/inspector-graphics-smoke.yml` — explicit Inspector/runtime + diagnostics-overlay flow;
- `.github/workflows/scene-diff-smoke.yml` — pure diff model + SVG overlay;
- `.github/workflows/scene-diff-lab-smoke.yml` — standalone Diff Lab + generic overlay-host flow.

Frontend graphics changes are intentionally separated from Cloud Run deployment triggers so renderer iteration does not rebuild the validator service.

## Future uses unlocked by Scene

The same Scene API and overlay host can now support:

- standalone Viewer;
- Laboratory/Inspector;
- solution diff viewer;
- area/occupancy overlays;
- collision debugging once collision events exist in the analysis contract;
- solver progress visualization;
- pattern previews;
- static thumbnails;
- alternate Canvas/WebGL backends.
