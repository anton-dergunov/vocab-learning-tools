"""The unattended half: what a sweep decides to do, and what it refuses to do twice.

The sweep's value is entirely in its arithmetic — which senses it picks, which it leaves alone, and
when it stops — so that is what is tested. It draws nothing itself: every picture is one call to the
service's own route, which `tests/unit/server/test_images.py` covers against the real encoder.
"""

from __future__ import annotations

from acervo.client import AcervoError
from acervo.jobs.images.sweep import plan, sweep


def word(word_id: str, **overrides):
    return {
        "id": word_id, "headword": word_id, "language": "es", "status": "inbox",
        "createdAt": "2026-01-01T00:00:00.000Z", "deleted": False, **overrides,
    }


def sense(sense_id: str, lexeme_id: str, **overrides):
    return {"id": sense_id, "lexemeId": lexeme_id, "deleted": False, **overrides}


def prompt(prompt_id: str, lexeme_id: str, sense_id: str, **overrides):
    return {
        "id": prompt_id, "lexemeId": lexeme_id, "senseId": sense_id, "prompt": "a nose",
        "styleId": "oil-painting", "imageRef": None, "imageModelId": None, "attempts": 0,
        "failureReason": None, "suppressed": False, "deleted": False, **overrides,
    }


def graph(**collections):
    empty = {
        "vocabularies": [], "topics": [], "lexemes": [], "senses": [], "attestations": [],
        "examples": [], "imagePrompts": [], "studyStates": [],
    }
    return {**empty, **collections}


class FakeClient:
    """The routes, recorded. Not `AcervoClient`, because what is under test is the arithmetic."""

    def __init__(self, changes, *, settings=None, refuse=None, draws=True):
        self.changes = changes
        self._settings = settings or {"sweepEnabled": True, "available": True, "maxAttempts": 4}
        self.refuse = refuse or {}
        self.draws = draws
        self.briefed: list[str] = []
        self.rendered: list[str] = []

    def image_settings(self):
        return self._settings

    def pull_graph(self, since: int = 0):
        return {"changes": self.changes}

    def brief_lexeme(self, lexeme_id, *, device_id, timeout=180.0):
        self.briefed.append(lexeme_id)
        if lexeme_id in self.refuse:
            raise AcervoError("refused", self.refuse[lexeme_id], 503)
        return {"lexemeId": lexeme_id, "imagePrompts": [
            row for row in self.changes["imagePrompts"] if row["lexemeId"] == lexeme_id
        ]}

    def render_image(self, prompt_id, *, device_id, timeout=300.0):
        self.rendered.append(prompt_id)
        if prompt_id in self.refuse:
            raise AcervoError("refused", self.refuse[prompt_id], 503)
        if not self.draws:
            return {"id": prompt_id, "imageRef": None, "failureReason": "the provider declined"}
        return {
            "id": prompt_id, "imageRef": f"images/x/{prompt_id}.webp", "imageModelId": "painter",
            "styleId": "oil-painting",
        }


# ── what the query returns ──────────────────────────────────────────────────


def test_a_sense_with_no_prompt_row_needs_describing():
    found = plan(graph(lexemes=[word("w1")], senses=[sense("s1", "w1")]))
    assert [(entry["lexemeId"], entry["unbriefed"]) for entry in found] == [("w1", 1)]


def test_a_sense_that_already_has_a_picture_is_not_work():
    found = plan(graph(
        lexemes=[word("w1")], senses=[sense("s1", "w1")],
        imagePrompts=[prompt("p1", "w1", "s1", imageRef="images/w1/p1.webp", imageModelId="painter")],
    ))
    assert found == []


def test_a_sense_the_owner_ruled_on_is_not_work():
    """Which is the whole reason `suppressed` is a column and not a tombstone: a tombstoned row is
    invisible here, so the sense would be re-briefed and its id re-minted."""
    found = plan(graph(
        lexemes=[word("w1")], senses=[sense("s1", "w1")],
        imagePrompts=[prompt("p1", "w1", "s1", suppressed=True)],
    ))
    assert found == []


def test_a_word_put_away_is_not_worth_a_picture():
    found = plan(graph(lexemes=[word("w1", status="archived")], senses=[sense("s1", "w1")]))
    assert found == []


def test_one_language_can_be_swept_alone():
    found = plan(
        graph(
            lexemes=[word("w1"), word("w2", language="en")],
            senses=[sense("s1", "w1"), sense("s2", "w2")],
        ),
        language="en",
    )
    assert [entry["lexemeId"] for entry in found] == ["w2"]


def test_the_newest_word_is_swept_first():
    """A word added today is the one being learned today, so an interrupted run should have spent
    its minutes there rather than on the oldest thing in the store."""
    found = plan(graph(
        lexemes=[word("old", createdAt="2026-01-01T00:00:00.000Z"),
                 word("new", createdAt="2026-06-01T00:00:00.000Z")],
        senses=[sense("s1", "old"), sense("s2", "new")],
    ))
    assert [entry["lexemeId"] for entry in found] == ["new", "old"]


# ── what the sweep does with it ─────────────────────────────────────────────


def test_it_describes_then_draws():
    # One sense has a brief and one has no row at all, so the word needs describing first — and the
    # description covers every sense at once, which is why briefing is per word and drawing is not.
    client = FakeClient(graph(
        lexemes=[word("w1")], senses=[sense("s1", "w1"), sense("s2", "w1")],
        imagePrompts=[prompt("p1", "w1", "s1")],
    ))
    result = sweep(client, report=lambda line: None)
    assert client.briefed == ["w1"]
    assert client.rendered == ["p1"]
    assert result.briefed == 1 and result.drawn == 1


def test_it_draws_without_describing_when_every_sense_has_a_brief():
    client = FakeClient(graph(
        lexemes=[word("w1")], senses=[sense("s1", "w1")],
        imagePrompts=[prompt("p1", "w1", "s1")],
    ))
    result = sweep(client, report=lambda line: None)
    assert client.briefed == []
    assert client.rendered == ["p1"]
    assert result.drawn == 1


def test_a_sense_past_the_threshold_is_left_alone():
    """`attempts` exists for exactly this: without it a permanently blocked sense was re-planned
    every night forever, because "no picture" was the only thing the row could say."""
    client = FakeClient(graph(
        lexemes=[word("w1")], senses=[sense("s1", "w1")],
        imagePrompts=[prompt("p1", "w1", "s1", attempts=4, failureReason="declined")],
    ))
    result = sweep(client, report=lambda line: None)
    assert client.rendered == []
    assert result.skipped == 1 and result.drawn == 0


def test_a_provider_declining_is_counted_rather_than_raised():
    client = FakeClient(
        graph(lexemes=[word("w1")], senses=[sense("s1", "w1")],
              imagePrompts=[prompt("p1", "w1", "s1")]),
        draws=False,
    )
    result = sweep(client, report=lambda line: None)
    assert result.refused == 1 and result.drawn == 0 and result.problems == []


def test_the_limit_counts_pictures_and_stops_the_run():
    client = FakeClient(graph(
        lexemes=[word("w1")],
        senses=[sense("s1", "w1"), sense("s2", "w1"), sense("s3", "w1")],
        imagePrompts=[prompt("p1", "w1", "s1"), prompt("p2", "w1", "s2"), prompt("p3", "w1", "s3")],
    ))
    result = sweep(client, limit=2, report=lambda line: None)
    assert len(client.rendered) == 2 and result.drawn == 2


def test_switching_unattended_drawing_off_spends_nothing():
    """The master switch gates *this*, and deliberately not the buttons: you pressed those."""
    client = FakeClient(
        graph(lexemes=[word("w1")], senses=[sense("s1", "w1")]),
        settings={"sweepEnabled": False, "available": True, "maxAttempts": 4},
    )
    result = sweep(client, report=lambda line: None)
    assert client.briefed == [] and client.rendered == []
    assert result.drawn == 0


def test_a_server_with_no_picture_provider_stops_before_asking():
    client = FakeClient(
        graph(lexemes=[word("w1")], senses=[sense("s1", "w1")]),
        settings={"sweepEnabled": True, "available": False, "maxAttempts": 4},
    )
    sweep(client, report=lambda line: None)
    assert client.briefed == [] and client.rendered == []


def test_a_word_that_fails_does_not_stop_the_rest_of_the_run():
    client = FakeClient(
        graph(
            lexemes=[word("w1", createdAt="2026-06-01T00:00:00.000Z"), word("w2")],
            senses=[sense("s1", "w1"), sense("s2", "w2")],
            imagePrompts=[prompt("p1", "w1", "s1"), prompt("p2", "w2", "s2")],
        ),
        refuse={"p1": "llm_failed"},
    )
    result = sweep(client, report=lambda line: None)
    assert client.rendered == ["p1", "p2"]
    assert result.failed == 1 and result.drawn == 1
    assert result.problems == ["w1: llm_failed"]


def test_it_waits_out_a_rate_limit_and_never_waits_out_a_bad_credential(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("acervo.jobs.images.sweep.time.sleep", lambda seconds: slept.append(seconds))

    limited = FakeClient(
        graph(lexemes=[word("w1")], senses=[sense("s1", "w1")],
              imagePrompts=[prompt("p1", "w1", "s1")]),
        refuse={"p1": "llm_rate_limited"},
    )
    sweep(limited, report=lambda line: None)
    assert slept == [30.0, 60.0, 120.0], "three waits, then it gives up on this sense"
    assert len(limited.rendered) == 4

    slept.clear()
    rejected = FakeClient(
        graph(lexemes=[word("w1")], senses=[sense("s1", "w1")],
              imagePrompts=[prompt("p1", "w1", "s1")]),
        refuse={"p1": "llm_authentication"},
    )
    result = sweep(rejected, report=lambda line: None)
    # A rejected credential is a mistake to fix, not a condition to route around: waiting on one
    # would hide it and spend the night doing nothing.
    assert slept == []
    assert len(rejected.rendered) == 1 and result.failed == 1
