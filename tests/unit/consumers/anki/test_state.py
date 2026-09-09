"""Anki's review state as Acervo records it.

The pure half: how a note's cards collapse into one row, what the graph is told, and what is left
out. The robot's own read side is covered by `test_robot.py`.
"""

from __future__ import annotations

import re

import pytest

from acervo.consumers.anki.state import SYSTEM, collapse, held_by_lexeme, study_states

INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def card(**overrides):
    return {
        "anki_card_id": 91, "reps": 4, "lapses": 1, "stability": 12.5, "difficulty": 5.2,
        "retrievability": 0.9, "last_review": "2026-09-01T00:00:00.000Z", **overrides,
    }


def note(**overrides):
    return {
        "note_id": "note00000000001", "lexeme_id": "lexeme000000001", "anki_note_id": 17,
        "card_ids": [91], "cards": [card()], **overrides,
    }


def test_a_note_with_one_card_carries_that_cards_numbers():
    assert collapse([card()]) == {
        "reps": 4, "lapses": 1, "stability": 12.5, "difficulty": 5.2,
        "retrievability": 0.9, "lastReview": "2026-09-01T00:00:00.000Z",
    }


def test_several_cards_collapse_by_counting_up_and_taking_the_weakest():
    """Counts add up because every review was a review of this word. The memory state comes from the
    least stable card, because that is the one coming up next and the one that says how well the word
    is actually known."""
    numbers = collapse(
        [
            card(stability=12.5, difficulty=5.0, retrievability=0.91, reps=4, lapses=1),
            card(stability=3.0, difficulty=7.0, retrievability=0.55, reps=2, lapses=0,
                 last_review="2026-09-05T00:00:00.000Z"),
        ]
    )
    assert numbers["reps"] == 6
    assert numbers["lapses"] == 1
    assert (numbers["stability"], numbers["difficulty"]) == (3.0, 7.0)
    assert numbers["retrievability"] == 0.55
    assert numbers["lastReview"] == "2026-09-05T00:00:00.000Z"


def test_a_note_never_reviewed_collapses_to_zeroes_rather_than_to_nothing():
    assert collapse([])["reps"] == 0
    assert collapse([])["lastReview"] is None


@pytest.mark.parametrize("value", [None, "", 1.4, -0.2])
def test_retrievability_is_held_inside_the_range_the_column_allows(value):
    """The column is bounded to (0, 1); an absent value must not become something out of range."""
    assert 0.0 <= collapse([card(retrievability=value)])["retrievability"] <= 1.0


def test_a_first_write_mints_an_id_and_claims_revision_zero():
    rows, skipped = study_states(
        {"notes": [note()]}, {}, {"lexeme000000001"}, device_id="ankiworker0001"
    )
    assert skipped == []
    (row,) = rows
    assert re.match(r"^[a-z0-9]{15}$", row["id"])
    assert row["revision"] == 0
    assert row["system"] == SYSTEM
    assert row["lexemeId"] == "lexeme000000001"
    assert row["noteId"] == 17
    assert row["cardIds"] == [91]
    assert row["editedBy"] == "ankiworker0001"
    assert INSTANT.match(row["syncedAt"])
    assert INSTANT.match(row["editedAt"])
    assert INSTANT.match(row["createdAt"])


def test_the_wire_timestamps_are_the_shape_the_graph_route_accepts():
    """`.isoformat()` gives `+00:00` and six fractional digits, and the route refuses both."""
    rows, _ = study_states(
        {"notes": [note()]}, {}, {"lexeme000000001"}, device_id="ankiworker0001"
    )
    assert INSTANT.match(rows[0]["lastReview"])


def test_a_second_write_updates_the_row_it_already_has():
    """A record the graph holds must state the revision it was edited from, and keep its own id."""
    held = {
        "lexeme000000001": {
            "id": "studyaaaaaaaaaa", "lexemeId": "lexeme000000001", "system": SYSTEM,
            "revision": 42, "createdAt": "2026-08-01T00:00:00.000Z",
        }
    }
    rows, _ = study_states(
        {"notes": [note()]}, held, {"lexeme000000001"}, device_id="ankiworker0001"
    )
    assert rows[0]["id"] == "studyaaaaaaaaaa"
    assert rows[0]["revision"] == 42
    assert rows[0]["createdAt"] == "2026-08-01T00:00:00.000Z"


def test_a_note_whose_word_is_gone_is_skipped_rather_than_refused():
    """An ordinary state, not a mismatch: a word removed in Acervo keeps its card in the collection
    until someone deletes it there, and one such note must not stop the rest from being written."""
    rows, skipped = study_states(
        {"notes": [note(), note(note_id="note00000000002", lexeme_id="goneaway0000001")]},
        {},
        {"lexeme000000001"},
        device_id="ankiworker0001",
    )
    assert [row["lexemeId"] for row in rows] == ["lexeme000000001"]
    assert skipped == ["note00000000002"]


def test_only_this_systems_rows_are_treated_as_ours():
    """Keyed by system so a second learning tool never collides with Anki."""
    changes = {
        "studyStates": [
            {"id": "aaaaaaaaaaaaaaa", "lexemeId": "lexeme000000001", "system": "anki", "revision": 1},
            {"id": "bbbbbbbbbbbbbbb", "lexemeId": "lexeme000000001", "system": "mochi", "revision": 1},
        ]
    }
    assert list(held_by_lexeme(changes)) == ["lexeme000000001"]
    assert held_by_lexeme(changes)["lexeme000000001"]["id"] == "aaaaaaaaaaaaaaa"


def test_what_anki_exports_and_acervo_does_not_store():
    """`queue`, `suspended` and `flag` have no columns, and giving them some means rebuilding the
    database for information nothing reads."""
    rows, _ = study_states(
        {"notes": [note(cards=[card(queue=-1, suspended=True, flag=3)])]},
        {},
        {"lexeme000000001"},
        device_id="ankiworker0001",
    )
    assert not {"queue", "suspended", "flag"} & set(rows[0])
