# Architecture Reboot — Opus Magnum Codex / OpusJS

## Status

Approved direction: combine existing public tools behind a project-owned canonical model.

## Architectural decision

- `omsim` is the validation oracle.
- `OpusSolver` is the first external solution generator.
- OpusJS remains the visualization layer.
- The Codex remains the human knowledge and heuristic layer.
- A project-owned canonical JSON model separates all components.

## Immediate constraints

- Do not rebuild game assets before the architecture is validated.
- Do not rewrite the simulator in JavaScript.
- Do not couple the frontend directly to OpusSolver or omsim data structures.
- Keep external tools replaceable through adapters.

## Target flow

```text
.puzzle + .solution
        |
        v
Import adapters
        |
        v
Canonical model
        |
        +--> omsim validation
        +--> metrics and analysis
        +--> OpusJS visualization
        +--> Codex annotations
        +--> solver providers
```

## First milestone

A deterministic local workflow that can:

1. import one `.puzzle`;
2. import one `.solution`;
3. validate the pair with omsim;
4. return structured metrics and errors;
5. export canonical JSON.

No automatic solving or animation is required for this milestone.
