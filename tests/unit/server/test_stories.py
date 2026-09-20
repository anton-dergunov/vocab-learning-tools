"""Asking for a story: the route, the rows it writes, and the job it queues.

No model is called here. `POST /stories` writes rows and queues a job, and the job is where the
calls live — which is the whole point of the derived state: what this route produces is a story
that was asked for and not yet written.
"""

from __future__ import annotations

import pytest
from graph_records import lexeme, sense, vocabulary

from acervo.repository import graph, jobs


def words(server, count: int = 3, **overrides):
    """A vocabulary and `count` words to build a story from."""
    made = []
    server.push({"vocabularies": [vocabulary()]})
    for index in range(count):
        entry = lexeme(headword=f"palabra{index}", lemma=f"palabra{index}", status="active",
                       shortGloss=f"word {index}", **overrides)
        server.push({"lexemes": [entry], "senses": [sense(entry["id"])]})
        made.append(entry)
    return made


def ask(server, ids, **overrides):
    body = {"deviceId": "device000000001", "language": "es", "lexemeIds": ids}
    return server.post("/stories", {**body, **overrides})


# ── what can be asked for ───────────────────────────────────────────────────


def test_the_kinds_and_the_styles_arrive_together(server):
    """One round trip: a switch is meaningless without its label, and a half-loaded dialog cannot
    be rendered. `services/images.settings_view` states the same rule."""
    answer = server.get("/stories/types")
    assert answer.status_code == 200, answer.text
    body = answer.json()["data"]
    assert len(body["types"]) >= 12
    assert {"id", "label", "emoji", "styles"} <= set(body["types"][0])
    assert body["styles"], "the dialog cannot offer a style it was not given"
    assert body["minParts"] <= body["defaultParts"] <= body["maxParts"]


def test_every_style_a_type_suggests_is_one_the_dialog_offers(server):
    body = server.get("/stories/types").json()["data"]
    offered = {style["id"] for style in body["styles"]}
    for kind in body["types"]:
        assert set(kind["styles"]) <= offered, f"{kind['id']} suggests a style nobody can pick"


# ── asking for one ──────────────────────────────────────────────────────────


def test_a_story_is_written_as_rows_and_a_queued_job(server):
    made = words(server, 3)
    answer = ask(server, [one["id"] for one in made])
    assert answer.status_code == 202, answer.text
    body = answer.json()["data"]

    story = body["story"]
    assert story["language"] == "es"
    assert story["typeId"], "a kind is chosen when the story is asked for, not when it is written"
    assert story["styleId"], "and so is the look"
    # Nothing the writer decides exists yet. No parts at all is the whole of "not written".
    assert not story["title"]
    assert graph.story_parts(server.owner, story["id"]) == []

    held = graph.story_words(server.owner, story["id"])
    assert [row["sourceText"] for row in held] == ["palabra0", "palabra1", "palabra2"]
    assert all(row["forms"] == [] for row in held), "no word has been used until the story is written"
    assert body["job"]["kind"] == "story"
    assert body["job"]["subject"] == {"kind": "story", "id": story["id"]}


def test_the_kind_and_the_style_may_be_chosen(server):
    made = words(server, 2)
    answer = ask(server, [one["id"] for one in made], typeId="mystery", styleId="film-noir")
    story = answer.json()["data"]["story"]
    assert (story["typeId"], story["styleId"]) == ("mystery", "film-noir")


def test_a_kind_or_a_style_nobody_has_is_refused_by_name(server):
    made = [one["id"] for one in words(server, 2)]
    assert ask(server, made, typeId="limerick").status_code == 400
    assert ask(server, made, styleId="crayon").status_code == 400


@pytest.mark.parametrize("ids, status", [
    ([], 400),                       # a story needs at least one word
    (["not-a-record-id"], 400),
])
def test_a_list_that_is_not_words_is_refused(server, ids, status):
    words(server, 1)
    assert ask(server, ids).status_code == status


def test_the_same_word_cannot_be_asked_for_twice(server):
    made = words(server, 1)
    assert ask(server, [made[0]["id"], made[0]["id"]]).status_code == 400


def test_more_words_than_a_story_can_carry_is_refused(server):
    made = words(server, 9)
    assert ask(server, [one["id"] for one in made]).status_code == 400


def test_another_accounts_word_cannot_be_put_in_your_story(server, other):
    mine = words(server, 1)
    theirs = lexeme(headword="ajeno", lemma="ajeno", status="active")
    other.push({"vocabularies": [vocabulary()], "lexemes": [theirs]})
    assert ask(server, [mine[0]["id"], theirs["id"]]).status_code == 404


def test_every_word_in_a_story_is_in_one_language(server):
    made = words(server, 1)
    german = lexeme(language="de", headword="Haus", lemma="Haus", status="active")
    server.push({"vocabularies": [vocabulary(language="de")], "lexemes": [german]})
    assert ask(server, [made[0]["id"], german["id"]]).status_code == 400


# ── removing one ────────────────────────────────────────────────────────────


def test_deleting_a_story_tombstones_its_rows(server):
    made = words(server, 2)
    story = ask(server, [one["id"] for one in made]).json()["data"]["story"]

    answer = server.delete(f"/stories/{story['id']}")
    assert answer.status_code == 200, answer.text
    assert answer.json()["data"]["deleted"] is True
    assert all(row["deleted"] for row in graph.story_words(server.owner, story["id"]))


def test_deleting_a_story_that_is_not_yours_is_not_found(server, other):
    made = words(server, 1)
    story = ask(server, [made[0]["id"]]).json()["data"]["story"]
    answer = other.delete(f"/stories/{story['id']}")
    assert answer.status_code == 404


# ── trying again ────────────────────────────────────────────────────────────


def test_try_again_queues_another_story_job(server):
    made = words(server, 2)
    story = ask(server, [one["id"] for one in made]).json()["data"]["story"]
    jobs.finish(jobs.open_jobs(server.owner)[0]["id"], "failed",
                error="llm_unavailable", message="nothing answered")

    answer = server.post("/jobs", {"kind": "story", "subject": {"kind": "story", "id": story["id"]}})
    assert answer.status_code in (200, 202), answer.text
    assert answer.json()["data"]["kind"] == "story"


def test_try_again_on_a_story_nobody_holds_is_not_found(server):
    words(server, 1)
    answer = server.post("/jobs", {"kind": "story",
                                   "subject": {"kind": "story", "id": "storynothing123"}})
    assert answer.status_code == 404
