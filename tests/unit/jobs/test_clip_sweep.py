"""The unattended half of clips: which words a sweep picks, and which it refuses to pick twice.

The sweep's value is entirely in its arithmetic — `clipsSearchedAt IS NULL`, and what that does and
does not mean — so that is what is tested. It searches nothing itself: every word is one call to the
service's own route, which `tests/unit/server/test_clips.py` covers against a fake corpus.
"""

from __future__ import annotations

import pytest

from acervo.client import AcervoError
from acervo.jobs.clips.sweep import plan, sweep

CORPUS = {"configured": True, "reachable": True, "ready": True, "indexedLanguages": ["es"]}


def word(word_id: str, **overrides):
    return {
        "id": word_id, "headword": word_id, "language": "es", "status": "inbox",
        "clipsSearchedAt": None, "createdAt": "2026-01-01T00:00:00.000Z", "deleted": False,
        **overrides,
    }


def sense(sense_id: str, lexeme_id: str, **overrides):
    return {"id": sense_id, "lexemeId": lexeme_id, "deleted": False, **overrides}


def graph(**collections):
    empty = {
        "vocabularies": [], "topics": [], "lexemes": [], "senses": [], "attestations": [],
        "examples": [], "imagePrompts": [], "studyStates": [],
    }
    return {**empty, **collections}


class FakeClient:
    """The two routes, recorded. Not `AcervoClient`, because what is under test is the arithmetic."""

    def __init__(self, changes, *, settings=None, refuse=None, answers=None):
        self.changes = changes
        self._settings = settings or {"searchEnabled": True, "corpus": CORPUS}
        self.refuse = refuse or {}
        self.answers = answers or {}
        self.searched: list[str] = []

    def clip_settings(self):
        return self._settings

    def pull_graph(self, since: int = 0):
        return {"changes": self.changes}

    def find_clips(self, lexeme_id, *, device_id, timeout=300.0):
        self.searched.append(lexeme_id)
        if lexeme_id in self.refuse:
            raise AcervoError("refused", self.refuse[lexeme_id], 503)
        return self.answers.get(lexeme_id, {
            "lexemeId": lexeme_id, "searched": True, "skipped": None,
            "examples": [{"id": "x"}], "dropped": 0, "usage": None,
        })


def quiet(_message: str) -> None:
    return None


# ── what the query returns ──────────────────────────────────────────────────


def test_a_word_never_consulted_is_the_whole_of_the_backlog():
    changes = graph(
        lexemes=[word("l1"), word("l2", clipsSearchedAt="2026-09-01T00:00:00.000Z")],
        senses=[sense("s1", "l1"), sense("s2", "l2")],
    )
    assert [entry["id"] for entry in plan(changes)] == ["l1"]


def test_a_word_searched_and_found_empty_is_not_in_it():
    """The whole point of the field being a date rather than a flag: consulted-and-found-nothing is
    the common answer, and re-asking would spend a model call to re-learn that the corpus is thin."""
    changes = graph(
        lexemes=[word("l1", clipsSearchedAt="2026-09-01T00:00:00.000Z")],
        senses=[sense("s1", "l1")],
        examples=[],        # searched, and nothing was good enough
    )
    assert plan(changes) == []


def test_a_word_with_no_senses_has_nothing_to_illustrate():
    assert plan(graph(lexemes=[word("l1")], senses=[])) == []


def test_a_word_put_away_is_not_worth_a_model_call():
    changes = graph(lexemes=[word("l1", status="retired")], senses=[sense("s1", "l1")])
    assert plan(changes) == []


def test_a_tombstoned_word_is_not_in_it():
    changes = graph(lexemes=[word("l1", deleted=True)], senses=[sense("s1", "l1")])
    assert plan(changes) == []


def test_the_newest_word_comes_first():
    """A word added today is the one being learned today, and an interrupted sweep should have spent
    its time on that rather than on the oldest thing in the store."""
    changes = graph(
        lexemes=[word("old", createdAt="2026-01-01T00:00:00.000Z"),
                 word("new", createdAt="2026-09-01T00:00:00.000Z")],
        senses=[sense("s1", "old"), sense("s2", "new")],
    )
    assert [entry["id"] for entry in plan(changes)] == ["new", "old"]


def test_one_language_can_be_asked_for():
    changes = graph(
        lexemes=[word("es1"), word("en1", language="en")],
        senses=[sense("s1", "es1"), sense("s2", "en1")],
    )
    assert [entry["id"] for entry in plan(changes, language="es")] == ["es1"]


# ── what the sweep does with it ─────────────────────────────────────────────


def one_word():
    return graph(lexemes=[word("l1")], senses=[sense("s1", "l1")])


def test_it_searches_each_word_once():
    client = FakeClient(one_word())
    result = sweep(client, report=quiet)
    assert client.searched == ["l1"]
    assert (result.searched, result.found, result.failed) == (1, 1, 0)


def test_a_word_the_model_declined_counts_as_searched_and_empty():
    """Not a failure. The word is marked by the route, so this sweep will not see it again."""
    client = FakeClient(one_word(), answers={"l1": {
        "lexemeId": "l1", "searched": True, "skipped": None, "examples": [], "dropped": 0,
        "usage": None,
    }})
    result = sweep(client, report=quiet)
    assert (result.searched, result.found, result.empty) == (1, 0, 1)


def test_a_word_the_route_skipped_is_not_counted_as_searched():
    """An unindexed language is skipped without being marked, so it stays in the backlog."""
    client = FakeClient(one_word(), answers={"l1": {
        "lexemeId": "l1", "searched": False, "skipped": "language_not_indexed", "examples": [],
        "dropped": 0, "usage": None,
    }})
    result = sweep(client, report=quiet)
    assert (result.searched, result.skipped) == (0, 1)


def test_a_language_the_corpus_does_not_index_costs_no_round_trip():
    """Filtering on the corpus's own reading is one request instead of one refusal per word."""
    changes = graph(lexemes=[word("fr1", language="fr")], senses=[sense("s1", "fr1")])
    client = FakeClient(changes)
    result = sweep(client, report=quiet)
    assert client.searched == []
    assert result.skipped == 1


def test_dropped_ids_are_carried_up_so_a_prompt_bug_is_visible():
    client = FakeClient(one_word(), answers={"l1": {
        "lexemeId": "l1", "searched": True, "skipped": None, "examples": [{"id": "x"}],
        "dropped": 2, "usage": None,
    }})
    assert sweep(client, report=quiet).dropped == 2


def test_the_limit_counts_words_because_a_word_is_one_unit():
    changes = graph(
        lexemes=[word(f"l{index}", createdAt=f"2026-01-0{index}T00:00:00.000Z") for index in (1, 2, 3)],
        senses=[sense(f"s{index}", f"l{index}") for index in (1, 2, 3)],
    )
    client = FakeClient(changes)
    assert sweep(client, limit=2, report=quiet).searched == 2
    assert len(client.searched) == 2


def test_a_failure_on_one_word_does_not_stop_the_rest():
    changes = graph(
        lexemes=[word("l1", createdAt="2026-01-02T00:00:00.000Z"),
                 word("l2", createdAt="2026-01-01T00:00:00.000Z")],
        senses=[sense("s1", "l1"), sense("s2", "l2")],
    )
    client = FakeClient(changes, refuse={"l1": "llm_failed"})
    result = sweep(client, report=quiet)
    assert client.searched == ["l1", "l2"]
    assert (result.failed, result.searched) == (1, 1)
    assert result.problems == ["l1: llm_failed"]


@pytest.mark.parametrize("settings, why", [
    ({"searchEnabled": False, "corpus": CORPUS}, "switched off"),
    ({"searchEnabled": True, "corpus": {"configured": False}}, "no corpus"),
    ({"searchEnabled": True, "corpus": {**CORPUS, "ready": False}}, "no index yet"),
    ({"searchEnabled": True, "corpus": {**CORPUS, "reachable": False}}, "unreachable"),
])
def test_it_spends_nothing_when_there_is_nothing_to_spend_it_on(settings, why):
    client = FakeClient(one_word(), settings=settings)
    result = sweep(client, report=quiet)
    assert client.searched == [], why
    assert result.searched == 0


def test_a_transient_refusal_is_waited_out_and_a_terminal_one_is_not(monkeypatch):
    """A provider that is busy says nothing about the request; a rejected configuration is a mistake
    to fix, and waiting on one would hide it and spend the night doing nothing."""
    import acervo.jobs.clips.sweep as module

    slept: list[float] = []
    monkeypatch.setattr(module.time, "sleep", slept.append)

    busy = FakeClient(one_word(), refuse={"l1": "corpus_unavailable"})
    sweep(busy, report=quiet)
    assert slept == [30.0, 60.0, 120.0]

    slept.clear()
    broken = FakeClient(one_word(), refuse={"l1": "llm_authentication"})
    sweep(broken, report=quiet)
    assert slept == []
