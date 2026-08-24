from pathlib import Path
from typing import Iterable, List

from ..fileops import atomic_write
from ..sections import normalize_separator_line, split_sections


class DraftInbox:
    """
    Manage a simple single-file inbox that contains multiple drafts.
    """
    SEPARATOR = "\n---\n"

    def __init__(self, path: Path):
        self.path = Path(path)
        self._load()

    def _load(self):
        if not self.path.exists():
            self._raw = ""
            self.entries: List[str] = []
            return

        text = self.path.read_text(encoding="utf-8")
        self._raw = text
        self.entries = split_sections(text.strip())

    def __len__(self) -> int:
        return len(self.entries)

    def iter_entries(self) -> Iterable[str]:
        yield from self.entries

    def get_slice(self, start: int, n: int) -> List[str]:
        """Return a list of entries from start (inclusive) to start+n (exclusive)."""
        return self.entries[start:start + n]

    def remove_slice(self, start: int, n: int) -> None:
        """Atomically persist removal, then update the in-memory entries."""
        remaining = self.entries[:start] + self.entries[start + n:]
        content = self._serialize(remaining)
        atomic_write(self.path, content)
        self.entries = remaining
        self._raw = content

    def _write(self):
        content = self._serialize(self.entries)
        atomic_write(self.path, content)
        self._raw = content

    def _serialize(self, entries: List[str]) -> str:
        if not entries:
            return ""
        joined = self.SEPARATOR.join(entry.strip() for entry in entries)
        return joined.strip() + "\n"
