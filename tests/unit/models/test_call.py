"""One row, one call — and the classification that the retry contract rests on.

The exceptions here are real LiteLLM exceptions, not stand-ins. Stubbing this package's own error
types would leave `classify()` untested, and `classify()` is the thing that can change retry
behaviour without the retry code changing.
"""

from __future__ import annotations

import base64
import json

import httpx
import litellm
import pytest

from acervo.models import call
from acervo.models.catalogue import load_catalogue
from acervo.models.errors import RETRYABLE, TERMINAL, ProviderRefused, ProviderUnavailable

SHIPPED = load_catalogue()
GEMINI = SHIPPED.find("gemini-free")       # jsonSchema: native
CLOUDFLARE = SHIPPED.find("cloudflare")    # jsonSchema: prompt
PRIVATE = "provider details that must stay private"


def reply(text: str, model: str = "gemini/gemini-3.1-flash-lite"):
    return litellm.ModelResponse(
        model=model,
        choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
    )


def response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://provider.example.com"))


def failures():
    """Every LiteLLM exception Acervo can meet, built the way its constructor wants."""
    return {
        "authentication": litellm.AuthenticationError(message=PRIVATE, llm_provider="p", model="m"),
        "permission": litellm.PermissionDeniedError(
            message=PRIVATE, llm_provider="p", model="m", response=response(403)
        ),
        "bad_request": litellm.BadRequestError(message=PRIVATE, model="m", llm_provider="p"),
        "context_window": litellm.ContextWindowExceededError(message=PRIVATE, model="m", llm_provider="p"),
        "not_found": litellm.NotFoundError(message=PRIVATE, model="m", llm_provider="p"),
        "rate_limit": litellm.RateLimitError(message=PRIVATE, llm_provider="p", model="m"),
        "internal": litellm.InternalServerError(message=PRIVATE, llm_provider="p", model="m"),
        "unavailable": litellm.ServiceUnavailableError(message=PRIVATE, llm_provider="p", model="m"),
        "teapot": litellm.APIError(status_code=418, message=PRIVATE, llm_provider="p", model="m"),
        "timeout": litellm.Timeout(message=PRIVATE, model="m", llm_provider="p"),
        "connection": litellm.APIConnectionError(message=PRIVATE, llm_provider="p", model="m"),
        "unknown": RuntimeError(PRIVATE),
    }


REASONS = {
    "authentication": "authentication",
    "permission": "authentication",
    "bad_request": "configuration",
    "context_window": "configuration",
    "not_found": "configuration",
    "rate_limit": "rate_limited",
    "internal": "unavailable",
    "unavailable": "unavailable",
    "teapot": "refused",
    "timeout": "unreachable",
    "connection": "unreachable",
    "unknown": "refused",
}


@pytest.mark.parametrize("name", sorted(REASONS), ids=sorted(REASONS))
def test_every_provider_failure_lands_on_exactly_one_reason(name):
    reason, _status = call.classify(failures()[name])
    assert reason == REASONS[name]


def test_a_timeout_and_a_dropped_connection_are_not_classified_by_their_status():
    """The two that a status-only map gets wrong, and the reason this test exists at all.

    `Timeout` carries 408 and `APIConnectionError` carries 500. Read numerically, a timeout becomes
    `refused` — which `scripts/ingest_vocabulary_file.py` does not retry. The retry behaviour would
    have changed without a line of the retry code changing.
    """
    timeout, connection = failures()["timeout"], failures()["connection"]
    assert timeout.status_code == 408 and connection.status_code == 500
    assert call.classify(timeout) == ("unreachable", 408)
    assert call.classify(connection) == ("unreachable", 500)


@pytest.mark.parametrize("name", sorted(REASONS), ids=sorted(REASONS))
def test_a_failure_is_either_retryable_at_the_next_row_or_terminal_for_the_chain(monkeypatch, name):
    monkeypatch.setattr(call, "completion", _raising(failures()[name]))
    with pytest.raises((ProviderRefused, ProviderUnavailable)) as caught:
        call.text("hello", row=GEMINI)
    expected = ProviderUnavailable if REASONS[name] in RETRYABLE else ProviderRefused
    assert isinstance(caught.value, expected)
    assert (REASONS[name] in RETRYABLE) != (REASONS[name] in TERMINAL)


def test_the_failing_row_and_model_are_carried_on_the_error(monkeypatch):
    monkeypatch.setattr(call, "completion", _raising(failures()["rate_limit"]))
    with pytest.raises(ProviderUnavailable) as caught:
        call.text("hello", row=GEMINI)
    assert caught.value.provider_id == "gemini-free"
    assert caught.value.model == "gemini/gemini-3.1-flash-lite"
    assert caught.value.status == 429


def test_a_key_echoed_back_by_a_provider_is_redacted_before_it_reaches_the_exception(monkeypatch):
    """Providers echo the request in an error, and this repository is public."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-not-a-real-key-000")
    monkeypatch.setattr(
        call,
        "completion",
        _raising(
            litellm.BadRequestError(
                message="rejected x-goog-api-key=AIzaSy-not-a-real-key-000", model="m", llm_provider="p"
            )
        ),
    )
    with pytest.raises(ProviderRefused) as caught:
        call.text("hello", row=GEMINI)
    assert "AIzaSy" not in caught.value.detail
    assert "«redacted»" in caught.value.detail


def test_a_native_row_is_asked_for_json_and_a_prompt_row_is_not(monkeypatch):
    """The capability declaration doing its one job: the package adapts at the call boundary."""
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply('{"a": 1}')))

    call.text("hello", row=GEMINI, as_json=True)
    assert calls[-1]["response_format"] == {"type": "json_object"}

    call.text("hello", row=CLOUDFLARE, as_json=True)
    assert "response_format" not in calls[-1]


def test_a_prompt_rows_reply_is_still_parsed(monkeypatch):
    """`prompt` means the instruction is the prompt's job, not that JSON is not expected back."""
    monkeypatch.setattr(call, "completion", _recording([], reply('{"headword": "el garfio"}')))
    assert call.text("hello", row=CLOUDFLARE, as_json=True).parsed == {"headword": "el garfio"}


def test_a_reply_that_is_not_json_parses_to_none_rather_than_raising(monkeypatch):
    """Whether an unreadable reply is an error is Acervo's question, not the provider's."""
    monkeypatch.setattr(call, "completion", _recording([], reply("not json at all")))
    result = call.text("hello", row=GEMINI, as_json=True)
    assert result.parsed is None
    assert result.text == "not json at all"


def test_a_fenced_reply_is_unwrapped(monkeypatch):
    monkeypatch.setattr(call, "completion", _recording([], reply('```json\n{"a": 1}\n```')))
    assert call.text("hello", row=GEMINI, as_json=True).parsed == {"a": 1}


def test_the_row_supplies_its_credential_its_endpoint_and_its_parameters(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a-gemini-key")
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))

    call.text("hello", row=GEMINI, system="be brief")
    assert calls[-1]["api_key"] == "a-gemini-key"
    assert calls[-1]["messages"][0] == {"role": "system", "content": "be brief"}
    assert calls[-1]["timeout"] == 120
    assert "vertex_location" not in calls[-1]

    # `params`, not an `if provider == "vertex"` — which is what let `reasoning_effort` be dropped
    # from this row, LiteLLM refusing it for these models, without touching the call path.
    call.text("hello", row=SHIPPED.find("vertex"))
    assert calls[-1]["vertex_location"] == "global"


def test_litellms_own_retries_are_switched_off_on_every_call(monkeypatch):
    """Both of them. `max_retries` is the provider SDK's and defaults to 2 when LiteLLM sets it.

    `models/chain.py` is the only fall-through in this codebase, and `acervo.client` carries no
    retries for the same reason: a retry inside the transport changes the behaviour of retry code
    that lives — and is tested — somewhere else.
    """
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))
    call.text("hello", row=GEMINI)
    assert calls[-1]["num_retries"] == 0
    assert calls[-1]["max_retries"] == 0


def test_the_answer_names_the_pair_that_answered_and_how_long_it_took(monkeypatch):
    monkeypatch.setattr(call, "completion", _recording([], reply("{}")))
    answer = call.text("hello", row=GEMINI).answer
    assert answer.provider_id == "gemini-free"
    assert answer.model == "gemini/gemini-3.1-flash-lite"  # the row's first, none having been named
    assert answer.seconds >= 0
    assert answer.attempts == (("gemini-free", "gemini/gemini-3.1-flash-lite"),)


def test_the_model_the_chain_chose_is_the_one_asked(monkeypatch):
    """A row offers several; the caller says which. Without this the second free-tier bucket is
    listed in the catalogue and never actually reached."""
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply("{}")))
    result = call.text("hello", row=GEMINI, model="gemini/gemini-3.5-flash-lite")
    assert calls[-1]["model"] == "gemini/gemini-3.5-flash-lite"
    assert result.answer.model == "gemini/gemini-3.5-flash-lite"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "audio/wav"),
        (b"ID3\x04\x00", "audio/mpeg"),
        (b"\xff\xfb\x90", "audio/mpeg"),
        (b"OggS\x00", "audio/ogg"),
        (b"nothing recognisable", "application/octet-stream"),
    ],
)
def test_audio_is_labelled_by_what_it_is_rather_than_by_what_was_hoped(data, expected):
    """Gemini answers WAV and Cloudflare's Aura answers MP3, so a hardcoded type is wrong for one
    of them — and a clip stored under the wrong container is a file nothing plays, found much
    later than the call that made it."""
    assert call.audio_mime(data) == expected


def test_a_cost_the_provider_did_not_report_is_none_rather_than_a_failure(monkeypatch):
    """Cost is provenance. `completion_cost()` raises for a model absent from LiteLLM's price
    table — every Cloudflare `@cf/…` id and every local model — and provenance must not be able to
    fail a capture."""
    monkeypatch.setattr(call, "completion", _recording([], reply("{}")))
    assert call.text("hello", row=GEMINI).answer.cost_usd is None


def test_a_reported_cost_is_carried(monkeypatch):
    answered = reply("{}")
    answered._hidden_params = {"response_cost": 0.00042}
    monkeypatch.setattr(call, "completion", _recording([], answered))
    assert call.text("hello", row=GEMINI).answer.cost_usd == pytest.approx(0.00042)


def test_hidden_reasoning_is_the_librarys_problem_and_never_reaches_the_text(monkeypatch):
    """`llm.py` skipped Google's `thought` parts by hand. LiteLLM separates `reasoning_content`
    from `content`, so the hand-written skip is not ported — this asserts we read the right one."""
    answered = reply('{"headword": "el garfio"}')
    answered.choices[0].message.reasoning_content = "deliberation nobody asked for"
    monkeypatch.setattr(call, "completion", _recording([], answered))
    result = call.text("hello", row=GEMINI, as_json=True)
    assert result.parsed == {"headword": "el garfio"}
    assert "deliberation" not in result.text


def test_an_image_comes_back_as_bytes_rather_than_a_url(monkeypatch):
    """One call, not a call and a fetch."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNGDATA").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    result = call.image("a hook", row=SHIPPED.find("openai"), size=(512, 512))
    assert result.data == b"PNGDATA"
    # OpenAI answers with a URL unless told otherwise, so the parameter is sent by default.
    assert calls[-1]["response_format"] == "b64_json"
    assert calls[-1]["size"] == "512x512"


def test_the_requested_size_reaches_a_row_that_says_it_chooses_its_own_resolution(monkeypatch):
    """Vertex takes `size` only as an aspect ratio — the resolution rides in `params.image` — so
    the parameter is still sent and the caller is told the pixels were not honoured."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    result = call.image("a hook", row=SHIPPED.find("vertex"), size=(512, 512))
    assert calls[-1]["size"] == "512x512"
    assert calls[-1]["imageConfig"] == {"imageSize": "1K"}
    assert any("chooses its own resolution" in warning for warning in result.answer.warnings)


def test_a_seed_a_provider_cannot_honour_is_dropped_with_a_warning_rather_than_sent(monkeypatch):
    """The companion of the style rule in `speech`, and it exists because the two ways of getting
    this wrong are both silent: LiteLLM never puts a seed in Vertex's request at all, and turns it
    into an `extra_body` field OpenAI's Images API rejects with a 400. Recording a seed that did
    nothing is worse than recording none — it claims a picture can be reproduced when it cannot."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    result = call.image("a hook", row=SHIPPED.find("vertex"), seed=17)
    assert "seed" not in calls[-1]
    assert any("not reproducible" in warning for warning in result.answer.warnings)


def test_a_seed_reaches_a_row_that_honours_it(monkeypatch):
    monkeypatch.setattr("acervo.models.cloudflare.image",
                        lambda *a, **k: (b"IMG", "image/png"))
    result = call.image("a hook", row=CLOUDFLARE, seed=17)
    assert result.answer.warnings == ()


def test_the_requested_resolution_survives_litellms_vertex_mapping():
    """A contract test against LiteLLM itself, because this failure is invisible at runtime.

    `image_size` is in LiteLLM's supported-parameter list for this model and is dropped anyway: it
    is not in `default_params`, so the non-default pass never sees it, and it *is* in
    `openai_params`, so the provider-specific pass skips it. It falls through both gates and the
    call succeeds at whatever resolution Vertex feels like. `imageConfig` is the one channel that
    survives, and this pins it so a LiteLLM upgrade that changes the mapping fails here rather than
    quietly costing a sweep its resolution.
    """
    from litellm.llms.vertex_ai.image_generation import get_vertex_ai_image_generation_config
    from litellm.utils import get_optional_params_image_gen

    row = SHIPPED.find("vertex")
    model = row.models_for("image")[0].split("/", 1)[1]
    mapped = get_optional_params_image_gen(
        model=model,
        custom_llm_provider="vertex_ai",
        provider_config=get_vertex_ai_image_generation_config(model),
        size="1024x1024",
        **row.params_for("image"),
    )
    assert mapped["imageConfig"] == {"imageSize": "1K"}
    assert mapped["aspectRatio"] == "1:1"


def test_a_row_that_cannot_take_the_response_format_is_not_sent_it(monkeypatch):
    """Vertex refuses the parameter outright — "Setting `response_format` is not supported by
    vertex_ai" — so the row says it cannot take it and the call path has no provider branch."""
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNGDATA").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    call.image("a hook", row=SHIPPED.find("vertex"))
    assert "response_format" not in calls[-1]


def test_a_row_passes_the_arguments_whose_values_live_in_the_environment(monkeypatch):
    """Vertex needs its project as a call argument, not read from the credentials. The row names
    which variable holds it, so this is data rather than an `if provider == "vertex"`."""
    monkeypatch.setenv("ACERVO_VERTEX_PROJECT", "a-project")
    calls = []
    payload = litellm.ImageResponse(data=[{"b64_json": base64.b64encode(b"PNG").decode()}])
    monkeypatch.setattr(call, "image_generation", _recording(calls, payload))
    call.image("a hook", row=SHIPPED.find("vertex"))
    assert calls[-1]["vertex_project"] == "a-project"
    assert calls[-1]["vertex_location"] == "global"


def test_a_row_whose_kind_goes_through_an_adapter_does_not_reach_litellm(monkeypatch):
    """Cloudflare images are the one thing LiteLLM does not cover, and the row says so."""
    monkeypatch.setattr(call, "image_generation", _raising(AssertionError("litellm was called")))
    monkeypatch.setattr("acervo.models.cloudflare.image", lambda *a, **k: (b"IMG", "image/png"))
    result = call.image("a hook", row=CLOUDFLARE)
    assert result.data == b"IMG"
    assert result.answer.provider_id == "cloudflare"
    assert result.answer.model == "@cf/black-forest-labs/flux-2-klein-4b"


def test_a_style_a_provider_cannot_follow_is_dropped_with_a_warning_rather_than_spoken(monkeypatch):
    """An instruction sent to a voice that does not take instructions gets read aloud."""
    monkeypatch.setattr("acervo.models.cloudflare.speech", lambda *a, **k: (b"MP3", "audio/mpeg"))
    result = call.speech("hola", row=CLOUDFLARE, style="cheerful")
    assert result.answer.warnings == ("style is not supported by this provider",)


def test_json_is_only_parsed_when_it_was_asked_for(monkeypatch):
    monkeypatch.setattr(call, "completion", _recording([], reply('{"a": 1}')))
    assert call.text("hello", row=GEMINI).parsed is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("```json\n{}\n```", "{}"),
        ("```\n{}\n```", "{}"),
        ("  {}  ", "{}"),
        ("", ""),
    ],
)
def test_unfenced(raw, expected):
    assert call.unfenced(raw) == expected


def _raising(error):
    def raise_it(**_kwargs):
        raise error

    return raise_it


def _recording(calls, answer):
    def record(**kwargs):
        calls.append(kwargs)
        return answer

    return record


def test_a_declared_schema_is_sent_inside_the_envelope_litellm_reads(monkeypatch):
    """A bare JSON Schema as `response_format` is not a `response_format`, and was dropped whole.

    `response_format` is an envelope with a `type`; a schema handed over as one matches no branch of
    LiteLLM's mapping, so the shape went unstated *and* JSON mode went unrequested — on every row
    declaring `jsonSchema: "native"`. Acervo's own callers never noticed because their prompts also
    describe the shape; the speech adapter's prompts deliberately do not, and every clip translation
    failed. `test_the_envelope_is_the_one_litellm_understands` is the other half of this check.
    """
    calls = []
    monkeypatch.setattr(call, "completion", _recording(calls, reply('{"a": 1}')))
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}

    call.text("hello", row=GEMINI, schema=schema)
    assert calls[-1]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "reply", "schema": schema, "strict": False},
    }

    # `strict` stays false on purpose: OpenAI's strict mode also demands
    # `additionalProperties: false` on every object and every property in `required`, which none of
    # the schemas in this repository satisfy. Tightening them is a separate decision from sending
    # them at all.
    assert calls[-1]["response_format"]["json_schema"]["strict"] is False

    # A row that cannot take one is still sent none — the declaration is what decides, unchanged.
    call.text("hello", row=CLOUDFLARE, schema=schema)
    assert "response_format" not in calls[-1]


def test_the_envelope_is_the_one_litellm_understands():
    """Pinned against LiteLLM itself, because this is where the bug lived and nothing else sees it.

    Every layer above happily carried the old value: it was a valid dict, `completion` accepted it,
    and the only symptom was a model that answered in prose. The assertion has to be made against
    the library's own mapping or it is not made at all.
    """
    from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import VertexGeminiConfig

    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
    envelope = {"type": "json_schema", "json_schema": {"name": "reply", "schema": schema,
                                                       "strict": False}}
    mapped = VertexGeminiConfig().map_openai_params(
        {"response_format": envelope}, {}, "gemini-2.0-flash", False
    )
    assert mapped["response_mime_type"] == "application/json"
    assert mapped["response_json_schema"] == schema

    # What was sent before, for contrast: nothing at all reached the provider.
    assert VertexGeminiConfig().map_openai_params(
        {"response_format": schema}, {}, "gemini-2.0-flash", False
    ) == {}
