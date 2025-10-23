import tempfile
from pathlib import Path
import pytest

from vocabgen.vocab_processor import (
    split_sections,
    split_llm_response_into_articles,
    extract_topic_from_article,
    parse_article_title
)

def test_split_sections_with_separators():
    t = "first section\n---\nsecond section\n\n---\nthird"
    sections = split_sections(t)
    assert sections == ["first section", "second section", "third"]

def test_split_sections_fallback_blanklines():
    t = "a\n\n\nb\n\n\nc"
    sections = split_sections(t)
    assert sections == ["a", "b", "c"]

def test_split_llm_response_articles():
    txt = "##### **el saco** 🧥\n*coat*\nTopic: Appearance\n\n---\n\n##### **garpar** 💸\n*to pay*\nTopic: Slang"
    arts = split_llm_response_into_articles(txt)
    assert len(arts) == 2
    assert "el saco" in arts[0]

def test_extract_topic():
    art = "##### **el saco** 🧥\n*coat*\nTopic: Appearance\n"
    assert extract_topic_from_article(art) == "Appearance"

def test_parse_article_title():
    art = "##### **ni en pedo** 🚫\n*no way*\nTopic: Slang\n"
    assert parse_article_title(art) == "ni en pedo"
