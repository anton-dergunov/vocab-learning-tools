import pytest
from pathlib import Path
from unittest.mock import patch

from vocabgen.data.draft_inbox import DraftInbox, normalize_separator_line, split_sections


# --- Helpers ------------------------------------------------------------

@pytest.fixture
def inbox_file(tmp_path: Path) -> Path:
    """Create a temporary inbox file for tests."""
    f = tmp_path / "inbox.md"
    return f


# --- Tests for normalize_separator_line ---------------------------------

@pytest.mark.parametrize("line,expected", [
    ("---", True),
    ("-----", True),
    ("———", True),
    ("***", True),
    ("___", True),
    ("--", True),
    (" - - ", False),
    ("-- text --", False),
    ("", False),
    ("   ", False),
])
def test_normalize_separator_line(line, expected):
    assert normalize_separator_line(line) is expected


# --- Tests for split_sections -------------------------------------------

def test_split_sections_with_explicit_separators():
    text = "First\n---\nSecond\n———\nThird\n***\nFourth\n___\nFifth"
    parts = split_sections(text)
    assert parts == ["First", "Second", "Third", "Fourth", "Fifth"]


def test_split_sections_with_blank_lines_fallback():
    text = "A\n\n\nB\n\n\n\nC"
    parts = split_sections(text)
    assert parts == ["A", "B", "C"]


def test_split_sections_strips_whitespace():
    text = "  one  \n---\n   two\n---\n three  "
    parts = split_sections(text)
    assert parts == ["one", "two", "three"]


# --- Tests for DraftInbox -----------------------------------------------

def test_inbox_loads_nonexistent_file(inbox_file):
    inbox = DraftInbox(inbox_file)
    assert len(inbox) == 0
    assert inbox.entries == []
    assert inbox._raw == ""


def test_inbox_loads_existing_file(inbox_file):
    inbox_file.write_text("entry1\n---\nentry2\n---\nentry3\n")
    inbox = DraftInbox(inbox_file)
    assert len(inbox) == 3
    assert inbox.entries == ["entry1", "entry2", "entry3"]
    assert list(inbox.iter_entries()) == ["entry1", "entry2", "entry3"]


def test_get_slice_returns_expected_subset(inbox_file):
    inbox_file.write_text("a\n---\nb\n---\nc\n")
    inbox = DraftInbox(inbox_file)
    assert inbox.get_slice(0, 2) == ["a", "b"]
    assert inbox.get_slice(1, 1) == ["b"]
    assert inbox.get_slice(2, 5) == ["c"]


def test_remove_slice_removes_and_rewrites_file(inbox_file):
    inbox_file.write_text("a\n---\nb\n---\nc\n")
    inbox = DraftInbox(inbox_file)
    inbox.remove_slice(1, 1)
    # Only 'a' and 'c' should remain
    assert inbox.entries == ["a", "c"]
    text = inbox_file.read_text(encoding="utf-8")
    # File should have correct separator
    assert text.strip() == "a\n---\nc"


def test_remove_slice_all_entries_clears_file(inbox_file):
    inbox_file.write_text("a\n---\nb\n")
    inbox = DraftInbox(inbox_file)
    inbox.remove_slice(0, 2)
    assert inbox.entries == []
    assert inbox_file.read_text() == ""


def test_remove_slice_uses_atomic_write(inbox_file):
    inbox_file.write_text("a\n---\nb\n---\nc\n")
    inbox = DraftInbox(inbox_file)

    with patch("vocabgen.data.draft_inbox.atomic_write") as atomic_write:
        inbox.remove_slice(1, 1)

    atomic_write.assert_called_once_with(inbox_file, "a\n---\nc\n")


def test_remove_slice_keeps_memory_and_file_when_atomic_write_fails(inbox_file):
    original = "a\n---\nb\n---\nc\n"
    inbox_file.write_text(original)
    inbox = DraftInbox(inbox_file)

    with patch(
        "vocabgen.data.draft_inbox.atomic_write",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(OSError, match="disk full"):
            inbox.remove_slice(0, 1)

    assert inbox.entries == ["a", "b", "c"]
    assert inbox_file.read_text() == original


def test_write_preserves_final_newline(inbox_file):
    inbox_file.write_text("one\n---\ntwo\n")
    inbox = DraftInbox(inbox_file)
    inbox._write()
    content = inbox_file.read_text()
    assert content.endswith("\n")


def test_mixed_separators_are_parsed(inbox_file):
    # includes em dash, underscores, and stars
    text = "word1\n———\nword2\n***\nword3\n___\nword4"
    inbox_file.write_text(text)
    inbox = DraftInbox(inbox_file)
    assert inbox.entries == ["word1", "word2", "word3", "word4"]
