from __future__ import annotations
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import logging
import difflib

from .fileops import atomic_write, append_to_file, read_text, backup_file

logger = logging.getLogger("vocabgen.vocab_processor")

# Allowed topics
ALLOWED_TOPICS = [
    "Emotions",
    "Actions",
    "Nature",
    "Culture",
    "Food",
    "Health",
    "Appearance",
    "Technology",
    "Travel",
    "Slang",
    "Misc",
]

# Suffix used when creating topic files if no existing " - Topic.md" file exists.
# Use this suffix for files you want to ignore in git (.gen.md recommended).
DEFAULT_GEN_SUFFIX = ".gen.md"


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


def join_sections_for_batch(sections: List[str], sep: str = "\n\n---\n\n") -> str:
    """
    Join multiple sections into a single chunk for LLM consumption.
    Use `sep` to clearly indicate separation.
    """
    # Use triple-dash separator because your prompt instructs LLM to split with '---'
    return sep.join(s.strip() for s in sections if s.strip())


def clean_llm_text_block(block: str) -> str:
    """
    Clean a single LLM-generated block:
    - remove code fences ```...```
    - remove leading/trailing whitespace
    - remove duplicated separators inside
    - ensure it ends with a single newline
    """
    # remove fenced code blocks
    block = re.sub(r"```(?:[\s\S]*?)```", "", block)
    # remove any '---' separators inside the block (we treat top-level separators only)
    block = re.sub(r"(^|\n)\s*-{3,}\s*(\n|$)", "\n", block)
    block = block.strip()
    if not block.endswith("\n"):
        block = block + "\n"
    return block


def split_llm_response_into_articles(llm_text: str) -> List[str]:
    """
    Split LLM response into articles. It is expected LLM separates multiple articles with '---'.
    We accept --- or triple newline.
    """
    # split on lines containing 3+ hyphens
    chunks = re.split(r"\n\s*-{3,}\s*\n", llm_text)
    # fallback: also split by two+ newlines if only one chunk
    if len(chunks) == 1:
        chunks = re.split(r"\n\s*\n\s*\n+", llm_text)
    return [clean_llm_text_block(c) for c in chunks if c.strip()]


_topic_re = re.compile(r"^Topic:\s*(?P<topic>.+)\s*$", re.IGNORECASE | re.MULTILINE)
_title_re = re.compile(r"^#{1,6}\s*\*\*(?P<title>.+?)\*\*", re.IGNORECASE | re.MULTILINE)


def extract_topic_from_article(article: str) -> Optional[str]:
    """
    Extract the Topic: <TopicName> line from the article.
    If found, return normalized topic if it's in ALLOWED_TOPICS. Otherwise return 'Misc'.
    If not found, return None.
    """
    m = _topic_re.search(article)
    if not m:
        return None
    raw = m.group("topic").strip()
    # Normalize capitalization
    for allowed in ALLOWED_TOPICS:
        if raw.lower() == allowed.lower():
            return allowed
    # If not exact match, fallback to closest (Misc)
    return "Misc"


def remove_topic_line(article: str) -> str:
    """
    Remove the Topic: ... line from the article text for appending into topic file.
    """
    return _topic_re.sub("", article).strip() + "\n"


def parse_article_title(article: str) -> Optional[str]:
    """
    Extract the word/phrase from the article header pattern, e.g.
    "##### **ni en pedo** 🚫" -> "ni en pedo"
    Returns normalized title string or None if not found.
    """
    m = _title_re.search(article)
    if not m:
        return None
    title = m.group("title").strip()
    # remove trailing emoji tokens if present (keep punctuation inside)
    # e.g. "ni en pedo** 🚫" shouldn't be present because regex stops before emoji,
    # but trim any trailing non-word chars
    title = title.strip()
    return title


def scan_topic_files_for_titles(base_dir: Path) -> Dict[str, List[Tuple[Path, int, str]]]:
    """
    Scan topic files in base_dir for titles. Returns dict: title -> list of (path, lineno, article_snippet).
    lineno is the line number where the header is found (1-based). article_snippet is first line(s) of article.
    This reads all files matching "* - <Topic>.md" and "*.gen.md" files in base_dir.
    """
    results: Dict[str, List[Tuple[Path, int, str]]] = {}
    # collect relevant files: any file with ' - <Topic>.md' or ending with DEFAULT_GEN_SUFFIX
    candidates = []
    for p in base_dir.iterdir():
        if p.is_file():
            # accept files that end with ' - <Topic>.md' pattern or our generated suffix
            if re.search(r" - (?:{})\.md$".format("|".join([re.escape(t) for t in ALLOWED_TOPICS])), p.name):
                candidates.append(p)
            elif p.name.endswith(DEFAULT_GEN_SUFFIX):
                candidates.append(p)
    for path in candidates:
        try:
            text = read_text(path)
        except FileNotFoundError:
            continue
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            m = _title_re.search(ln)
            if m:
                title = m.group("title").strip()
                snippet = "\n".join(lines[i : min(i + 5, len(lines))])
                results.setdefault(title, []).append((path, i + 1, snippet))
    return results


def find_fuzzy_matches(title: str, existing_titles: List[str], n: int = 3, cutoff: float = 0.8) -> List[str]:
    """
    Use difflib.get_close_matches to find close titles (case-insensitive).
    """
    if not existing_titles:
        return []
    # lower-case mapping
    lower_map = {t.lower(): t for t in existing_titles}
    matches = difflib.get_close_matches(title.lower(), list(lower_map.keys()), n=n, cutoff=cutoff)
    return [lower_map[m] for m in matches]


def topic_filename_for_inbox(inbox_path: Path) -> Dict[str, Path]:
    """
    Map topic names to filenames in the inbox directory.
    Prefer existing files like 'Spanish vocab - Food.md'; otherwise create '<Topic>.gen.md'.
    """
    inbox_dir = inbox_path.parent
    out: Dict[str, Path] = {}
    for t in ALLOWED_TOPICS:
        pattern = f"* - {t}.md"
        found = list(inbox_dir.glob(pattern))
        if found:
            out[t] = found[0]
        else:
            out[t] = inbox_dir / f"{t}{DEFAULT_GEN_SUFFIX}"
    return out
