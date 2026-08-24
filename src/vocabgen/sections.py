import re
from typing import List


def normalize_separator_line(line: str) -> bool:
    """Return whether a line is a supported inbox section separator."""
    if not line:
        return False
    separator = line.strip()
    if re.fullmatch(r"[-—]{2,}", separator):
        return True
    if re.fullmatch(r"\*{3,}", separator):
        return True
    if re.fullmatch(r"_{3,}", separator):
        return True
    return False


def split_sections(text: str) -> List[str]:
    """Split inbox text on separator lines, with blank paragraphs as fallback."""
    lines = text.splitlines()
    separators = [
        index for index, line in enumerate(lines) if normalize_separator_line(line)
    ]
    if separators:
        sections = []
        start = 0
        for index in separators:
            section = "\n".join(lines[start:index]).strip()
            if section:
                sections.append(section)
            start = index + 1
        final_section = "\n".join(lines[start:]).strip()
        if final_section:
            sections.append(final_section)
        return sections

    parts = re.split(r"\n\s*\n\s*\n+", text)
    return [part.strip() for part in parts if part.strip()]
