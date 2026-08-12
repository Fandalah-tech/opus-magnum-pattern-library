# Opus binary parser

Pure-Python, dependency-free readers for Opus Magnum `.puzzle` and `.solution` files.

## Public API

```python
from packages.opus_parser import parse_puzzle, parse_solution

puzzle = parse_puzzle("example.puzzle")
solution = parse_solution("example.solution")
```

Both functions return JSON-serializable canonical dictionaries and include the source SHA-256, file size, binary format version and number of unconsumed trailing bytes.

## Supported formats

- Puzzle format version 3.
- Solution format versions 6 and 7.
- Standard molecules, normal bonds, and the red/black/yellow channel bitmask
  used by triplex bonds. Parsed bonds retain their exact binary `rawCode`.
- Standard arms, Van Berlo wheel, tracks, glyphs, inputs and outputs represented as solution parts.
- Sparse arm instruction tapes.

Production-specific trailing structures and conduit payloads have not yet been confirmed. The parser therefore reports `trailingBytes` rather than silently claiming full coverage.

## Sources and credit

The implementation was independently written for Opus Codex using these public primary references:

- `gtw123/OpusSolver`, especially `OpusSolver/IO/PuzzleReader.cs` and `OpusSolver/IO/SolutionWriter.cs`, MIT License, copyright gtw123.
- `ianh/omsim`, used as the validation oracle and behavioral cross-reference. Its `COPYING` notice permits use without restriction.
- Armin Rigo's public `opus_magnum.py` Information Age puzzle generator as an additional historical format reference.

No upstream source code is copied verbatim. Field order, identifiers and format semantics necessarily follow the game file format documented by those projects.

See the repository-level `THIRD_PARTY_NOTICES.md` for full attribution and license notes.
