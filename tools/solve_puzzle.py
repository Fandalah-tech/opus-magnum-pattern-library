from __future__ import annotations

import argparse
from itertools import count
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.opus_parser import parse_puzzle, write_solution
from packages.opus_solver import solve_puzzle_auto
from packages.opus_solver.autonomous import KNOWLEDGE_OBJECTIVES, LOCAL_OBJECTIVES
from tools.omsim_adapter.validate import run_omsim


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
        description="Generate and optionally oracle-optimize a solution with the autonomous Opus solver."
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
        "--objective",
        choices=KNOWLEDGE_OBJECTIVES,
        default="balanced",
        help=(
            "Optimization objective. Without --omsim only balanced, cycles and instructions are "
            "available as local ranking signals. With --omsim, cost/area/cycles/rate/instructions/"
            "costarea/costcycles/sum4 use authoritative OMSim metrics."
        ),
    )
    parser.add_argument(
        "--omsim",
        type=Path,
        help="Optional OMSim executable used as the authoritative validator and objective scorer.",
    )
    parser.add_argument(
        "--omsim-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for each OMSim candidate validation.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report containing the manufacturing plan and validation",
    )
    args = parser.parse_args()

    if args.omsim is None and args.objective not in LOCAL_OBJECTIVES:
        parser.error(
            f"--objective {args.objective!r} requires --omsim; without OMSim choose one of {LOCAL_OBJECTIVES}"
        )

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

    with TemporaryDirectory(prefix="opus-autonomous-oracle-") as oracle_temp_name:
        oracle_counter = count()

        def omsim_validator(solution: dict) -> dict:
            candidate_path = Path(oracle_temp_name) / f"candidate-{next(oracle_counter):04d}.solution"
            write_solution(solution, candidate_path, version=7)
            return run_omsim(
                args.omsim,
                args.puzzle,
                candidate_path,
                max(1, int(args.omsim_timeout)),
                output_intervals=True,
            )

        result = solve_puzzle_auto(
            puzzle,
            flow_index=flow_index,
            fragment_index=fragment_index,
            composition_limit=max(1, int(args.composition_limit)),
            objective=args.objective,
            oracle_validator=omsim_validator if args.omsim is not None else None,
            oracle_name="omsim" if args.omsim is not None else "oracle",
        )

    result.write(args.output)

    report = result.to_dict(include_solution=True)
    report["knowledgeResolution"] = {
        "flowIndex": str(flow_path) if flow_path is not None else None,
        "fragmentIndex": str(fragment_path) if fragment_path is not None else None,
        "flowIndexExplicit": args.flow_index is not None,
        "fragmentIndexExplicit": args.fragment_index is not None,
    }
    report["oracleResolution"] = {
        "enabled": args.omsim is not None,
        "name": "omsim" if args.omsim is not None else None,
        "binary": str(args.omsim) if args.omsim is not None else None,
        "timeoutSeconds": max(1, int(args.omsim_timeout)) if args.omsim is not None else None,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "puzzle": result.puzzle_name,
        "strategy": result.strategy,
        "route": result.validation.get("solverRoute"),
        "objective": result.validation.get("optimizationObjective"),
        "metricSource": result.validation.get("optimizationMetricSource"),
        "localMetrics": result.validation.get("localCandidateMetrics"),
        "oracleMetrics": result.validation.get("oracleMetrics"),
        "knowledge": report["knowledgeResolution"],
        "oracle": report["oracleResolution"],
        "output": str(args.output),
        "validation": result.validation,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
