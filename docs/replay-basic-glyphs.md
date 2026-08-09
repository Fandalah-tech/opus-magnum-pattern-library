# Basic glyph replay simulation

The replay engine now applies three passive glyph effects after arm instructions and before disposal/output consumers.

## Supported glyphs

- `bonder`: if atoms occupy both glyph cells and no bond already joins those positions, create a normal bond. Separate molecules are merged before the bond is added.
- `unbonder`: if a normal bond joins the two glyph cells, remove it. If the molecular graph becomes disconnected, split it into separate replay molecules.
- `glyph-calcification`: convert `air`, `earth`, `fire`, or `water` occupying the glyph anchor to `salt`.

Each mutation emits a `glyph-effect` event. Functional-fragment evidence can therefore promote matching bonding/conversion fragments to `dynamic-confirmed` when the replay actually observes the mutation.

## Validation boundary

This implementation is deliberately narrow. Geometry follows the two occupied bonder/unbonder cells already used by the viewer geometry model. The behavior should be cross-validated against OMSim across a representative corpus before it is treated as authoritative simulation semantics.

Not yet simulated: multibonder, prismatic bonding, purification, projection, duplication, animismus, unification/dispersion, triplex bonding, collision rules, and other glyph effects.
