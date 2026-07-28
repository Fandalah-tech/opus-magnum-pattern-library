# Reference calibration

Fidelity overlays must only be enabled when an asset has an isolated, asset-specific reference image or a verified crop with alignment metadata.

A full production sheet may be displayed as contextual evidence, but it must not be overlaid directly against a single OpusJS asset.

Each calibrated reference should define:

- source and attribution
- isolated image URL or local path
- crop and scale metadata, when applicable
- alignment offset
- validation date
- notes about colour sampling and geometry

Until these fields are complete, the asset remains `draft` and Fidelity comparison controls stay disabled.
