from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import scripts.clean_vocab as clean_vocab_script
from vocabgen.data.draft_inbox import DraftInbox
from vocabgen.vocab_processor import scan_topic_files_for_titles


pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPOSITORY_ROOT / "test-data"
INBOX_NAME = "Spanish vocab - Inbox.md"
EXPECTED_TOPIC_FILES = {
    "Spanish vocab - Actions.md",
    "Spanish vocab - Appearance.md",
    "Spanish vocab - Culture.md",
    "Spanish vocab - Emotions.md",
    "Spanish vocab - Food.md",
    "Spanish vocab - Health.md",
    "Spanish vocab - Misc.md",
    "Spanish vocab - Nature.md",
    "Spanish vocab - Slang.md",
    "Spanish vocab - Technology.md",
    "Spanish vocab - Travel.md",
}


@pytest.fixture
def corpus_copy(tmp_path: Path) -> Path:
    """Copy the tracked corpus so integration tests can safely mutate it."""
    destination = tmp_path / "vocabulary-corpus"
    shutil.copytree(CORPUS_ROOT, destination)
    return destination


def topic_files(corpus: Path) -> list[Path]:
    return sorted(path for path in corpus.glob("Spanish vocab - *.md") if path.name != INBOX_NAME)


def topic_map(corpus: Path) -> dict[str, Path]:
    prefix = "Spanish vocab - "
    return {
        path.stem.removeprefix(prefix): path
        for path in topic_files(corpus)
    }


def test_real_topic_corpus_is_structurally_valid(corpus_copy: Path) -> None:
    files = topic_files(corpus_copy)
    assert {path.name for path in files} == EXPECTED_TOPIC_FILES

    articles_by_headword = scan_topic_files_for_titles(files)
    article_count = sum(len(entries) for entries in articles_by_headword.values())

    # Keep these as lower bounds so adding vocabulary does not require updating
    # the test while accidental large-scale deletion is still detected.
    assert article_count >= 900
    assert len(articles_by_headword) >= 850


def test_real_inbox_can_be_resumed_without_mutating_the_fixture(
    corpus_copy: Path,
) -> None:
    tracked_inbox = CORPUS_ROOT / INBOX_NAME
    original_tracked_text = tracked_inbox.read_text(encoding="utf-8")
    copied_inbox_path = corpus_copy / INBOX_NAME
    copied_inbox = DraftInbox(copied_inbox_path)
    original_entry_count = len(copied_inbox)

    assert original_entry_count > 1
    copied_inbox.remove_slice(0, 1)

    assert len(copied_inbox) == original_entry_count - 1
    assert copied_inbox_path.read_text(encoding="utf-8") != original_tracked_text
    assert tracked_inbox.read_text(encoding="utf-8") == original_tracked_text


def test_cleaner_handles_duplicates_against_the_real_corpus(
    corpus_copy: Path,
) -> None:
    topics = topic_map(corpus_copy)
    existing = scan_topic_files_for_titles(list(topics.values()))
    tracked_misc = (CORPUS_ROOT / "Spanish vocab - Misc.md").read_text(encoding="utf-8")

    duplicate = """##### **añorar** 🥲
*to long for; to miss*
> **Añoro** los días en que estábamos juntos. - I **long for** the days we were together.
Topic: Emotions
"""
    new_article = """##### **fixture de integración** 🧪
*integration fixture*
> Esta es una **fixture de integración**. - This is an **integration fixture**.
Topic: Misc
"""

    appended, new_items, conflicts, _ = clean_vocab_script.write_articles_atomic(
        topics,
        [duplicate, new_article],
        existing,
    )

    assert appended == 1
    assert new_items == ["Misc: fixture de integración"]
    assert [title for title, *_ in conflicts] == ["añorar"]
    assert "fixture de integración" in topics["Misc"].read_text(encoding="utf-8")
    assert (CORPUS_ROOT / "Spanish vocab - Misc.md").read_text(encoding="utf-8") == tracked_misc
