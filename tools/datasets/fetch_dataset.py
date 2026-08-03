from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "datasets" / "registry.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(dataset_id: str) -> dict:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for dataset in registry["datasets"]:
        if dataset["id"] == dataset_id:
            return dataset
    raise SystemExit(f"Unknown dataset: {dataset_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a registered external dataset without committing it.")
    parser.add_argument("dataset_id")
    parser.add_argument("--output-dir", default=str(ROOT / ".datasets"))
    parser.add_argument("--accept-unknown-license", action="store_true")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset_id)
    license_status = dataset["license"]["status"]
    if license_status == "unknown" and not args.accept_unknown_license:
        raise SystemExit(
            "Dataset has no confirmed redistribution license. "
            "Use --accept-unknown-license only for local evaluation and do not redistribute the downloaded files."
        )

    source = dataset.get("source")
    if not source or not source.lower().endswith((".zip", ".tar", ".tar.gz", ".tgz")):
        raise SystemExit("Registered source is not a directly downloadable archive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".tar.gz" if source.lower().endswith(".tar.gz") else Path(source).suffix
    output_path = output_dir / f"{dataset['id']}{suffix}"

    request = urllib.request.Request(source, headers={"User-Agent": "Opus-Codex-Dataset-Fetcher/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, output_path.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)

    print(json.dumps({
        "datasetId": dataset["id"],
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "licenseStatus": license_status,
        "redistribution": dataset["license"]["redistribution"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
