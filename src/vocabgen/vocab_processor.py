from __future__ import annotations
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union
import logging
import difflib

from .fileops import atomic_write, append_to_file, read_text, backup_file
from .sections import normalize_separator_line, split_sections
from .data.article_short import ArticleShort

logger = logging.getLogger("vocabgen.vocab_processor")


def join_sections_for_batch(sections: List[str], sep: str = "\n\n---\n\n") -> str:
    """
    Join multiple sections into a single chunk for LLM consumption.
    Use `sep` to clearly indicate separation.
    """
    # Use triple-dash separator because your prompt instructs LLM to split with '---'
    return sep.join(s.strip() for s in sections if s.strip())


def clean_llm_text_block(block: str) -> str:
    """
    Clean a single LLM-generated block (simplified version):
    - remove all backtick (`) characters
    - remove separator lines (---)
    - collapse multiple blank lines into a single one
    - trim leading/trailing whitespace
    - ensure it ends with exactly one newline
    """
    if not block:
        return "\n"

    # remove all backticks
    block = block.replace("`", "")

    # collapse multiple blank lines
    block = re.sub(r"\n\s*\n+", "\n", block)

    # remove separator lines (--- etc.)
    block = re.sub(r"^\s*-{3,}\s*$", "", block, flags=re.MULTILINE)

    # collapse multiple blank lines
    block = re.sub(r"\n\s*\n+", "\n", block)

    # strip leading/trailing whitespace
    block = block.strip()

    # ensure one trailing newline
    return block + "\n"


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


def extract_topic_from_article(article: str) -> Optional[str]:
    """
    Extract the Topic: <TopicName> line from the article.
    If not found, return None.
    """
    m = _topic_re.search(article)
    if not m:
        return None
    return m.group("topic").strip()


def remove_topic_line(article: str) -> str:
    """
    Remove the Topic: ... line from the article text for appending into topic file.
    """
    return _topic_re.sub("", article).strip() + "\n"


def parse_article_title(article: str) -> Optional[str]:
    """
    Parse an article and return its word/phrase, e.g.
    "##### **ni en pedo** 🚫" -> "ni en pedo"
    Returns None if the complete article is malformed.
    """
    try:
        return ArticleShort.parse_from_markdown(remove_topic_line(article)).headword
    except ValueError:
        return None


def _split_topic_file_articles(text: str) -> List[Tuple[int, str]]:
    """Return ``(line_number, article_markdown)`` blocks from a topic file."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith("#")]

    if not starts:
        if text.strip():
            raise ValueError("no Markdown article headings found")
        return []

    if any(line.strip() for line in lines[:starts[0]]):
        first_content_line = next(
            index + 1 for index, line in enumerate(lines[:starts[0]]) if line.strip()
        )
        raise ValueError(f"unexpected content before the first article at line {first_content_line}")

    blocks: List[Tuple[int, str]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        blocks.append((start + 1, "\n".join(lines[start:end]).strip()))
    return blocks


def scan_topic_files_for_titles(
    files: List[Union[str, Path]],
) -> Dict[str, List[Tuple[Path, int, str]]]:
    """
    Parse topic files and index articles by headword.

    Returns ``headword -> [(path, line_number, canonical_markdown)]``. A malformed
    existing article is reported with its file and starting line rather than being
    silently omitted from duplicate detection.
    """
    results: Dict[str, List[Tuple[Path, int, str]]] = {}

    for file in files:
        path = Path(file)
        try:
            text = read_text(path)
        except FileNotFoundError:
            continue

        try:
            blocks = _split_topic_file_articles(text)
        except ValueError as exc:
            raise ValueError(f"Failed to parse topic file {path}: {exc}") from exc

        for line_number, markdown in blocks:
            try:
                article = ArticleShort.parse_from_markdown(markdown)
            except ValueError as exc:
                raise ValueError(
                    f"Failed to parse article in {path} at line {line_number}: {exc}"
                ) from exc
            results.setdefault(article.headword, []).append(
                (path, line_number, article.to_markdown().rstrip())
            )
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
