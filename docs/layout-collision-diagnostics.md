# Layout collision diagnostics

Composed layouts now expose static geometry diagnostics before engine simulation. The goal is to rank and explain candidates, not to replace the engine as the authority on Opus Magnum collision semantics.

Known glyph footprints, rails, conduits and arm bases are mapped to occupied hexes. Overlaps between two exact footprints are reported separately from approximate conflicts involving an unknown anchor-only footprint. An arm base sharing a rail cell is explicitly allowed.

Arm workspace analysis is conservative: each arm is expanded over reachable rotations, branches, piston lengths and, when track instructions are present, rail origins. Workspace overlap is reported as a dynamic-risk signal only. It is never treated as an invalid layout because interacting mechanisms frequently require shared reachable cells.

Engine validation also records whether every input source successfully spawned its reagent at cycle zero. A source blocked by another reagent is returned as `blocked-input-at-start`, which is a strong signal that geometry repair should be preferred over timing repair.

These diagnostics currently support ranking and failure explanation. Exact moving-atom collision validity remains the responsibility of the simulator and OMSim cross-validation.
