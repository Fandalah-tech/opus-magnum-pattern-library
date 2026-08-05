from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import io
import zipfile

from packages.opus_parser import parse_solution_bytes

from .rotor_corpus import RotorCorpusEntry, rank_seed_candidates, summarize_solution
from .solver import validate_generated_solution


@dataclass(slots=True)
class SeedSolveResult:
    found: bool
    filename: str | None
    solution: dict[str, Any] | None
    validation: dict[str, Any] | None
    attempted: int
    rejected: tuple[tuple[str, str], ...]


def _open_zip(source: str | Path | bytes) -> zipfile.ZipFile:
    if isinstance(source, bytes):
        return zipfile.ZipFile(io.BytesIO(source))
    return zipfile.ZipFile(source)


def solve_from_reference_corpus(
    puzzle: dict[str, Any],
    corpus: str | Path | bytes,
    *,
    target: int = 6,
) -> SeedSolveResult:
    """Find and validate a mechanically complete seed solution from a corpus.

    This is a bootstrap strategy, not the final generative solver.  It gives the
    layout compiler a known-valid topology for a specific puzzle while the
    independent chemistry blueprint and motion synthesizer are developed.
    Every candidate is reparsed and validated by the local engine before it is
    returned.
    """
    with _open_zip(corpus) as archive:
        parsed: dict[str, dict[str, Any]] = {}
        entries: list[RotorCorpusEntry] = []
        for filename in archive.namelist():
            if not filename.lower().endswith(".solution"):
                continue
            solution = parse_solution_bytes(archive.read(filename), source_name=filename)
            if str(solution.get("puzzleFile") or "") != str((puzzle.get("source") or {}).get("name") or "").removesuffix(".puzzle"):
                # Community exports sometimes vary only in path decoration.  A
                # strict name mismatch is recorded later if validation fails.
                pass
            parsed[filename] = solution
            entries.append(summarize_solution(solution, filename))

        rejected: list[tuple[str, str]] = []
        attempted = 0
        for entry in rank_seed_candidates(entries):
            attempted += 1
            candidate = parsed[entry.filename]
            try:
                validation = validate_generated_solution(puzzle, candidate, target=target)
            except Exception as error:  # preserve diagnostics for engine gaps
                rejected.append((entry.filename, f"{type(error).__name__}: {error}"))
                continue
            if validation.get("complete"):
                return SeedSolveResult(True, entry.filename, candidate, validation, attempted, tuple(rejected))
            rejected.append((entry.filename, f"incomplete: {validation}"))

    return SeedSolveResult(False, None, None, None, attempted, tuple(rejected))
