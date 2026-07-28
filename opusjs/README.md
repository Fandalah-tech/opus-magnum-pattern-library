# OpusJS

OpusJS is the shared rendering foundation for the Opus Magnum Codex and the future Laboratory.

## v0.1 scope

- declarative scene descriptions;
- reusable SVG primitives for board cells, atoms, arms, glyphs and tracks;
- deterministic SVG rendering;
- no simulation yet;
- no `.solution` parser yet.

## Design rule

Game objects use one canonical renderer. Codex cards, detail views, future editors and exports must all consume the same scene data.

## Terminology

Official game terms remain canonical. Project-created terms describe research structures only and remain marked provisional.
