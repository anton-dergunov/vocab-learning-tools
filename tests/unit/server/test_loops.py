"""The two collections a loop is, and what the graph refuses about them.

A loop is the first replicated record that hangs off no word: it is an owner-level artefact that
*references* lexemes. So the things worth pinning here are the ones that fall out of that — where it
sits in the merge order, what a half-rendered one looks like, and which deletions reach it.
"""

from __future__ import annotations

import pytest
from graph_records import lexeme, loop, loop_item, sense, vocabulary

from acervo.db import tables
from acervo.domain.projection import COLLECTIONS, WORD_COLLECTIONS


def words(server):
    """One vocabulary and one word, which is the least a loop item can refer to."""
    word = lexeme()
    server.push({"vocabularies": [vocabulary()], "lexemes": [word], "senses": [sense(word["id"])]})
    return word


def stored(server, key):
    return server.pull().json()["data"]["changes"][key]


# ── where they sit ──────────────────────────────────────────────────────────


def test_loops_come_last_so_both_their_relations_resolve_before_them():
    """The merge order is the collection order, and a loop item names a loop *and* a lexeme."""
    keys = [collection.key for collection in COLLECTIONS]
    assert keys[-2:] == ["loops", "loopItems"]
    assert keys.index("lexemes") < keys.index("loopItems")
    assert keys.index("loops") < keys.index("loopItems")
    assert tables.REPLICATED[-2:] == ("loops", "loop_items")


def test_the_word_reset_takes_loops_and_leaves_the_languages_alone():
    """Not coded anywhere: it falls out of loops sitting last, which is why they were put there."""
    keys = [collection.key for collection in WORD_COLLECTIONS]
    assert "loops" in keys and "loopItems" in keys
    assert "vocabularies" not in keys and "topics" not in keys
    # Children first, so a tombstone never outlives what it hangs off.
    assert keys.index("loopItems") < keys.index("loops")


# ── a loop, written and read back ───────────────────────────────────────────


def test_a_loop_and_its_items_land_in_one_batch_and_come_back_projected(server):
    word = words(server)
    track = loop()
    item = loop_item(track["id"], word["id"])

    answer = server.push({"loops": [track], "loopItems": [item]})
    assert answer.status_code == 200, answer.text

    written = stored(server, "loops")[0]
    assert written["styleId"] == "sunlit-acoustic"
    assert written["seed"] == 104740
    assert written["position"] == 0
    assert written["durationSeconds"] == pytest.approx(124.5)
    row = stored(server, "loopItems")[0]
    assert row["loopId"] == track["id"] and row["lexemeId"] == word["id"]
    assert row["sourceText"] == "picar" and row["targetText"] == "to sting"
    assert row["targetRevealSeconds"] == pytest.approx(17.65)


def test_position_is_stored_as_loop_order_and_projected_back_as_position(server):
    """The wire says `position`, storage says `loop_order` beside `vocab_order` and `sense_order`."""
    words(server)
    server.push({"loops": [loop(position=7)]})
    assert stored(server, "loops")[0]["position"] == 7


def test_an_unrendered_loop_is_one_with_no_reference_and_nothing_else_says_so(server):
    """There is no status column: four facts already say all of it, and a fifth would be a thing to
    keep in step."""
    words(server)
    server.push({"loops": [loop(audioRef=None, audioMime=None, durationSeconds=0)]})
    written = stored(server, "loops")[0]
    assert written["audioRef"] is None
    # Hidden with it, rather than projected as an empty string and a zero that read like facts.
    assert written["audioMime"] is None
    assert written["durationSeconds"] is None


# ── what is refused ─────────────────────────────────────────────────────────


def test_a_reference_without_a_type_is_refused_and_so_is_a_type_without_one(server):
    words(server)
    for overrides in ({"audioMime": None}, {"audioRef": None}):
        answer = server.push({"loops": [loop(**overrides)]})
        assert answer.status_code == 400
        assert "together" in answer.text


def test_a_duration_on_a_loop_that_was_never_rendered_is_refused(server):
    words(server)
    answer = server.push({"loops": [loop(audioRef=None, audioMime=None, durationSeconds=90.0)]})
    assert answer.status_code == 400
    assert "has not been rendered" in answer.text


@pytest.mark.parametrize("overrides", [
    {"sourceRevealSeconds": 4.0, "startSeconds": 9.0},
    {"targetRevealSeconds": 1.0},
    {"endSeconds": 2.0},
])
def test_times_that_run_backwards_are_refused(server, overrides):
    """What a retrieval display turns on: the answer must not be on screen before the recall gap."""
    word = words(server)
    track = loop()
    server.push({"loops": [track]})
    answer = server.push({"loopItems": [loop_item(track["id"], word["id"], **overrides)]})
    assert answer.status_code == 400
    assert "backwards" in answer.text


def test_a_loop_item_naming_another_owners_word_is_refused(server, other):
    word = words(server)
    track = loop()
    server.push({"loops": [track]})

    other.push({"vocabularies": [vocabulary()]})
    stranger = lexeme()
    other.push({"lexemes": [stranger]})

    answer = server.push({"loopItems": [loop_item(track["id"], stranger["id"])]})
    assert answer.status_code in (400, 409)


def test_a_loop_item_naming_no_loop_is_refused(server):
    word = words(server)
    answer = server.push({"loopItems": [loop_item("loopmissing001", word["id"])]})
    assert answer.status_code == 400
    assert "Loop does not exist" in answer.text


# ── the fields a loop is made from ──────────────────────────────────────────


def test_a_lexeme_carries_the_one_term_a_loop_speaks_and_how_it_sounds(server):
    server.push({"vocabularies": [vocabulary()]})
    word = lexeme(
        shortGloss="disgust, revulsion",
        primaryGloss="disgust",
        emotion="repulsed, recoiling slightly",
    )
    assert server.push({"lexemes": [word]}).status_code == 200
    written = stored(server, "lexemes")[0]
    # Both, and separately: `shortGloss` may carry several meanings and a loop must choose one.
    assert written["shortGloss"] == "disgust, revulsion"
    assert written["primaryGloss"] == "disgust"
    assert written["emotion"] == "repulsed, recoiling slightly"


def test_a_word_without_a_loop_line_is_an_ordinary_word(server):
    """Both fields are optional. A word the writer left without one is simply not eligible for a
    loop, and nothing backfills it."""
    server.push({"vocabularies": [vocabulary()]})
    assert server.push({"lexemes": [lexeme()]}).status_code == 200
    written = stored(server, "lexemes")[0]
    assert written["primaryGloss"] is None and written["emotion"] is None


# ── the reset reaches them ──────────────────────────────────────────────────


def test_the_reset_tombstones_loops_along_with_the_words_they_name(server):
    """A loop whose every caption names a deleted word is a track nothing describes."""
    from graph_records import DEVICE

    from acervo.domain import SCHEMA_VERSION

    word = words(server)
    track = loop()
    server.push({"loops": [track]})
    server.push({"loopItems": [loop_item(track["id"], word["id"])]})

    answer = server.post(
        "/graph/reset",
        {"schemaVersion": SCHEMA_VERSION, "deviceId": DEVICE, "confirm": "delete-all-words"},
    )
    assert answer.status_code == 200

    remaining = server.pull().json()["data"]["changes"]
    assert [record["deleted"] for record in remaining["vocabularies"]] == [False]
    for key in ("lexemes", "loops", "loopItems"):
        assert all(record["deleted"] for record in remaining[key]), key
