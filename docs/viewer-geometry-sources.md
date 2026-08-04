# Solution viewer geometry sources

The interactive viewer is implemented locally in SVG, but its coordinate and footprint conventions are based on public Opus Magnum tooling rather than visual guesswork.

## Sources reviewed

- **omsim** by Ian Henry — authoritative simulator used by the validator and the primary reference for game behavior.
- **OpusSolver** by gtw123 — prior automated solver referenced by Biggie's technical history of Opus Magnum automation.
- **Opus Magnum Bench / SDK conventions** — public documentation exposing axial directions, rotation semantics, occupied-cell helpers, and canonical part footprints.
- **Biggie's automation write-up** — overview of prior tools and the 24 Hour Challenge ecosystem.
- **fazzone.github.io/opus** — historical external solution-file editor; useful for file manipulation precedent, but not a reusable renderer.

## Viewer conventions

- Axial coordinates `(q, r)`.
- Rotation `0` points east.
- Positive rotation follows `E → NE → NW → W → SW → SE`.
- Multi-cell parts are rendered from canonical rotation-zero footprints and transformed in axial space.
- Unknown or unconfirmed part footprints intentionally fall back to one occupied cell.

## Current limitations

- Input and output molecule shapes are not rendered yet.
- Some late-game and journal-specific glyph footprints still require confirmation against simulator source or a diverse fixture corpus.
- The viewer renders the static initial layout only; moving arms, held atoms, collisions, and glyph activation will require cycle traces.
- SVG symbols are original schematic representations and are not extracted game assets.

## Credits

Opus Magnum was created by Zachtronics. `omsim` was created by Ian Henry. OpusSolver was created by gtw123. The external solution editor was published by Fazzone. Biggie MacDonald documented and connected much of the solver ecosystem.