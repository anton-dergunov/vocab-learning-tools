from pathlib import Path
import re
from typing import Iterable, List


def normalize_separator_line(line: str) -> bool:
    """
    Return True if this line should be treated as a section separator.
    Accepts:
      - lines of two or more hyphens: '---', '-----'
      - lines of two or more em-dashes: '———' (iPhone converts)
      - lines with only asterisks '***'
      - lines with only '___'
    """
    if not line:
        return False
    s = line.strip()
    if re.fullmatch(r"[-—]{2,}", s):
        return True
    if re.fullmatch(r"\*{3,}", s):
        return True
    if re.fullmatch(r"_{3,}", s):
        return True
    return False


def split_sections(text: str) -> List[str]:
    """
    Split the inbox text into sections. We use separator lines as primary delimiter.
    If no separators found, fallback to splitting by 2+ consecutive blank lines.
    Strips leading/trailing whitespace from each section.
    """
    lines = text.splitlines()
    separators = [i for i, ln in enumerate(lines) if normalize_separator_line(ln)]
    if separators:
        sections = []
        start = 0
        for idx in separators:
            # create chunk from start..idx
            chunk = "\n".join(lines[start:idx]).strip()
            if chunk:
                sections.append(chunk)
            start = idx + 1
        # final chunk
        last = "\n".join(lines[start:]).strip()
        if last:
            sections.append(last)
        return sections
    # fallback: split by 2+ blank lines
    parts = re.split(r"\n\s*\n\s*\n+", text)
    return [p.strip() for p in parts if p.strip()]


class DraftInbox:
    """
    Manage a simple single-file inbox that contains multiple draft
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
        # Robust split: split on line consisting of 3+ dashes, allowing surrounding whitespace/newlines
        parts = re.split(r"\n-{3,}\n", text.strip(), flags=re.MULTILINE)
        parts = [p.strip() for p in parts if p.strip()]
        self._raw = text
        self.entries = parts

    def __len__(self) -> int:
        return len(self.entries)

    def iter_entries(self) -> Iterable[str]:
        yield from self.entries

    def get_slice(self, start: int, n: int) -> List[str]:
        """Return a list of entries from start (inclusive) to start+n (exclusive)."""
        return self.entries[start:start + n]

    def remove_slice(self, start: int, n: int) -> None:
        """Remove entries from start (inclusive) to start+n (exclusive) and write the file immediately."""
        del self.entries[start:start + n]
        self._write()

    def _write(self):
        if not self.entries:
            # clear file
            self.path.write_text("", encoding="utf-8")
            return

        joined = self.SEPARATOR.join(entry.strip() for entry in self.entries)
        # keep one leading/trailing newline consistent with examples
        content = joined.strip() + "\n"
        self.path.write_text(content, encoding="utf-8")
