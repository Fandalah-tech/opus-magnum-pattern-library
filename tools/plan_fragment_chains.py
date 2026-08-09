from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.opus_solver import build_composition_prior


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank empirical fragment composition chains from the canonical flow index.")
    parser.add_argument("--flow-index", type=Path, default=Path("database/fragment-flow-index.json"))
    parser.add_argument("--fragment-index", type=Path, default=Path("database/fragment-index.json"))
    parser.add_argument("--output", type=Path, default=Path("database/composition-prior.json"))
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    flow_index = json.loads(args.flow_index.read_text(encoding="utf-8"))
    fragment_index = json.loads(args.fragment_index.read_text(encoding="utf-8")) if args.fragment_index.exists() else None
    prior = build_composition_prior(flow_index, fragment_index=fragment_index, max_depth=args.max_depth, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(prior, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(prior["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
