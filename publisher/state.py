import json
import os
import tempfile
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(json.dumps(self._data, indent=2))
                tmp.write("\n")
                tmp_path = Path(tmp.name)
            os.replace(tmp_path, self.path)
        except Exception:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            raise

    def is_published(self, platform: str, key: str) -> bool:
        return key in self._data.get(platform, [])

    def mark_published(self, platform: str, key: str) -> None:
        entries = self._data.setdefault(platform, [])
        if key not in entries:
            entries.append(key)
            self._save()
