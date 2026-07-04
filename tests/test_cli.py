"""Tests for auto-mode --limit behaviour in the CLI."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from publisher.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_soundbite(parent: Path, ep: str, sb: str) -> Path:
    folder = parent / ep / sb
    folder.mkdir(parents=True)
    (folder / f"{ep}_{sb}_vertical.mp4").touch()
    (folder / f"{ep}_{sb}_caption.txt").write_text(f"{ep} {sb} Title\n\nBody\n\n#tag")
    return folder


def _make_config(tmp_path: Path, output_dir: Path, state_file: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"input_dir: {output_dir}\n"
        f"state_file: {state_file}\n"
        "youtube:\n  enabled: true\n"
    )
    return cfg


def _mock_platform(publish_side_effect=None):
    """Return a mock platform class."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.is_configured.return_value = True
    if publish_side_effect:
        mock_instance.publish.side_effect = publish_side_effect
    else:
        mock_instance.publish.return_value = "ok"
    mock_cls.return_value = mock_instance
    return mock_cls


def _published_keys(state_file: Path) -> list[str]:
    if not state_file.exists():
        return []
    data = json.loads(state_file.read_text())
    keys: set[str] = set()
    for entries in data.values():
        keys.update(entries)
    return sorted(keys)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAutoModeLimit:
    """--limit controls how many soundbites are published per run."""

    def _setup(self, tmp_path, limit=None, extra_args=None):
        output_dir = tmp_path / "output"
        state_file = tmp_path / "published.json"
        config_file = _make_config(tmp_path, output_dir, state_file)

        for sb in ("sb1", "sb2", "sb3"):
            _make_soundbite(output_dir, "ep01", sb)

        argv = ["--config", str(config_file), "--state-file", str(state_file)]
        if limit is not None:
            argv += ["--limit", str(limit)]
        if extra_args:
            argv += extra_args

        return argv, state_file

    def test_default_limit_publishes_one(self, tmp_path):
        argv, state_file = self._setup(tmp_path)
        with patch("publisher.cli.PLATFORM_REGISTRY", {"youtube": _mock_platform()}):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 0
        assert len(_published_keys(state_file)) == 1

    def test_limit_2_publishes_two(self, tmp_path):
        argv, state_file = self._setup(tmp_path, limit=2)
        with patch("publisher.cli.PLATFORM_REGISTRY", {"youtube": _mock_platform()}):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 0
        assert len(_published_keys(state_file)) == 2

    def test_limit_larger_than_available_publishes_all(self, tmp_path):
        argv, state_file = self._setup(tmp_path, limit=10)
        with patch("publisher.cli.PLATFORM_REGISTRY", {"youtube": _mock_platform()}):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 0
        assert len(_published_keys(state_file)) == 3  # only 3 soundbites exist

    def test_dry_run_does_not_update_state(self, tmp_path):
        argv, state_file = self._setup(tmp_path, limit=2, extra_args=["--dry-run"])
        with patch("publisher.cli.PLATFORM_REGISTRY", {"youtube": _mock_platform()}):
            with pytest.raises(SystemExit) as exc:
                main(argv)
        assert exc.value.code == 0
        assert _published_keys(state_file) == []

    def test_second_run_skips_already_published(self, tmp_path):
        argv, state_file = self._setup(tmp_path, limit=1)
        registry = {"youtube": _mock_platform()}

        with patch("publisher.cli.PLATFORM_REGISTRY", registry):
            with pytest.raises(SystemExit):
                main(argv)
        after_first = _published_keys(state_file)
        assert len(after_first) == 1

        with patch("publisher.cli.PLATFORM_REGISTRY", registry):
            with pytest.raises(SystemExit):
                main(argv)
        after_second = _published_keys(state_file)
        assert len(after_second) == 2
        assert after_first[0] != after_second[-1]

    def test_limit_is_per_platform_so_broken_platform_does_not_block_healthy_ones(self, tmp_path):
        output_dir = tmp_path / "output"
        state_file = tmp_path / "published.json"
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            f"input_dir: {output_dir}\n"
            f"state_file: {state_file}\n"
            "youtube:\n  enabled: true\n"
            "telegram:\n  enabled: true\n  api_id: 1\n  api_hash: test\n"
        )
        for sb in ("sb1", "sb2"):
            _make_soundbite(output_dir, "ep01", sb)
        state_file.write_text(json.dumps({"youtube": ["ep01/sb1"]}))

        registry = {
            "youtube": _mock_platform(),
            "telegram": _mock_platform(RuntimeError("telegram down")),
        }
        argv = ["--config", str(config_file), "--state-file", str(state_file), "--limit", "1"]

        with patch("publisher.cli.PLATFORM_REGISTRY", registry):
            with pytest.raises(SystemExit) as exc:
                main(argv)

        assert exc.value.code == 1
        data = json.loads(state_file.read_text())
        assert "ep01/sb2" in data["youtube"]
        assert "telegram" not in data
