from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.opus_analysis import solution_architecture_signature, specialization_axes
from packages.opus_parser import parse_solution


def analyze(root: Path) -> dict:
    records = []
    for path in sorted(root.glob("*.solution")):
        solution = parse_solution(path)
        records.append({
            "name": path.name,
            "puzzleFile": solution.get("puzzleFile"),
            "metrics": solution.get("metrics", {}),
            "signature": solution_architecture_signature(solution),
        })
    winners = specialization_axes(records)
    return {
        "schemaVersion": "0.1.0",
        "summary": {
            "solutionCount": len(records),
            "puzzleFiles": sorted({str(item["puzzleFile"]) for item in records}),
            "archetypes": dict(sorted(__import__("collections").Counter(
                item["signature"]["archetype"] for item in records
            ).items())),
        },
        "bestByMetric": {metric: value["name"] for metric, value in winners.items()},
        "solutions": records,
    }


def text_report(report: dict) -> str:
    lines = [
        "OPUS MAGNUM — SOLUTION PORTFOLIO ANALYSIS",
        "",
        f"Solutions: {report['summary']['solutionCount']}",
        f"Archetypes: {report['summary']['archetypes']}",
        "",
        "Best stored metrics:",
    ]
    lines.extend(f"- {metric}: {name}" for metric, name in report["bestByMetric"].items())
    lines.extend(["", "Architectures:"])
    for item in report["solutions"]:
        sig = item["signature"]
        m = item["metrics"]
        lines.extend([
            f"- {item['name']}",
            f"  metrics: cost={m.get('cost')} area={m.get('area')} cycles={m.get('cycles')} instructions={m.get('instructions')}",
            f"  archetype: {sig['archetype']}; parts={sig['partCount']}; arms={sig['armCount']}; tracks={sig['trackCount']}; pistons={sig['pistonCount']}",
            f"  program: entries={sig['programEntryCount']}; span={sig['programSpan']}; repeats={sig['repeatMarkerCount']}; period-overrides={sig['periodOverrideCount']}",
        ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a same-puzzle solution portfolio.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--text", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.root)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.text.write_text(text_report(report), encoding="utf-8")
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
