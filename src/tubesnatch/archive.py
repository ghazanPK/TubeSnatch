"""Remembers which videos were already downloaded ("only new videos" for playlists).

The file uses yt-dlp's --download-archive format ("youtube <id>" per line), so it can
be shared with the yt-dlp command line.
"""

from __future__ import annotations

from pathlib import Path


class Archive:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._keys: set[str] = set()
        self.reload()

    def reload(self) -> None:
        self._keys.clear()
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    self._keys.add(line.lower())
        except FileNotFoundError:
            pass

    def __contains__(self, key: str) -> bool:
        return bool(key) and key.lower() in self._keys

    def __len__(self) -> int:
        return len(self._keys)

    def add(self, key: str) -> None:
        if not key or key in self:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(key + "\n")
        self._keys.add(key.lower())

    def clear(self) -> None:
        self._keys.clear()
        self.path.unlink(missing_ok=True)
