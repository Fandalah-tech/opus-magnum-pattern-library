from __future__ import annotations

from pathlib import Path

from tools.a41_validator_cache import ValidatorCache, solution_fingerprint


def test_solution_fingerprint_is_stable_and_content_sensitive() -> None:
    assert solution_fingerprint(b"abc") == solution_fingerprint(b"abc")
    assert solution_fingerprint(b"abc") != solution_fingerprint(b"abd")


def test_validator_cache_persists_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    cache = ValidatorCache(path, "validator:/api/v1/analyze")
    key = solution_fingerprint(b"candidate")
    value = {"ok": True, "response": {"valid": True, "metrics": {"cycles": 1099}}, "error": None}
    cache.put(key, value)

    loaded = ValidatorCache(path, "validator:/api/v1/analyze")
    assert len(loaded) == 1
    assert loaded.get(key) == value


def test_validator_cache_rejects_other_namespace(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    first = ValidatorCache(path, "validator:v1")
    first.put(solution_fingerprint(b"candidate"), {"ok": True})

    second = ValidatorCache(path, "validator:v2")
    assert len(second) == 0
