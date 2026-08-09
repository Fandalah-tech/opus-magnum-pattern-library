from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_solver.library import build_solver_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a solver-ready mechanism index from solution archive analysis.")
    parser.add_argument("--analysis", type=Path, default=Path("reports/solution-archive-analysis.json"))
    parser.add_argument("--output", type=Path, default=Path("database/solver-index.json"))
    args = parser.parse_args()

    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    index = build_solver_index(analysis)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(index["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
