from __future__ import annotations

import json

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


def test_generation_report_recommends_next_only_after_real_gain(tmp_path, monkeypatch):
    report = tmp_path / "generation.json"
    archive = tmp_path / "checkpoint.previous.json"
    monkeypatch.setattr(fresh, "GENERATION", report)
    monkeypatch.setattr(fresh, "ARCHIVE", archive)

    fresh.write_generation_report(
        archived=True,
        start_cycles=1100,
        final_cycles=1094,
        exit_code=0,
        status="completed",
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["improved"] is True
    assert data["cycleGain"] == 6
    assert data["recommendedNextGeneration"] is True

    fresh.write_generation_report(
        archived=True,
        start_cycles=1094,
        final_cycles=1094,
        exit_code=0,
        status="completed",
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["improved"] is False
    assert data["cycleGain"] == 0
    assert data["recommendedNextGeneration"] is False


def test_generation_report_does_not_recommend_retry_after_failure(tmp_path, monkeypatch):
    report = tmp_path / "generation.json"
    monkeypatch.setattr(fresh, "GENERATION", report)

    fresh.write_generation_report(
        archived=False,
        start_cycles=1100,
        final_cycles=1090,
        exit_code=5,
        status="failed",
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["improved"] is True
    assert data["recommendedNextGeneration"] is False
