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
