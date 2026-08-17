from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
from typing import Any


def _slug(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    return text.strip("-") or "learned"


def _metric_suffix(metrics: dict[str, Any]) -> str:
    pieces = []
    for key, suffix in (
        ("boundingHexagon", "h"),
        ("cycles", "c"),
        ("cost", "g"),
        ("area", "a"),
        ("instructions", "i"),
    ):
        value = metrics.get(key)
        if isinstance(value, int):
            pieces.append(f"{value}{suffix}")
    return "-".join(pieces) or "learned"


def _focus_objectives(objective: str) -> list[str]:
    if objective == "cga":
        return ["cycles"]
    if objective == "bca":
        return ["bca"]
    return [objective]


def entries_from_materialization(
    report: dict[str, Any],
    *,
    persist_dir: Path,
    repository_root: Path,
) -> list[dict[str, Any]]:
    puzzle_file = str(report.get("puzzleFile") or "")
    if not puzzle_file:
        raise ValueError("Materialization report is missing puzzleFile")

    persist_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for item in report.get("results", []):
        if not item.get("complete"):
            continue
        source_raw = item.get("outputFile")
        if not source_raw:
            raise ValueError(
                f"Complete architecture {item.get('architectureId')!r} has no outputFile"
            )
        source = Path(str(source_raw))
        if not source.exists():
            raise FileNotFoundError(source)

        objective = str(item.get("objective") or "learned")
        architecture_id = str(item.get("architectureId") or source.stem)
        metrics = dict(item.get("referenceMetrics") or {})
        filename = (
            f"{_slug(puzzle_file)}-{_slug(objective)}-"
            f"{_metric_suffix(metrics)}-{_slug(architecture_id)[:18]}.solution"
        )
        destination = persist_dir / filename
        shutil.copyfile(source, destination)
        try:
            relative_solution = destination.resolve().relative_to(repository_root.resolve())
        except ValueError as error:
            raise ValueError(
                f"Persisted learned solution must live under repository root: {destination}"
            ) from error

        provenance = {
            **dict(item.get("provenance") or {}),
            "kind": "learned-materialized-blueprint",
            "materializedFromLearnedBlueprint": True,
            "originalSolutionBytesCommitted": False,
            "sourceMaterializationReport": report.get("portfolio"),
            "outputSha256": item.get("outputSha256"),
        }
        entries.append({
            "id": f"{_slug(puzzle_file)}-{_slug(objective)}-{_slug(architecture_id)}",
            "puzzleFile": puzzle_file,
            "solutionPath": relative_solution.as_posix(),
            "focusObjectives": _focus_objectives(objective),
            "referenceMetrics": metrics,
            "canonicalStructuralHash": item.get("canonicalStructuralHash"),
            "canonicalMechanismHash": item.get("canonicalMechanismHash"),
            "provenance": provenance,
            "sourceKey": f"{puzzle_file}:{objective}:{architecture_id}",
        })
    return entries


def merge_bank(
    current: dict[str, Any],
    new_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    retained = {
        str(item.get("sourceKey") or item.get("id")): item
        for item in current.get("entries", [])
    }
    for item in new_entries:
        retained[str(item.get("sourceKey") or item.get("id"))] = item
    entries = sorted(
        retained.values(),
        key=lambda item: (
            str(item.get("puzzleFile") or ""),
            str(item.get("focusObjectives") or ""),
            str(item.get("id") or ""),
        ),
    )
    return {
        "schemaVersion": "0.2.0",
        "kind": "learned-solution-bank",
        "summary": {
            "entryCount": len(entries),
            "puzzleCount": len({str(item.get('puzzleFile') or '') for item in entries}),
        },
        "entries": entries,
    }


def update_bank(
    report_path: Path,
    bank_path: Path,
    *,
    persist_dir: Path,
    repository_root: Path,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    current = (
        json.loads(bank_path.read_text(encoding="utf-8"))
        if bank_path.exists()
        else {"entries": []}
    )
    entries = entries_from_materialization(
        report,
        persist_dir=persist_dir,
        repository_root=repository_root,
    )
    updated = merge_bank(current, entries)
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    bank_path.write_text(
        json.dumps(updated, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "schemaVersion": "0.1.0",
        "report": str(report_path),
        "bank": str(bank_path),
        "persistDir": str(persist_dir),
        "addedOrUpdated": len(entries),
        "summary": updated["summary"],
        "entryIds": [item["id"] for item in entries],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Persist complete learned materializations and merge them into the "
            "autonomous solver's learned-solution bank."
        )
    )
    parser.add_argument("--materialization-report", type=Path, required=True)
    parser.add_argument(
        "--bank",
        type=Path,
        default=Path("database/learned-solution-bank.json"),
    )
    parser.add_argument("--persist-dir", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = update_bank(
        args.materialization_report,
        args.bank,
        persist_dir=args.persist_dir,
        repository_root=args.repository_root,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
