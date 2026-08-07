# Opus graphics engine architecture

Status: migration in progress

## Goal

The graphics stack must render an Opus Magnum state without owning simulation, validation, parsing, or optimization logic.

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
        +-------------------+
        |                   |
        v                   v
 OpusSvgRenderer       future backend
        |              (Canvas/WebGL/etc.)
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
  timeline
    frames
    frameIndex
    frame
    cycleCount
```

`OpusScene.atFrame(scene, n)` returns a new scene view for a replay frame and does not mutate the source scene.

### Scene rules

A scene may contain already-derived display geometry such as canonical occupied cells and arm tips. It must not contain DOM nodes or browser UI state.

A renderer must not need to know how `.solution` binary fields were parsed or how OMSIM reached a cycle state.

## 3. OpusSvgRenderer

`assets/js/opus-svg-renderer.js`

The first concrete rendering backend.

Responsibilities:

- own SVG layers;
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
- maintaining Viewer zoom/pan/selection UI.

## 4. OpusViewerRuntime

The runtime is an adapter between analyzed payloads and graphical consumers.

```text
payload -> OpusScene.build(payload) -> renderScene(scene)
```

It retains the current scene and exposes `sceneAtFrame(n)` so tools can inspect a replay state without coupling themselves to replay-control DOM.

## 5. Viewer

The Viewer is becoming a controller rather than a renderer.

Its long-term responsibilities are limited to:

- zoom / pan / fit;
- selection;
- inspector/details UI;
- replay controls;
- user interaction;
- choosing a renderer backend.

Static drawing code is being migrated out of `solution-viewer.js` into `OpusSvgRenderer` after structural parity tests prove equivalence.

## Migration safety

`.github/workflows/scene-renderer-smoke.yml` renders the same canonical scene through the existing Viewer and the standalone SVG renderer and compares structural output. The historical Viewer visual smoke suite remains in place to catch visual/replay regressions.

## Future uses unlocked by Scene

The same Scene API is intended to support:

- standalone Viewer;
- Laboratory/Inspector;
- solution diff viewer;
- area/occupancy overlays;
- collision debugging;
- solver progress visualization;
- pattern previews;
- static thumbnails;
- alternate Canvas/WebGL backends.
