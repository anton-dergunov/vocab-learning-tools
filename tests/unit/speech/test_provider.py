"""The translation seam: one structured call on the owner's chain, for the corpus to use.

`deploy/acervo/speech/serve.py` is the wiring that knows the retrieval service's prompts, schemas
and exception types, and it lives in the one image where that package is installed. What is under
test here is the half that is Acervo's — and it imports nothing of that service's, which is exactly
why it can be tested from a virtualenv that does not carry FastAPI, uvicorn, yt-dlp or Stanza.
"""

from __future__ import annotations

import pytest

from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable
from acervo.models.results import Answer, TextResult
from acervo.speech.provider import ChainGenerator, GenerationFailed


def answered(payload: str, *, provider: str = "cloudflare", model: str = "second") -> TextResult:
    return TextResult(
        text=payload,
        parsed=None if payload is None else __import__("json").loads(payload),
        answer=Answer(provider_id=provider, model=model, seconds=0.4, cost_usd=None),
    )


@pytest.fixture
def walking(monkeypatch):
    """Stand in for the chain, so this tests the adapter rather than LiteLLM."""
    from acervo.models import chain

    calls: list[dict] = []
    state: dict = {"result": answered('{"target_text": "it itches"}')}

    def walk(kind, chosen, catalogue, ask, stamp):
        calls.append({"kind": kind, "chosen": chosen})
        outcome = state["result"]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(chain, "walk", walk)
    class Candidate:
        named = ("gemini-free", "flash")

    monkeypatch.setattr(
        ChainGenerator, "_candidates", lambda self: state.get("candidates", (Candidate(),))
    )
    return calls, state


# ── the cache key ───────────────────────────────────────────────────────────


def test_it_reports_the_chain_and_never_the_row_that_answered(walking):
    """The service caches on `provider` and `model`, so a fall-through that moved them would miss
    the cache on every retry and re-translate work already paid for. The row that answered travels
    in the metadata instead, where it is provenance rather than a key."""
    generator = ChainGenerator(["gemini-free", "cloudflare"])
    assert (generator.provider, generator.model) == ("acervo-chain", "gemini-free,cloudflare")

    answer = generator.generate(instructions="translate", user_text="Me pica.", schema={})
    assert answer.provider_metadata == {"answered_by": "cloudflare:second"}
    # Asking again after a fall-through must not change the key.
    assert (generator.provider, generator.model) == ("acervo-chain", "gemini-free,cloudflare")


def test_no_chain_is_still_a_stable_key():
    """Absent means "follow the deployment default", which is one order rather than no order."""
    assert ChainGenerator(None).model == "deployment-default"
    assert ChainGenerator([]).model == "deployment-default"


# ── what comes back ─────────────────────────────────────────────────────────


def test_a_parsed_object_comes_back_with_how_long_it_took(walking):
    answer = ChainGenerator(["gemini-free"]).generate(
        instructions="translate", user_text="Me pica.", schema={"type": "object"}
    )
    assert answer.payload == {"target_text": "it itches"}
    assert answer.raw_output == '{"target_text": "it itches"}'
    assert answer.latency_ms >= 0


def test_a_reply_that_is_not_an_object_is_retryable_and_carries_the_raw_output(walking):
    """The service has an invalid-output path that re-asks, and it wants the text to log."""
    _calls, state = walking
    state["result"] = TextResult(text="not json at all", parsed=None,
                                 answer=Answer("gemini-free", "flash", 0.1, None))

    with pytest.raises(GenerationFailed) as raised:
        ChainGenerator(["gemini-free"]).generate(instructions="t", user_text="x", schema={})
    assert raised.value.code == "invalid_output"
    assert raised.value.retryable is True
    assert raised.value.raw == "not json at all"


# ── how failure is classified ───────────────────────────────────────────────


@pytest.mark.parametrize("reason, code, retryable", [
    ("rate_limited", "rate_limited", True),
    ("unavailable", "temporarily_unavailable", True),
    ("unreachable", "temporarily_unavailable", True),
    ("authentication", "provider_unavailable", False),
    ("configuration", "provider_unavailable", False),
    ("refused", "provider_unavailable", False),
])
def test_each_reason_maps_to_what_the_service_acts_on(walking, reason, code, retryable):
    """The service draws one distinction — wait or do not — and it is the same one `acervo.models`
    already draws: a provider that is busy says nothing about the request, while a rejected
    credential is a mistake to fix rather than a condition to route around."""
    _calls, state = walking
    failure = (ProviderUnavailable if retryable else ProviderRefused)(reason, "detail")
    state["result"] = ChainExhausted(attempts=(("gemini-free", "flash"),), last=failure)

    with pytest.raises(GenerationFailed) as raised:
        ChainGenerator(["gemini-free"]).generate(instructions="t", user_text="x", schema={})
    assert (raised.value.code, raised.value.retryable) == (code, retryable)


def test_a_chain_with_no_credentials_refuses_rather_than_waiting(walking):
    """Nothing to wait for. Retrying this every time a clip opens would be a busy loop."""
    _calls, state = walking
    state["candidates"] = ()

    with pytest.raises(GenerationFailed) as raised:
        ChainGenerator(["gemini-free"]).generate(instructions="t", user_text="x", schema={})
    assert raised.value.retryable is False


def test_the_chain_is_given_rather_than_looked_up(walking):
    """This runs in the speech container, which has no business reaching Acervo's database — the
    rule already stated for any work that cannot import `repository/`."""
    import acervo.speech.provider as module

    source = (module.__file__ or "")
    assert "acervo.repository" not in open(source, encoding="utf-8").read()
    assert "acervo.settings" not in open(source, encoding="utf-8").read()


# ── the shape of the answer, said twice ─────────────────────────────────────


def test_googles_type_spelling_is_renamed_into_json_schemas():
    """The retrieval service's schemas are written in Google's GenAI dialect, which spells the type
    keywords in capitals. `acervo.models` speaks JSON Schema. Nothing else about the two differs for
    these shapes, so this is a rename — and it is applied unconditionally because it is a no-op on a
    schema that was already JSON Schema."""
    from acervo.speech.provider import json_schema

    assert json_schema({
        "type": "OBJECT",
        "properties": {
            "alignments": {
                "type": "ARRAY",
                "minItems": 2,
                "items": {
                    "type": "OBJECT",
                    "properties": {"source_id": {"type": "STRING", "enum": ["S1", "S2"]}},
                    "required": ["source_id"],
                },
            },
        },
        "required": ["alignments"],
    }) == {
        "type": "object",
        "properties": {
            "alignments": {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    # An enum's *values* are data, not type keywords, and are left alone.
                    "properties": {"source_id": {"type": "string", "enum": ["S1", "S2"]}},
                    "required": ["source_id"],
                },
            },
        },
        "required": ["alignments"],
    }

    # Already JSON Schema, including a union, and unchanged.
    already = {"type": "object", "properties": {"segmentId": {"type": ["string", "null"]}}}
    assert json_schema(already) == already


def _asking(monkeypatch):
    """A chain that actually calls the ask, so what reaches `call.text` can be read."""
    from acervo.models import call, chain

    seen: list[dict] = []

    def text(prompt, **kwargs):
        seen.append({"prompt": prompt, **kwargs})
        return answered('{"target_text": "it itches"}')

    monkeypatch.setattr(call, "text", text)
    monkeypatch.setattr(chain, "walk", lambda kind, chosen, catalogue, ask, stamp: ask(Asked()))

    class Asked:
        row = object()
        model = "flash"
        named = ("gemini-free", "flash")

    monkeypatch.setattr(ChainGenerator, "_candidates", lambda self: (Asked(),))
    return seen


def test_no_schema_is_sent_at_all(monkeypatch):
    """Constrained decoding is not used here, or anywhere — AGENTS.md says why, and the alignment
    measurement behind it is the strongest case that was tried and still lost."""
    seen = _asking(monkeypatch)
    ChainGenerator(None).generate(
        instructions="Translate it.", user_text="me pica",
        schema={"type": "OBJECT", "properties": {"target_text": {"type": "STRING"}}},
    )
    assert "schema" not in seen[-1]
    assert seen[-1]["as_json"] is True


def test_the_shape_is_also_stated_in_the_instructions(monkeypatch):
    """Not belt-and-braces: with no schema sent anywhere, it is the only statement of the shape.

    The retrieval service's two prompts name no field at all — they end with "Return only the
    requested structured result" and leave the shape entirely to the schema, which is how its own
    Gemini adapter works. A row declaring `prompt` is sent no schema by design, so cloudflare and
    openrouter could never answer either stage without this line. It is in JSON Schema's spelling
    too, so the instruction and the wire say the same thing.
    """
    seen = _asking(monkeypatch)
    ChainGenerator(None).generate(
        instructions="Translate it.", user_text="me pica",
        schema={"type": "OBJECT", "properties": {"target_text": {"type": "STRING"}}},
    )
    system = seen[-1]["system"]
    assert system.startswith("Translate it.")
    assert '"type": "object"' in system
    assert "target_text" in system
    assert "OBJECT" not in system
