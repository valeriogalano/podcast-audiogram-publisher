import pytest
from pathlib import Path

from publisher.detector import detect_assets


def _make_soundbite(parent: Path, name: str, with_caption: bool = True) -> Path:
    sb = parent / name
    sb.mkdir()
    (sb / f"ep142_{name}_vertical.mp4").touch()
    (sb / f"ep142_{name}_square.mp4").touch()
    if with_caption:
        (sb / f"ep142_{name}_caption.txt").write_text("Title\n\nBody\n\n#tag")
    return sb


def test_detect_single_soundbite(tmp_path):
    sb = _make_soundbite(tmp_path, "sb1")
    assets = detect_assets(sb)
    assert len(assets) == 1
    assert assets[0].video_vertical.name == "ep142_sb1_vertical.mp4"
    assert assets[0].caption_file is not None


def test_detect_episode_folder(tmp_path):
    _make_soundbite(tmp_path, "sb1")
    _make_soundbite(tmp_path, "sb2")
    assets = detect_assets(tmp_path)
    assert len(assets) == 2
    names = {a.video_vertical.name for a in assets}
    assert "ep142_sb1_vertical.mp4" in names
    assert "ep142_sb2_vertical.mp4" in names


def test_detect_episode_folder_skips_sb_without_vertical(tmp_path):
    _make_soundbite(tmp_path, "sb1")
    empty_sb = tmp_path / "sb2"
    empty_sb.mkdir()
    # no vertical file
    assets = detect_assets(tmp_path)
    assert len(assets) == 1


def test_detect_missing_vertical_raises(tmp_path):
    sb = tmp_path / "sb1"
    sb.mkdir()
    (sb / "ep142_sb1_caption.txt").write_text("Title")
    with pytest.raises(FileNotFoundError, match="_vertical.mp4"):
        detect_assets(sb)


def test_detect_optional_files_none(tmp_path):
    sb = tmp_path / "sb1"
    sb.mkdir()
    (sb / "ep142_sb1_vertical.mp4").touch()
    assets = detect_assets(sb)
    assert assets[0].video_square is None
    assert assets[0].video_horizontal is None
    assert assets[0].caption_file is None


def test_detect_nonexistent_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        detect_assets(tmp_path / "does_not_exist")


def test_detect_file_instead_of_dir_raises(tmp_path):
    f = tmp_path / "file.mp4"
    f.touch()
    with pytest.raises(NotADirectoryError):
        detect_assets(f)
