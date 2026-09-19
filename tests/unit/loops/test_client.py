"""The narrow loop client, against recorded responses from the real service.

`fixtures/*.json` were captured from lexibeat 0.2.0 in-process — the contract in the only shape
Acervo consumes. Re-record them when `deploy/acervo/lexibeat/pin.json` moves; the recorder is in
that commit's message and takes half a minute.

Offline by construction, as `tests/unit/clips/test_corpus.py` is: `httpx.MockTransport` serves the
recordings, so this is a test of the *client* and never of the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from acervo.loops.client import Item, LoopError, LoopService

FIXTURES = Path(__file__).parent / "fixtures"


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def serving(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def answering(payload, status: int = 200, *, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return handler


def service(handler) -> LoopService:
    return LoopService("http://lexibeat:8000/api/v1", http=serving(handler))


# ── what it can be asked for ────────────────────────────────────────────────


def test_the_catalogues_are_read_from_the_service_and_never_copied_here():
    """A family or a second pattern added in a later version must appear with nothing changing on
    this side, which is only true while nothing here lists them."""
    schema = service(answering(recorded("schema"))).schema()
    assert schema.api_version == "1.0.0"
    assert set(schema.patterns) == {"retrieval", "alternating"}
    assert "auto" in schema.families and len(schema.families) > 5
    assert schema.max_items > 0


def test_a_deployment_with_no_samples_says_so_rather_than_failing():
    """Not an error: the service serves, and that is why its healthcheck asserts liveness. Worth
    saying, because the difference is recorded instruments against oscillators."""
    payload = {**recorded("schema"), "production_bundle": False, "palette": ["electronic"]}
    assert service(answering(payload)).schema().sample_free is True
    assert service(answering(recorded("schema"))).schema().sample_free is False


def test_liveness_is_a_question_that_answers_false_rather_than_raising():
    assert service(answering(recorded("health"))).alive() is True
    assert service(answering({"error": {"code": "x", "message": "y"}}, 503)).alive() is False


# ── a render ────────────────────────────────────────────────────────────────


def test_starting_a_render_sends_the_words_and_the_render_token():
    seen: list[httpx.Request] = []
    operation = service(answering(recorded("queued"), 202, seen=seen)).start(
        items=[Item("asco", "disgust", "repulsed, recoiling slightly")],
        source_language={"code": "es", "name": "Spanish"},
        target_language={"code": "en", "name": "English"},
        token="a-render-scoped-token", delivery="plain", seed=11,
    )
    body = json.loads(seen[0].content)
    assert body["items"] == [{"source": "asco", "target": "disgust",
                              "direction": "repulsed, recoiling slightly"}]
    assert body["source_language"] == {"code": "es", "name": "Spanish"}
    # The whole of what the generator is given to speak with: it holds no provider key of its own,
    # and no way of its own to find out what that voice can do.
    assert body["speech"] == {"token": "a-render-scoped-token", "delivery": "plain"}
    assert operation.status == "queued" and not operation.finished


def test_a_completed_operation_carries_exactly_the_two_collections():
    operation = service(answering(recorded("completed"))).operation("whatever")
    assert operation.finished and operation.successful is True
    loop = operation.result
    assert loop is not None
    # §2.9's `loops` row...
    assert loop.style_id and loop.seed and loop.engine_version and loop.bed_fingerprint
    assert loop.pattern == "retrieval" and loop.duration_seconds > 0 and loop.bpm > 0
    assert loop.audio_mime == "audio/mpeg"
    # ...and its `loopItems`, with what was *said* and the four times.
    assert len(loop.timeline) == 2
    first = loop.timeline[0]
    assert first["source"] == "asco" and first["target"] == "disgust"
    assert first["start"] <= first["source_reveal"] <= first["target_reveal"] <= first["end"]


def test_the_resolved_bed_is_not_in_the_answer_and_is_not_wanted():
    """Style, seed and engine version replay it; the fingerprint proves the replay. Nothing here
    stores opaque JSON."""
    assert "bed_spec" not in recorded("completed")["result"]


def test_an_unfinished_operation_reports_progress_rather_than_a_result():
    payload = {**recorded("queued"), "status": "running",
               "progress": {"fraction": 0.42, "message": "Synthesizing 7 of 12"}}
    operation = service(answering(payload)).operation("x")
    assert not operation.finished and operation.result is None
    assert operation.fraction == pytest.approx(0.42)
    assert operation.message == "Synthesizing 7 of 12"


def test_a_failed_render_is_an_answer_with_a_reason_rather_than_an_exception():
    payload = {**recorded("queued"), "status": "failed", "successful": False,
               "error": "RuntimeError: the voice refused"}
    operation = service(answering(payload)).operation("x")
    assert operation.finished and operation.successful is False
    assert "refused" in (operation.error or "")


# ── the track ───────────────────────────────────────────────────────────────


def test_the_track_is_fetched_from_the_url_the_service_gave_and_stored_as_it_arrives():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ID3mp3bytes", headers={"content-type": "audio/mpeg"})

    url = recorded("completed")["result"]["audio_url"]
    data, mime = LoopService("http://lexibeat:8000/api/v1", http=serving(handler)).track(url)
    assert data == b"ID3mp3bytes" and mime == "audio/mpeg"
    # Resolved against the service's own root, and never concatenated from anything a client sent:
    # this path came out of an answer this module parsed.
    assert str(seen[0].url) == f"http://lexibeat:8000{url}"


# ── what it refuses ─────────────────────────────────────────────────────────


def test_a_service_that_cannot_be_reached_is_its_own_refusal():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(LoopError) as refused:
        service(handler).schema()
    assert refused.value.code == "unreachable"


def test_a_busy_queue_is_told_apart_from_a_refusal():
    busy = {"error": {"code": "queue_full", "message": "The render queue is full."}}
    with pytest.raises(LoopError) as refused:
        service(answering(busy, 429)).operation("x")
    assert refused.value.code == "busy"
    assert "queue is full" in refused.value.message


def test_an_answer_that_describes_no_operation_is_refused_rather_than_half_read():
    for payload in ({}, {"status": "completed"}, ["not", "a", "mapping"]):
        with pytest.raises(LoopError):
            service(answering(payload)).operation("x")


def test_the_six_utterance_spans_become_the_two_numbers_acervo_stores():
    """A word is said, then its translation, then that pair twice more.

    Acervo keeps two numbers rather than six spans — how many times the pair is said and how far
    apart — which is what lets the player mark *which* of the pair is sounding without the schema
    moving the day three repetitions become four. This is the arithmetic that turns one into the
    other, pinned against a render the real service produced.
    """
    loop = service(answering(recorded("completed"))).operation("whatever").result
    assert loop is not None
    row = loop.timeline[0]
    # The recorded render says `asco` at 8.82, `disgust` at 17.65, then the pair again at 22.06 /
    # 26.47 and at 30.88 / 35.29 — evenly 4.41 apart, three times in all.
    assert row["repeats"] == 3
    assert row["repeat_seconds"] == pytest.approx(4.41, abs=0.01)
    # And the two numbers put every utterance back where the render had it.
    spoken = [row["start"]] + [row["target_reveal"] + step * row["repeat_seconds"]
                               for step in range(2 * row["repeats"] - 1)]
    assert spoken == pytest.approx([8.82, 17.65, 22.06, 26.47, 30.88, 35.29], abs=0.02)
    # Nothing of the service's own shape escapes: the spans it sent are not in what came back.
    assert "utterances" not in row


def test_a_render_that_reported_no_spans_says_so_rather_than_guessing():
    """Zero is "unknown", and the player then marks only the first pass rather than the wrong one."""
    payload = recorded("completed")
    for row in payload["result"]["timeline"]:
        row.pop("utterances", None)
    result = service(answering(payload)).operation("whatever").result
    assert result is not None
    assert result.timeline[0]["repeats"] == 0 and result.timeline[0]["repeat_seconds"] == 0.0
