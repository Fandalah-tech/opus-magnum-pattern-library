# OpusJS primitive architecture

OpusJS separates reusable visual objects into three layers.

## Geometry

Geometry contains dimensions and proportions only. `masterAtomV1` is the validated atom geometry inherited from Pb.

## Material

A material contains palette, gradient placement, ink colour and reflection profile. Current atom materials are `lead`, `tin`, `iron`, `copper`, `silver`, `gold` and `mercury`.

## Identity

An identity maps an official element code to one geometry, one material and one alchemical mark.

```js
Pb: {
  geometry: 'masterAtomV1',
  material: 'lead',
  mark: '♄',
  symbolSize: 21.2,
  symbolY: 0
}
```

Existing scene data remains compatible:

```js
atoms: [{ element: 'Pb', q: 0, r: 0 }]
```

The renderer resolves that identity internally. The public registry is exposed at `OpusJS.primitives` for the future editor, parser and validation tools.

## Validation state

- Pb: approved master reference.
- Sn: first material profile implemented; visual validation pending.
- Fe, Cu, Ag, Au, Hg: migrated to the shared geometry; material calibration pending.
