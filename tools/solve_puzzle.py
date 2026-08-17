from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from packages.opus_parser import parse_puzzle
from packages.opus_solver import solve_puzzle_auto


_DEFAULT_FLOW_INDEX_CANDIDATES = (
    Path("database/engine-fragment-flow-index.json"),
    Path("database/fragment-flow-index.json"),
)


def _resolve_index_path(
    explicit: Path | None,
    *,
    environment_name: str,
    defaults: tuple[Path, ...],
) -> Path | None:
    if explicit is not None:
        return explicit
    environment_value = os.environ.get(environment_name)
    if environment_value:
        candidate = Path(environment_value)
        if candidate.exists():
            return candidate
    return next((candidate for candidate in defaults if candidate.exists()), None)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a solution with the autonomous Opus solver."
    )
    parser.add_argument("puzzle", type=Path, help="Path to an Opus Magnum .puzzle file")
    parser.add_argument("output", type=Path, help="Destination .solution file")
    parser.add_argument(
        "--flow-index",
        type=Path,
        help=(
            "Optional engine-coherent fragment-flow knowledge index. When omitted, "
            "OPUS_FLOW_INDEX and the standard database index locations are searched automatically."
        ),
    )
    parser.add_argument(
        "--fragment-index",
        type=Path,
        help=(
            "Optional fragment geometry index. When omitted, OPUS_FRAGMENT_INDEX is checked, "
            "then the resolved flow index is reused when it already contains fragment geometry."
        ),
    )
    parser.add_argument(
        "--composition-limit",
        type=int,
        default=10,
        help="Maximum learned assemblies attempted by the autonomous composition fallback.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report containing the manufacturing plan and validation",
    )
    args = parser.parse_args()

    puzzle = parse_puzzle(args.puzzle)
    flow_path = _resolve_index_path(
        args.flow_index,
        environment_name="OPUS_FLOW_INDEX",
        defaults=_DEFAULT_FLOW_INDEX_CANDIDATES,
    )
    fragment_path = _resolve_index_path(
        args.fragment_index,
        environment_name="OPUS_FRAGMENT_INDEX",
        defaults=(),
    )
    if fragment_path is None:
        fragment_path = flow_path

    flow_index = (
        json.loads(flow_path.read_text(encoding="utf-8"))
        if flow_path is not None
        else None
    )
    fragment_index = (
        json.loads(fragment_path.read_text(encoding="utf-8"))
        if fragment_path is not None
        else None
    )
    result = solve_puzzle_auto(
        puzzle,
        flow_index=flow_index,
        fragment_index=fragment_index,
        composition_limit=max(1, int(args.composition_limit)),
    )
    result.write(args.output)

    report = result.to_dict(include_solution=True)
    report["knowledgeResolution"] = {
        "flowIndex": str(flow_path) if flow_path is not None else None,
        "fragmentIndex": str(fragment_path) if fragment_path is not None else None,
        "flowIndexExplicit": args.flow_index is not None,
        "fragmentIndexExplicit": args.fragment_index is not None,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "puzzle": result.puzzle_name,
        "strategy": result.strategy,
        "route": result.validation.get("solverRoute"),
        "knowledge": report["knowledgeResolution"],
        "output": str(args.output),
        "validation": result.validation,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
