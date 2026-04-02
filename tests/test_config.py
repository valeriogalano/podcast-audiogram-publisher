import pytest
from pathlib import Path

from publisher.config import load_config


def _write_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(content)
    return p


def test_load_minimal_config(tmp_path):
    cfg_path = _write_config(tmp_path, "youtube:\n  enabled: true\n")
    config = load_config(cfg_path)
    assert config["youtube"]["enabled"] is True
    # defaults preserved
    assert config["youtube"]["privacy"] == "private"
    assert config["youtube"]["category_id"] == 22


def test_defaults_applied_for_missing_sections(tmp_path):
    cfg_path = _write_config(tmp_path, "input_dir: ./custom_output\n")
    config = load_config(cfg_path)
    assert config["input_dir"] == "./custom_output"
    assert config["instagram"]["enabled"] is False
    assert config["telegram"]["period"] == 86400


def test_deep_merge_overrides_leaf(tmp_path):
    cfg_path = _write_config(
        tmp_path,
        "youtube:\n  privacy: public\n  default_tags:\n    - mypodcast\n",
    )
    config = load_config(cfg_path)
    assert config["youtube"]["privacy"] == "public"
    assert config["youtube"]["default_tags"] == ["mypodcast"]
    # non-overridden keys still have defaults
    assert config["youtube"]["category_id"] == 22


def test_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="config.yaml"):
        load_config(tmp_path / "config.yaml")


def test_empty_config_uses_all_defaults(tmp_path):
    cfg_path = _write_config(tmp_path, "")
    config = load_config(cfg_path)
    assert config["input_dir"] == "./output"
    assert config["youtube"]["enabled"] is False
