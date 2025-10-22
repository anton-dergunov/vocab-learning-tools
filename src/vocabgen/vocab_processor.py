from __future__ import annotations
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import logging

from .fileops import atomic_write, append_to_file, read_text, backup_file

logger = logging.getLogger("vocabgen.vocab_processor")

# Allowed topics (as in your prompt)
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


def append_article_to_topic(base_dir: Path, topic: str, article: str) -> Path:
    """
    Append article text to a file named by topic in base_dir.
    Filenames: "<base_filename> - <Topic>.md" -- but we will just use "<topic>.md"
    (As you have files like 'Spanish vocab - Food.md', the script will append to file named
     after the topic in the same directory; see higher-level code for comprehension.)
    """
    # We'll let caller pass the exact file path; for convenience, choose topicfilename slug:
    filename = f"{topic}.md"
    path = base_dir / filename
    append_to_file(path, article + "\n")
    return path
