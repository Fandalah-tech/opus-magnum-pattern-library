from __future__ import annotations

import tools.run_rotor_a41_remote_fresh as fresh


def test_archive_checkpoint_copies_before_removing_source(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint.json"
    archive = tmp_path / "checkpoint.previous.json"
    payload = b'{"schemaVersion":2,"testedCandidates":150}\n'
    checkpoint.write_bytes(payload)

    monkeypatch.setattr(fresh.cached.campaign, "CHECKPOINT", checkpoint)
    monkeypatch.setattr(fresh, "ARCHIVE", archive)

    assert fresh.archive_checkpoint() is True
    assert not checkpoint.exists()
    assert archive.read_bytes() == payload


def test_archive_checkpoint_is_noop_when_missing(tmp_path, monkeypatch):
    checkpoint = tmp_path / "missing.json"
    archive = tmp_path / "checkpoint.previous.json"
    monkeypatch.setattr(fresh.cached.campaign, "CHECKPOINT", checkpoint)
    monkeypatch.setattr(fresh, "ARCHIVE", archive)

    assert fresh.archive_checkpoint() is False
    assert not archive.exists()
