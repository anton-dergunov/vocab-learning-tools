import tempfile
from pathlib import Path
import pytest

from vocabgen.vocab_processor import (
    split_sections,
    clean_llm_text_block,
    split_llm_response_into_articles,
    extract_topic_from_article,
    parse_article_title,
    scan_topic_files_for_titles,
)


def test_clean_preserves_article_without_fences():
    inp = """##### **deprimido** 😔
*depressed*
> Estuve **deprimido** “AL LLEGAR A ARGENTINA”. - I was **depressed** “upon arriving in Argentina”.
Topic: Emotions
"""
    out = clean_llm_text_block(inp)
    assert out.endswith("\n")
    assert "deprimido" in out
    # no extra blank lines
    assert "\n\n\n" not in out


def test_unwrap_triple_backticks_and_trim():
    inp = "```\n##### **el acertijo** 🧠\n*riddle*\nTopic: Culture\n```\n"
    out = clean_llm_text_block(inp)
    assert out.startswith("##### **el acertijo**")
    assert out.strip().endswith("Topic: Culture")
    assert out.count("\n") >= 1


def test_remove_single_backtick_lines_and_edge_backticks():
    inp = "`\n##### **x**\n*one*\n`\n"
    out = clean_llm_text_block(inp)
    assert out.startswith("##### **x**")
    assert "`" not in out  # stray backticks removed


def test_remove_internal_separator_lines():
    inp = """##### **a** 🔤
*word*
Topic: Misc

---

##### **b** 🔤
*word*
Topic: Misc
"""
    # split on separators first:
    parts = split_llm_response_into_articles(inp)
    # Should yield 2 parts
    assert len(parts) == 2
    assert parts[0].startswith("##### **a**")
    assert parts[1].startswith("##### **b**")


def test_collapse_many_newlines():
    inp = "\n\n\n\n##### **foo**\n*bar*\n\n\n\nTopic: Misc\n\n\n"
    out = clean_llm_text_block(inp)
    # Only single trailing newline, and internal paragraph separated by at most one blank line
    assert out.endswith("\n")
    assert "\n\n\n" not in out


def test_split_sections_with_separators():
    t = "first section\n---\nsecond section\n\n---\nthird"
    sections = split_sections(t)
    assert sections == ["first section", "second section", "third"]


def test_split_llm_response_into_articles_mixed():
    inp = (
        "##### **deprimido** 😔\n*depressed*\n> Estuve **deprimido**\nTopic: Emotions\n\n---\n\n"
        "##### **el acertijo** 🧠\n*riddle*\nTopic: Culture\n\n---\n\n"
        "##### **escalofriante** 🥶\n*chilling*\nTopic: Emotions\n"
    )
    parts = split_llm_response_into_articles(inp)
    assert len(parts) == 3
    assert "deprimido" in parts[0]
    assert "acertijo" in parts[1]
    assert "escalofriante" in parts[2]


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


def test_parse_article_title_rejects_malformed_article_body():
    art = "##### **ni en pedo** 🚫\nno way\nTopic: Slang\n"
    assert parse_article_title(art) is None


def test_scan_topic_files_parses_complete_articles(tmp_path):
    topic_file = tmp_path / "Spanish vocab - Nature.md"
    topic_file.write_text(
        """##### **la luna** 🌕
*moon*
> La **luna** brilla. - The **moon** shines.

##### **el sol** ☀️
*sun*
> El **sol** calienta. - The **sun** warms us.
"""
    )

    titles = scan_topic_files_for_titles([topic_file])

    assert set(titles) == {"la luna", "el sol"}
    assert titles["la luna"][0][0:2] == (topic_file, 1)
    assert titles["el sol"][0][0:2] == (topic_file, 5)
    assert titles["la luna"][0][2].startswith("##### **la luna**")


def test_scan_topic_files_reports_malformed_article_with_context(tmp_path):
    topic_file = tmp_path / "Spanish vocab - Nature.md"
    topic_file.write_text("##### **la luna** 🌕\nmoon\n")

    with pytest.raises(ValueError, match=r"Nature\.md at line 1.*Invalid translation"):
        scan_topic_files_for_titles([topic_file])


def test_scan_topic_files_rejects_content_before_first_article(tmp_path):
    topic_file = tmp_path / "Spanish vocab - Nature.md"
    topic_file.write_text("orphaned note\n\n##### **la luna** 🌕\n*moon*\n")

    with pytest.raises(ValueError, match="unexpected content before the first article"):
        scan_topic_files_for_titles([topic_file])
