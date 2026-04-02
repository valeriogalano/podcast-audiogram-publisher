import json
from pathlib import Path


class PublishState:
    """Persists which soundbites have been published, keyed by platform name.

    State file format::

        {
          "youtube":   ["ep142/sb1", "ep142/sb2"],
          "instagram": ["ep142/sb1"]
        }

    Keys are paths relative to the output directory (e.g. ``ep142/sb1``).
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict[str, list[str]] = self._load()

    def _load(self) -> dict[str, list[str]]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def is_published(self, platform: str, key: str) -> bool:
        return key in self._data.get(platform, [])

    def mark_published(self, platform: str, key: str) -> None:
        entries = self._data.setdefault(platform, [])
        if key not in entries:
            entries.append(key)
            self._save()
