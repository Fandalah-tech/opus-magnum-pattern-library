from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def solution_fingerprint(payload: bytes) -> str:
    """Stable identity for the exact binary solution sent to the validator."""
    return hashlib.sha256(payload).hexdigest()


class ValidatorCache:
    """Small persistent cache for remote validator responses.

    The cache is intentionally keyed by the exact encoded solution bytes plus a
    protocol namespace. A validator endpoint/protocol change can therefore use
    another namespace without trusting stale responses.
    """

    def __init__(self, path: Path, namespace: str) -> None:
        self.path = Path(path)
        self.namespace = namespace
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict) or raw.get("namespace") != self.namespace:
            return
        entries = raw.get("entries")
        if isinstance(entries, dict):
            self._entries = {
                str(key): value for key, value in entries.items()
                if isinstance(value, dict)
            }

    def get(self, fingerprint: str) -> dict[str, Any] | None:
        value = self._entries.get(fingerprint)
        return dict(value) if value is not None else None

    def put(self, fingerprint: str, value: dict[str, Any]) -> None:
        self._entries[fingerprint] = dict(value)
        self.flush()

    def __len__(self) -> int:
        return len(self._entries)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "namespace": self.namespace,
            "entries": self._entries,
        }
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp.replace(self.path)
