"""The narrow corpus client, against a recorded response from the real service.

`fixtures/search-es-picar.json` was captured from a running spoken-usage-retrieval 0.2.0 holding the
Spanish corpus. It is the contract in the only shape Acervo consumes, and it is the data every fake
corpus below serves — re-record it when `deploy/acervo/speech/pin.json` moves.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from acervo.clips.corpus import Candidate, Corpus, CorpusError

FIXTURE = Path(__file__).parent / "fixtures" / "search-es-picar.json"


def recorded() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def serving(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def answering(payload, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.seen = request
        return httpx.Response(status, json=payload)
    handler.seen = None
    return handler


def test_the_search_asks_for_what_the_design_fixed():
    handler = answering(recorded())
    Corpus("http://corpus/api/v1", http=serving(handler)).search("es", "picar")

    query = dict(handler.seen.url.params)
    assert query == {
        "language": "es", "q": "picar", "match_mode": "auto", "order": "ranked", "limit": "20"
    }
    assert handler.seen.url.path == "/api/v1/search"


def test_a_result_becomes_a_candidate_carrying_only_what_a_clip_needs():
    found = Corpus("http://corpus/api/v1", http=serving(answering(recorded()))).search("es", "picar")

    assert len(found) == 3
    first = found[0]
    assert isinstance(first, Candidate)
    assert first.segment_id == "seg_fafe38592cc31df5c430"
    assert first.sentence == "Y ella ya le va a empezar a picar porque es raro, chicos."
    # The corpus guarantees the matched surface is verbatim at those offsets. `Example.matchedForm`
    # rests on exactly that, so it is worth asserting against a real recording rather than a stub.
    assert first.matched_surface == "picar"
    assert first.sentence[first.char_start:first.char_end] == first.matched_surface
    assert first.video_url == "https://www.youtube.com/watch?v=ebJDiXbeHTY"
    assert first.channel == "LUZU TV"
    assert first.caption_kind == "automatic"
    assert "Argentina" in first.varieties and "conversation" in first.speech_style
    assert first.boundary_reason == "punctuation"


def test_the_stored_seconds_bracket_the_speech():
    """Floored start, ceiled end — a clip must not begin after the speech does or end before it."""
    found = Corpus("http://corpus/api/v1", http=serving(answering(recorded()))).search("es", "picar")
    first = found[0]
    assert first.start_second <= first.clip_start
    assert first.end_second >= first.clip_end
    # And the invariant the graph enforces on the pair.
    assert first.end_second > first.start_second


def test_one_sentence_saying_the_word_twice_is_one_candidate():
    """The corpus answers per occurrence. Offering the same sentence twice spends candidate budget
    on nothing and invites the model to name the copy the request did not index."""
    payload = recorded()
    again = json.loads(json.dumps(payload["results"][0]))
    again["occurrence_id"] = again["occurrence_id"] + ":again"
    again["rank"] = 9
    payload["results"].append(again)

    found = Corpus("http://corpus/api/v1", http=serving(answering(payload))).search("es", "picar")
    assert len(found) == 3
    assert [row.rank for row in found] == [1, 2, 3]      # the better rank is the one kept


def test_a_row_with_no_video_reference_is_not_a_candidate():
    """`videoRef` is what every clip field hangs on, so a row without one cannot become an example."""
    payload = recorded()
    payload["results"][0]["video"]["url"] = ""
    found = Corpus("http://corpus/api/v1", http=serving(answering(payload))).search("es", "picar")
    assert [row.segment_id for row in found] == [
        payload["results"][1]["segment_id"], payload["results"][2]["segment_id"]
    ]


@pytest.mark.parametrize(
    "status, reason",
    [(400, "rejected"), (503, "unavailable"), (500, "unavailable"), (404, "refused")],
)
def test_each_refusal_gets_its_own_reason(status, reason):
    """`rejected` is the one that is not a failure: a query this corpus will never accept."""
    handler = answering({"error": {"code": "invalid_request", "message": "too many words"}}, status)
    with pytest.raises(CorpusError) as raised:
        Corpus("http://corpus/api/v1", http=serving(handler)).search("es", "a b c d e f")
    assert raised.value.reason == reason


def test_a_dropped_connection_is_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(CorpusError) as raised:
        Corpus("http://corpus/api/v1", http=serving(handler)).search("es", "picar")
    assert raised.value.reason == "unreachable"


def test_status_reports_what_can_be_searched():
    """`indexedLanguages` is the field that decides whether a word was *consulted* at all."""
    payload = {
        "ready": True, "built_at": "2026-09-11T16:32:14.295846+00:00",
        "indexed_languages": ["es"], "videos": 251, "segments": 60704,
    }
    status = Corpus("http://corpus/api/v1", http=serving(answering(payload))).status()
    assert status["ready"] is True
    assert status["indexedLanguages"] == ("es",)
    assert status["builtAt"] == "2026-09-11T16:32:14.295846+00:00"
    assert (status["videos"], status["segments"]) == (251, 60704)


def test_an_unready_corpus_is_an_answer_rather_than_an_error():
    """A fresh deployment has no index and says so with a 200 — which is why the compose healthcheck
    asserts `/health/live` and not `/health/ready`."""
    payload = {"ready": False, "built_at": None, "indexed_languages": [], "videos": 0, "segments": 0}
    status = Corpus("http://corpus/api/v1", http=serving(answering(payload))).status()
    assert status["ready"] is False and status["indexedLanguages"] == ()
