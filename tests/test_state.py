"""Unit tests for publisher.state.PublishState."""
import json
import os

import pytest

from publisher.state import PublishState


class TestPublishState:
    def test_is_not_published_on_empty_state(self, tmp_path):
        state = PublishState(tmp_path / "published.json")
        assert state.is_published("youtube", "ep1/sb1") is False

    def test_mark_published_persists(self, tmp_path):
        path = tmp_path / "published.json"
        state = PublishState(path)
        state.mark_published("youtube", "ep1/sb1")
        assert state.is_published("youtube", "ep1/sb1") is True

    def test_mark_published_writes_file(self, tmp_path):
        path = tmp_path / "published.json"
        state = PublishState(path)
        state.mark_published("youtube", "ep1/sb1")
        assert path.exists()
        data = json.loads(path.read_text())
        assert "ep1/sb1" in data["youtube"]

    def test_mark_published_creates_parent_directory(self, tmp_path):
        path = tmp_path / "nested" / "published.json"
        state = PublishState(path)
        state.mark_published("youtube", "ep1/sb1")
        assert json.loads(path.read_text()) == {"youtube": ["ep1/sb1"]}

    def test_failed_atomic_replace_keeps_existing_file(self, tmp_path, monkeypatch):
        path = tmp_path / "published.json"
        path.write_text(json.dumps({"youtube": ["ep1/sb1"]}), encoding="utf-8")
        state = PublishState(path)

        def fail_replace(source, target):
            raise RuntimeError("replace failed")

        monkeypatch.setattr(os, "replace", fail_replace)
        with pytest.raises(RuntimeError, match="replace failed"):
            state.mark_published("youtube", "ep1/sb2")

        assert json.loads(path.read_text(encoding="utf-8")) == {"youtube": ["ep1/sb1"]}
        assert list(tmp_path.glob(".published.json.*.tmp")) == []

    def test_state_loaded_from_existing_file(self, tmp_path):
        path = tmp_path / "published.json"
        path.write_text(json.dumps({"youtube": ["ep1/sb1"]}))
        state = PublishState(path)
        assert state.is_published("youtube", "ep1/sb1") is True

    def test_platform_isolation(self, tmp_path):
        state = PublishState(tmp_path / "published.json")
        state.mark_published("youtube", "ep1/sb1")
        assert state.is_published("instagram", "ep1/sb1") is False

    def test_no_duplicate_entries(self, tmp_path):
        path = tmp_path / "published.json"
        state = PublishState(path)
        state.mark_published("youtube", "ep1/sb1")
        state.mark_published("youtube", "ep1/sb1")  # second call, same key
        data = json.loads(path.read_text())
        assert data["youtube"].count("ep1/sb1") == 1

    def test_multiple_platforms(self, tmp_path):
        state = PublishState(tmp_path / "published.json")
        state.mark_published("youtube", "ep1/sb1")
        state.mark_published("instagram", "ep1/sb2")
        assert state.is_published("youtube", "ep1/sb1") is True
        assert state.is_published("instagram", "ep1/sb2") is True
        assert state.is_published("youtube", "ep1/sb2") is False

    def test_missing_file_starts_empty(self, tmp_path):
        state = PublishState(tmp_path / "nonexistent.json")
        assert state.is_published("youtube", "ep1/sb1") is False
