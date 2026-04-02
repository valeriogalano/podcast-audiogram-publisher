import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SoundbiteAssets:
    folder: Path
    video_vertical: Path
    video_square: Path | None = None
    video_horizontal: Path | None = None
    caption_file: Path | None = None


def _detect_soundbite(folder: Path) -> SoundbiteAssets:
    vertical = next(folder.glob("*_vertical.mp4"), None)
    if vertical is None:
        raise FileNotFoundError(f"No *_vertical.mp4 found in {folder}")
    return SoundbiteAssets(
        folder=folder,
        video_vertical=vertical,
        video_square=next(folder.glob("*_square.mp4"), None),
        video_horizontal=next(folder.glob("*_horizontal.mp4"), None),
        caption_file=next(folder.glob("*_caption.txt"), None),
    )


def _ep_number(path: Path) -> int:
    m = re.match(r"ep(\d+)", path.name, re.IGNORECASE)
    return int(m.group(1)) if m else -1


def _sb_number(path: Path) -> int:
    m = re.match(r"sb(\d+)", path.name, re.IGNORECASE)
    return int(m.group(1)) if m else -1


def soundbite_key(output_dir: Path, assets: SoundbiteAssets) -> str:
    """Stable identifier for a soundbite relative to output_dir (e.g. ``ep142/sb1``)."""
    return str(assets.folder.relative_to(output_dir))


def scan_output_dir(output_dir: str | Path) -> list[SoundbiteAssets]:
    """Return all soundbites found under *output_dir*, ordered by episode number
    descending (newest first) then soundbite number ascending within each episode.
    """
    root = Path(output_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Output dir is not a directory: {root}")

    ep_dirs = sorted(
        (p for p in root.iterdir() if p.is_dir() and re.match(r"ep\d+", p.name, re.IGNORECASE)),
        key=_ep_number,
        reverse=True,
    )

    result: list[SoundbiteAssets] = []
    for ep_dir in ep_dirs:
        sb_dirs = sorted(
            (p for p in ep_dir.iterdir() if p.is_dir() and re.match(r"sb\d+", p.name, re.IGNORECASE)),
            key=_sb_number,
        )
        for sb_dir in sb_dirs:
            try:
                result.append(_detect_soundbite(sb_dir))
            except FileNotFoundError:
                pass
    return result


def detect_assets(input_path: str | Path) -> list[SoundbiteAssets]:
    path = Path(input_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {path}")

    # Check if this is an episode folder (contains sb* subdirs) or a soundbite folder
    sb_dirs = sorted(p for p in path.iterdir() if p.is_dir() and p.name.startswith("sb"))
    if sb_dirs:
        assets = []
        for sb_dir in sb_dirs:
            try:
                assets.append(_detect_soundbite(sb_dir))
            except FileNotFoundError:
                pass  # skip subdirs without a vertical video
        if not assets:
            raise FileNotFoundError(f"No soundbites with *_vertical.mp4 found under {path}")
        return assets

    # Treat it as a single soundbite folder
    return [_detect_soundbite(path)]
