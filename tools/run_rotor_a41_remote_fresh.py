from __future__ import annotations

import json
import shutil
from pathlib import Path

import tools.run_rotor_a41_remote_cached as cached

ARCHIVE = Path("reports/rotor-a41-cycle-checkpoint.previous.json")
GENERATION = Path("reports/rotor-a41-campaign-generation.json")


def archive_checkpoint() -> bool:
    checkpoint = cached.campaign.CHECKPOINT
    if not checkpoint.is_file():
        return False
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(checkpoint, ARCHIVE)
    checkpoint.unlink()
    return True


def main() -> int:
    archived = archive_checkpoint()
    payload = {
        "schemaVersion": 1,
        "mode": "fresh-generation",
        "checkpointArchived": archived,
        "checkpointArchive": str(ARCHIVE) if archived else None,
        "searchStrategy": cached.SEARCH_STRATEGY,
        "maxIdleJump": cached.MAX_IDLE_JUMP,
    }
    GENERATION.parent.mkdir(parents=True, exist_ok=True)
    GENERATION.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cached.main()


if __name__ == "__main__":
    raise SystemExit(main())
