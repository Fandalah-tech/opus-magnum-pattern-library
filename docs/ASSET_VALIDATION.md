# Canonical Asset Validation

## Purpose

The temporary Assets workspace is the review gate for OpusJS visual primitives.

## Reference hierarchy

1. Primary production-art references published by artists who worked on Opus Magnum.
2. Screenshots and exported solution GIFs from the released game.
3. Opus Magnum Wiki pages for terminology and behavior.
4. Community references only when primary material is unavailable.

Kyle Steed's Opus Magnum portfolio is the current primary visual reference for atoms, parts, interface framing, and board treatment:

- https://www.kylesteed.net/opus-magnum
- `atom_layout_B_1200.png`
- `parts_layout_withFrame_1200.png`

Reference images remain externally hosted and are shown only inside the validation workspace. They are not packaged as OpusJS assets.

## Statuses

- `draft`: recognizable intent, geometry or material treatment still substantially wrong.
- `close`: recognizable and structurally close; smaller proportion, colour, shading, or detail changes remain.
- `validated`: reviewed against a primary reference and accepted for canonical use.

No asset should be marked `validated` without a named reference and review notes.

## Asset lifecycle

```text
experimental -> draft -> close -> canonical
```

Canonical assets are the only assets that should eventually be used by stable Codex and Laboratory scenes. During the current prototype phase, draft assets may still appear in scenes, but their status must remain visible in the Assets workspace.
