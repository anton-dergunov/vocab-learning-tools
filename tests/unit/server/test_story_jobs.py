"""The `story` job: write, translate, brief, draw.

The models are faked at `acervo.models.call`'s own seams — `completion` and `image_generation` —
so this exercises the real chain, the real parsers and the real writes, and never the network.

What is pinned here is the two things the four-step shape exists for: that three good steps survive
a fourth that fails, and that a retry redraws only the pictures that are actually missing.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import litellm
import pytest
from graph_records import lexeme, sense, vocabulary

from acervo.repository import graph, jobs
from acervo.work import kinds
from acervo.work.runner import Runner

# A real PNG, as `conftest.ImageStub` uses: the renderer decodes what comes back before it
# re-encodes, so a byte string that is not an image fails inside Pillow rather than in the job.
PICTURE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def story_reply(parts: int = 4) -> dict:
    return {
        "title": "El perro asombroso",
        "emoji": "🐕",
        "parts": [
            {"heading": f"Parte viva {index}", "text": f"Marcos vio algo asombroso. Numero {index}."}
            for index in range(parts)
        ],
        "words": [{"lexemeId": "", "forms": ["asombroso"]}],
    }


def translation_reply(parts: int = 4) -> dict:
    return {
        "title": "The amazing dog",
        "parts": [{"heading": f"Live part {index}", "text": f"Marcos saw something amazing. {index}."}
                  for index in range(parts)],
    }


def brief_reply(parts: int = 4) -> dict:
    return {
        "cast": "MARCOS: a thin man in a green jacket.",
        "world": "A Spanish street on a Saturday morning.",
        "parts": [{"brief": f"A thin man in a green jacket stands in a street. Scene {index}."}
                  for index in range(parts)],
    }


class Models:
    """The text chain and the image chain, answering in the order the job asks."""

    def __init__(self) -> None:
        self.texts: list[dict] = []
        self.prompts: list[str] = []
        self.image_calls = 0
        self.image_fails_after: int | None = None
        self.image_rate_limited = False

    def completion(self, **kwargs):
        self.prompts.append(kwargs["messages"][-1]["content"])
        payload = self.texts.pop(0)
        return litellm.ModelResponse(
            model=kwargs["model"],
            choices=[{"index": 0, "finish_reason": "stop",
                      "message": {"role": "assistant", "content": json.dumps(payload)}}],
        )

    def image_generation(self, **kwargs):
        self.image_calls += 1
        if self.image_rate_limited:
            raise litellm.RateLimitError(message="no allowance left", llm_provider="p", model="m")
        if self.image_fails_after is not None and self.image_calls > self.image_fails_after:
            # A *refusal* of this particular brief, not a rate limit. The two are deliberately
            # different here: a refusal is about the brief, so it is recorded on the part and the
            # loop goes on; an exhausted allowance stops the step without burning anybody's
            # retries, which `test_an_exhausted_allowance_costs_no_part_its_retries` pins.
            raise litellm.BadRequestError(message="that brief was declined", model="m",
                                          llm_provider="p")
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(PICTURE).decode())], usage=None
        )


@pytest.fixture
def models(server, monkeypatch) -> Models:
    stub = Models()
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    # The `server` fixture clears every provider but Gemini, which draws nothing. OpenAI is the
    # image row `test_images.py` credentials for the same reason.
    monkeypatch.setenv("OPENAI_API_KEY", "a-key")
    monkeypatch.setattr("acervo.models.call.completion", lambda **kw: stub.completion(**kw))
    monkeypatch.setattr("acervo.models.call.image_generation",
                        lambda **kw: stub.image_generation(**kw))

    # The real encoder runs, on a real PNG: it is the same WebP path a drawn picture takes, and
    # stubbing it would leave the bytes the digest is taken from untested.
    return stub


@pytest.fixture
def runner(server) -> Runner:
    return Runner(server.settings)


def only_the_story(server) -> None:
    """Clear the `enrich` jobs that saving a word queues.

    They are queued in the same transaction as the record, which is the design — but they would run
    first here and eat the replies stubbed for the story, so a test about the story job would
    silently be a test about enrichment.
    """
    for job in jobs.open_jobs(server.owner):
        if job["kind"] != "story":
            jobs.finish(job["id"], "cancelled")


def a_story(server, count: int = 2) -> dict:
    server.push({"vocabularies": [vocabulary()]})
    ids = []
    for index in range(count):
        entry = lexeme(headword="asombroso" if index == 0 else f"palabra{index}",
                       lemma="asombroso" if index == 0 else f"palabra{index}",
                       status="active", shortGloss=f"word {index}")
        server.push({"lexemes": [entry], "senses": [sense(entry["id"])]})
        ids.append(entry["id"])
    answer = server.post("/stories", {"deviceId": "device000000001", "language": "es",
                                      "lexemeIds": ids, "typeId": "funny",
                                      "styleId": "comic-book"})
    assert answer.status_code == 202, answer.text
    only_the_story(server)
    return answer.json()["data"]["story"]


def test_the_kind_declares_its_four_steps_before_it_runs(server):
    """The progress strip names them while the job is queued, so they cannot be discovered late."""
    assert kinds.find("story").steps == (
        "story.write", "story.translate", "story.brief", "story.draw"
    )


def test_a_whole_story_is_written_translated_briefed_and_drawn(server, models, runner):
    story = a_story(server, 2)
    words = graph.story_words(server.owner, story["id"])
    reply = story_reply(4)
    reply["words"] = [{"lexemeId": words[0]["lexemeId"], "forms": ["asombroso"]}]
    models.texts = [reply, translation_reply(4), brief_reply(4)]

    runner.run_until_idle()

    held = graph.owned_records(server.owner, "stories", [story["id"]])[story["id"]]
    assert held["title"] == "El perro asombroso"
    assert held["titleTranslation"] == "The amazing dog"
    assert held["modelId"], "the entry records the model that answered"

    parts = graph.story_parts(server.owner, story["id"])
    assert len(parts) == 4
    assert all(part["translation"] for part in parts), "every part is translated"
    assert all(part["imagePrompt"] for part in parts), "every part is briefed"
    assert all(part["imageRef"] for part in parts), "every part is drawn"
    assert models.image_calls == 4, "one image call per part"

    # The word the story used is recorded with the form it used; the other is honestly empty.
    refreshed = graph.story_words(server.owner, story["id"])
    assert refreshed[0]["forms"] == ["asombroso"]
    assert refreshed[1]["forms"] == []


def test_the_briefs_are_asked_for_in_one_call_covering_every_part(server, models, runner):
    """The load-bearing half of the design: a model that sees all four parts can keep the same
    character in the same coat, and one that sees one cannot."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    runner.run_until_idle()

    briefing = models.prompts[2]
    for index in range(4):
        assert f"Numero {index}" in briefing, "every part is in the one briefing call"


def test_a_story_whose_pictures_fail_is_still_a_story_you_can_read(server, models, runner):
    """Four steps exist so three can survive the fourth. A half-drawn story is readable; a
    half-written one is not."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    models.image_fails_after = 1  # the first lands, the rest are refused

    runner.run_until_idle()

    parts = graph.story_parts(server.owner, story["id"])
    assert sum(1 for part in parts if part["imageRef"]) == 1
    assert all(part["text"] and part["translation"] for part in parts), "the story survived"
    undrawn = [part for part in parts if not part["imageRef"]]
    assert all(part["failureReason"] for part in undrawn), "and each says why it has no picture"
    assert all(part["attempts"] == 1 for part in undrawn)


def test_an_exhausted_allowance_costs_no_part_its_retries(server, models, runner):
    """`services/images.py`'s rule: an allowance that ran out is not something wrong with the
    brief, so it must not use up a part's attempts. This loop adds the other half — the step stops
    rather than walking the same exhausted chain once per remaining part."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    models.image_rate_limited = True

    runner.run_until_idle()

    parts = graph.story_parts(server.owner, story["id"])
    assert all(part["attempts"] == 0 for part in parts), "nobody's retries were spent"
    assert models.image_calls == 1, "it stopped rather than collecting the same refusal four times"
    assert all(part["text"] for part in parts), "and the story it already wrote is intact"


def test_trying_again_redraws_only_the_pictures_that_are_missing(server, models, runner):
    """`story.draw` re-derives what is missing from the graph rather than being handed it, which is
    what makes a retry cost one picture rather than four."""
    story = a_story(server, 1)
    models.texts = [story_reply(4), translation_reply(4), brief_reply(4)]
    models.image_fails_after = 1
    runner.run_until_idle()
    assert models.image_calls == 4  # one drawn, three refused

    models.image_fails_after = None
    models.image_calls = 0
    jobs.enqueue(server.owner, "story", trigger="manual", subject_kind="story",
                 subject_id=story["id"])
    runner.run_until_idle()

    # The three that were missing, and **not** the one already drawn, nor a second story call.
    assert models.image_calls == 3
    parts = graph.story_parts(server.owner, story["id"])
    assert all(part["imageRef"] for part in parts)


def test_a_writer_that_refuses_is_terminal_rather_than_retried(server, models, runner):
    """The writer judged, so trying another model pays twice for the same answer."""
    story = a_story(server, 1)
    models.texts = [{"refused": True, "reason": "that word is a slur"}]

    runner.run_until_idle()

    job = [one for one in jobs.recent(server.owner) if one["kind"] == "story"][0]
    assert job["state"] == "failed"
    assert "slur" in (job["message"] or ""), "the writer's own words survive the hand-off"
    # And the story reads as one that was asked for and never written.
    assert graph.story_parts(server.owner, story["id"]) == []
