"""Reading a story aloud: one voice for the whole story, whatever the models do.

Against the real service, the real chains and the real encoder. What is stubbed is the two providers
and only them — the text model (`acervo.models.call.completion`) that cuts a part into passages, and
Cloud TTS's adapter, which answers with a real WAV and records what it was asked. So a test can say
which voice read a passage, whether a direction reached it, and which pair was never asked.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

import litellm
import pytest
from test_story_jobs import (
    Models, a_story, brief_reply, story_reply, translation_reply,
)

from acervo.models.errors import ProviderUnavailable
from acervo.repository import graph, jobs, pronunciation_settings
from acervo.work.runner import Runner

DEVICE = "device000000001"
FIRST, SECOND = "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-tts"


def wav(words: str) -> bytes:
    frames = bytearray()
    for index in range(2_400 * max(len(words), 1)):
        frames += struct.pack("<h", int(12_000 * math.sin(2 * math.pi * 220 * index / 24_000)))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24_000)
        out.writeframes(bytes(frames))
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def a_voice(server, monkeypatch, tmp_path):
    """Cloud TTS is credentialed and answers. `speech.fail[model]` makes one model refuse."""
    credentials = tmp_path / "service-account.json"
    credentials.write_text("{}")
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project-name")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(credentials))
    monkeypatch.delenv("ACERVO_VERTEX_ACCOUNT", raising=False)
    calls: list[dict] = []

    def speech(row, model, words, **kwargs):
        calls.append({"provider": row.id, "model": model, "words": words, **kwargs})
        if model in speech.fail:
            raise speech.fail[model]
        return wav(words), "audio/wav"

    speech.calls, speech.fail = calls, {}
    monkeypatch.setattr("acervo.models.google_tts.speech", speech)
    server.speech = speech
    return speech


@pytest.fixture
def models(server, monkeypatch) -> Models:
    stub = Models()
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    monkeypatch.setenv("OPENAI_API_KEY", "a-key")
    monkeypatch.setattr("acervo.models.call.completion", lambda **kw: stub.completion(**kw))
    monkeypatch.setattr("acervo.models.call.image_generation", lambda **kw: stub.image_generation(**kw))
    return stub


@pytest.fixture
def runner(server) -> Runner:
    return Runner(server.settings)


def narrate_reply(text: str, direction: str = "Hushed and slow.") -> dict:
    """What the text model returns for a part: one passage per sentence, verbatim."""
    sentences = [one.strip() + "." for one in text.split(".") if one.strip()]
    return {"segments": [{"text": one, "direction": f"{direction} {index}"} for index, one in enumerate(sentences)]}


def switch(server, **changes) -> None:
    pronunciation_settings.save(server.owner, **changes)


def written(server, models, runner, parts: int = 3) -> dict:
    """A story that has been written, translated, briefed and drawn — with nothing read aloud yet."""
    switch(server, pregenerate={"stories": False})
    story = a_story(server, 2)
    models.texts = [story_reply(parts), translation_reply(parts), brief_reply(parts)]
    runner.run_until_idle()
    switch(server, pregenerate={"stories": True})
    return story


def read(server, story, part, *, expect: int = 200):
    answer = server.post(f"/stories/{story['id']}/parts/{part['id']}/audio", {"deviceId": DEVICE})
    assert answer.status_code == expect, answer.text
    return answer.json()["data"] if expect == 200 else answer.json()["error"]


def parts_of(server, story) -> list[dict]:
    return graph.story_parts(server.owner, story["id"])


# ── one part, on demand ─────────────────────────────────────────────────────


def test_a_clear_voice_reads_the_part_in_one_go_with_no_passages_and_no_text_call(server, models, runner):
    story = written(server, models, runner, parts=3)
    switch(server, delivery={"stories": "plain"})
    part = parts_of(server, story)[0]

    row = read(server, story, part)

    assert len(server.speech.calls) == 1, "one call for the whole part"
    assert server.speech.calls[0]["words"] == part["text"]
    assert not server.speech.calls[0].get("style"), "a clear voice is not sent a direction"
    assert models.texts == [] and len(models.prompts) == 3, "and nobody was asked where to cut it"
    assert row["audioRef"].startswith(f"stories/{story['id']}/{part['id']}-")
    assert row["audioMime"] == "audio/ogg" and row["audioSegments"] == []
    assert (row["audioProviderId"], row["audioModelId"]) == ("google-tts", "wavenet")
    assert Path(server.settings.media_path, row["audioRef"]).read_bytes()[:4] == b"OggS"


def test_a_directed_voice_reads_a_passage_at_a_time_and_says_where_each_is(server, models, runner):
    story = written(server, models, runner, parts=3)
    part = parts_of(server, story)[0]
    models.texts = [narrate_reply(part["text"])]

    row = read(server, story, part)

    passages = row["audioSegments"]
    assert [one["text"] for one in passages] == ["Marcos vio algo asombroso. ", "Numero 0."]
    assert "".join(one["text"] for one in passages) == part["text"], "what is read is exactly what is written"
    assert [call["words"] for call in server.speech.calls] == ["Marcos vio algo asombroso.", "Numero 0."]
    assert [one["direction"] for one in passages] == ["Hushed and slow. 0", "Hushed and slow. 1"]
    for call, passage in zip(server.speech.calls, passages):
        assert passage["direction"] in call["style"], "the direction reached the voice"
        assert "storyteller" in call["style"], "framed as a narrator, not as a person in the moment"
    assert passages[0]["start"] == 0 and passages[0]["end"] < passages[1]["start"] < passages[1]["end"]
    assert row["audioProviderId"] == "google-tts" and row["audioModelId"] == FIRST


def test_a_direction_is_recorded_only_when_it_was_actually_sent(server, models, runner):
    """The order is a chain, and a model in it may not take a direction. Recording the direction that
    was *asked* would claim a reading nobody gave."""
    story = written(server, models, runner, parts=3)
    part = parts_of(server, story)[0]
    server.speech.fail[FIRST] = ProviderUnavailable("unavailable", "down", provider_id="google-tts", model=FIRST)
    server.speech.fail[SECOND] = ProviderUnavailable("unavailable", "down", provider_id="google-tts", model=SECOND)
    models.texts = [narrate_reply(part["text"])]

    row = read(server, story, part)

    assert row["audioModelId"] == "wavenet", "the last pair in the order answered"
    assert all(one["direction"] == "" for one in row["audioSegments"])


def test_a_part_that_is_not_in_the_story_is_not_found(server, models, runner):
    story = written(server, models, runner, parts=3)

    error = read(server, story, {"id": "notapart0000001"}, expect=404)

    assert error["code"] == "not_found"


# ── one voice for the whole story ───────────────────────────────────────────


def test_the_pair_that_answered_first_reads_every_later_passage_and_part(server, models, runner):
    story = written(server, models, runner, parts=3)
    first, second, *_ = parts_of(server, story)
    models.texts = [narrate_reply(first["text"]), narrate_reply(second["text"])]
    # The first pair in the order is down for the first passage, so the second answers it…
    server.speech.fail[FIRST] = ProviderUnavailable("unavailable", "down", provider_id="google-tts", model=FIRST)

    read(server, story, first)
    server.speech.fail.clear()  # …and is healthy again by the time the next part is read.
    server.speech.calls.clear()
    row = read(server, story, second)

    assert {call["model"] for call in server.speech.calls} == {SECOND}, "the story keeps its speaker"
    assert row["audioModelId"] == SECOND
    held = parts_of(server, story)
    assert held[0]["audioVoice"] == held[1]["audioVoice"] != ""
    assert {call["voice"] for call in server.speech.calls} == {held[0]["audioVoice"]}


def test_a_pair_that_is_pinned_is_never_left_for_another_when_it_refuses(server, models, runner):
    story = written(server, models, runner, parts=3)
    first, second, *_ = parts_of(server, story)
    models.texts = [narrate_reply(first["text"]), narrate_reply(second["text"])]
    read(server, story, first)
    server.speech.calls.clear()
    server.speech.fail[FIRST] = ProviderUnavailable("unavailable", "down", provider_id="google-tts", model=FIRST)

    error = read(server, story, second, expect=503)

    assert error["code"] == "llm_unavailable"
    assert {call["model"] for call in server.speech.calls} == {FIRST}, "nothing else was asked"
    assert not parts_of(server, story)[1]["audioRef"], "and nothing was written"


def test_a_pair_that_can_no_longer_be_asked_for_does_not_hold_the_story_to_it(server, models, runner):
    story = written(server, models, runner, parts=3)
    first, second, *_ = parts_of(server, story)
    models.texts = [narrate_reply(first["text"]), narrate_reply(second["text"])]
    read(server, story, first)
    # The recorded pair is one this server no longer offers: rewrite what the first part says.
    stale = graph.owned_records(server.owner, "storyParts", [first["id"]])[first["id"]]
    graph.merge_graph(server.owner, DEVICE, {"storyParts": [{**stale, "audioModelId": "gone-model"}]}, enqueue=None)

    row = read(server, story, second)

    assert row["audioRef"], "it was recorded with whatever answers first"


# ── when the models let it down ─────────────────────────────────────────────


def test_a_part_the_text_models_cannot_cut_is_read_whole_rather_than_left_silent(server, models, runner):
    story = written(server, models, runner, parts=3)
    part = parts_of(server, story)[0]
    models.texts = [{"nonsense": True}] * 6

    row = read(server, story, part)

    assert [call["words"] for call in server.speech.calls] == [part["text"]]
    assert not server.speech.calls[0].get("style"), "there was no direction to send"
    assert row["audioRef"] and row["audioSegments"] == []


def test_a_rate_limited_text_model_is_a_wait_not_a_fallback(server, models, runner, monkeypatch):
    story = written(server, models, runner, parts=3)
    part = parts_of(server, story)[0]

    def limited(**kwargs):
        raise litellm.RateLimitError(message="no allowance", llm_provider="p", model="m")

    monkeypatch.setattr("acervo.models.call.completion", limited)

    error = read(server, story, part, expect=503)

    assert error["code"] == "llm_rate_limited"
    assert server.speech.calls == [], "the voice is not spent on a part nobody has cut yet"


# ── the job ─────────────────────────────────────────────────────────────────


def _step(server, name: str) -> dict:
    job = [one for one in jobs.recent(server.owner) if one["kind"] == "story"][0]
    return next(step for step in job["steps"] if step["name"] == name)


def test_the_job_reads_every_part_in_one_voice_and_reports_how_far_it_has_got(server, models, runner):
    story = a_story(server, 2)
    models.texts = [story_reply(3), translation_reply(3), brief_reply(3)]
    models.texts += [narrate_reply(f"Marcos vio algo asombroso. Numero {index}.") for index in range(3)]

    runner.run_until_idle()

    held = parts_of(server, story)
    assert all(part["audioRef"] for part in held)
    assert len({(part["audioProviderId"], part["audioModelId"], part["audioVoice"]) for part in held}) == 1
    step = _step(server, "story.audio")
    assert step["state"] == "done" and (step["done"], step["total"]) == (3, 3)


def test_a_story_is_not_recorded_when_the_switch_is_off(server, models, runner):
    switch(server, pregenerate={"stories": False})
    story = a_story(server, 2)
    models.texts = [story_reply(3), translation_reply(3), brief_reply(3)]

    runner.run_until_idle()

    assert server.speech.calls == []
    assert _step(server, "story.audio")["state"] == "skipped"
    assert not any(part["audioRef"] for part in parts_of(server, story))


def test_trying_again_after_a_failed_recording_records_the_rest_and_writes_no_second_story(
        server, models, runner, monkeypatch):
    """The way a story most often fails is its last step. Try again queues every step again, and the
    first three must find their work already done — otherwise the retry writes the story a second
    time, beside the first, before it ever reaches the recording."""
    story = a_story(server, 2)
    models.texts = [story_reply(3), translation_reply(3), brief_reply(3)]
    models.texts += [narrate_reply(f"Marcos vio algo asombroso. Numero {index}.") for index in range(3)]
    # The second part's recording fails outright: a voice that refuses it, and no other in the chain.
    original = server.speech
    calls = {"count": 0}

    def flaky(row, model, words, **kwargs):
        calls["count"] += 1
        if "Numero 2" in words:
            raise ProviderUnavailable("authentication", "rejected", provider_id="google-tts", model=model)
        return original(row, model, words, **kwargs)

    monkeypatch.setattr("acervo.models.google_tts.speech", flaky)
    runner.run_until_idle()
    assert [bool(part["audioRef"]) for part in parts_of(server, story)] == [True, True, False]
    ids_before = [part["id"] for part in parts_of(server, story)]

    monkeypatch.setattr("acervo.models.google_tts.speech", original)
    models.texts = [narrate_reply("Marcos vio algo asombroso. Numero 2.")]
    answer = server.post("/jobs", {"kind": "story", "subject": {"kind": "story", "id": story["id"]}})
    assert answer.status_code in (200, 202), answer.text
    runner.run_until_idle()

    held = parts_of(server, story)
    assert [part["id"] for part in held] == ids_before, "no second set of parts"
    assert all(part["audioRef"] for part in held)
    assert len(models.prompts) == 3 + 3 + 1, "the writer, translator and briefer were not asked again"


# ── deleting ────────────────────────────────────────────────────────────────


def test_deleting_a_story_removes_its_recordings_with_its_pictures(server, models, runner):
    story = written(server, models, runner, parts=3)
    part = parts_of(server, story)[0]
    models.texts = [narrate_reply(part["text"])]
    row = read(server, story, part)
    recording = Path(server.settings.media_path, row["audioRef"])
    assert recording.exists()

    answer = server.delete(f"/stories/{story['id']}", headers={"x-acervo-device": DEVICE})

    assert answer.status_code == 200, answer.text
    assert not recording.exists()
