"""The locked fall-through rule, and the provenance that goes with it.

Two of these assert a *call count* rather than an exception. That is deliberate: "never fallen
through" is a claim about what did not happen, and an exception type alone cannot tell the
difference between a row that was skipped and a row that was tried and refused.
"""

from __future__ import annotations

import pytest

from acervo.models import call, chain
from acervo.models.catalogue import load_catalogue
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable
from acervo.models.results import Answer, TextResult

SHIPPED = load_catalogue()


@pytest.fixture(autouse=True)
def three_credentialed_rows(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a-gemini-key")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "a-cloudflare-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("OPENAI_API_KEY", "an-openai-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ACERVO_OLLAMA_URL", raising=False)
    monkeypatch.delenv("ACERVO_VERTEX_PROJECT", raising=False)


def answers(row):
    return TextResult(
        text="{}", parsed={}, answer=Answer(row.id, row.model_for("text"), 0.1, None, (), (row.id,))
    )


def refusing(*errors):
    """A script of one outcome per row, and a record of which rows were reached."""
    tried: list[str] = []
    script = list(errors)

    def ask(row):
        tried.append(row.id)
        outcome = script.pop(0) if script else None
        if isinstance(outcome, BaseException):
            raise outcome
        return answers(row)

    return ask, tried


def unavailable(reason="rate_limited"):
    return ProviderUnavailable(reason, "429 from the provider", provider_id="x", status=429)


def refused(reason="authentication"):
    return ProviderRefused(reason, "the credential was rejected", provider_id="x", status=401)


def test_a_rate_limited_row_falls_through_and_the_next_one_answers():
    ask, tried = refusing(unavailable())
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert tried == ["gemini-free", "cloudflare"]
    assert result.answer.provider_id == "cloudflare"
    assert result.answer.attempts == ("gemini-free", "cloudflare")


def test_the_answer_names_the_row_that_answered_and_not_the_one_that_was_asked_first():
    """The locked provenance contract: a fall-through that leaves `modelId` naming the first
    choice is a bug, so `modelId` is read from here rather than from the configuration."""
    ask, _tried = refusing(unavailable(), unavailable())
    result = chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert result.answer.provider_id == "openai"
    assert result.answer.model == "openai/gpt-5.1"


def test_an_authentication_failure_stops_the_chain_and_the_second_row_is_never_called():
    """A mistake to fix, not a condition to route around. The call count is the assertion."""
    ask, tried = refusing(refused())
    with pytest.raises(ProviderRefused):
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert tried == ["gemini-free"]


@pytest.mark.parametrize("reason", ["authentication", "configuration", "refused", "unconfigured"])
def test_no_terminal_reason_is_ever_routed_around(reason):
    ask, tried = refusing(refused(reason))
    with pytest.raises(ProviderRefused):
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert len(tried) == 1


@pytest.mark.parametrize("reason", ["rate_limited", "unavailable", "unreachable"])
def test_every_retryable_reason_moves_to_the_next_row(reason):
    ask, tried = refusing(unavailable(reason))
    chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert tried == ["gemini-free", "cloudflare"]


def test_every_row_unavailable_raises_chain_exhausted_carrying_the_last_error():
    """The last one is the actionable one, and it is what keeps the retry contract: a chain whose
    final row was rate limited must still be reported as rate limiting."""
    ask, tried = refusing(unavailable("unavailable"), unavailable("unreachable"), unavailable("rate_limited"))
    with pytest.raises(ChainExhausted) as caught:
        chain.walk("text", None, SHIPPED, ask, chain.stamped)
    assert caught.value.attempts == ("gemini-free", "cloudflare", "openai")
    assert caught.value.last.reason == "rate_limited"
    assert tried == ["gemini-free", "cloudflare", "openai"]


def test_an_unset_chain_is_every_credentialed_row_in_catalogue_order():
    assert [row.id for row in chain.resolve("text", None, SHIPPED)] == [
        "gemini-free",
        "cloudflare",
        "openai",
    ]


def test_a_row_without_credentials_is_left_out_rather_than_tried(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert [row.id for row in chain.resolve("text", None, SHIPPED)] == ["cloudflare", "openai"]
    assert [row.id for row in chain.resolve("text", ["gemini-free", "openai"], SHIPPED)] == ["openai"]


def test_a_stated_chain_is_asked_in_the_order_it_states():
    ask, tried = refusing(unavailable())
    chain.walk("text", ["openai", "cloudflare"], SHIPPED, ask, chain.stamped)
    assert tried == ["openai", "cloudflare"]


def test_an_unknown_provider_id_is_a_mistake_to_fix_rather_than_a_row_to_skip():
    with pytest.raises(ProviderRefused, match="nonesuch"):
        chain.resolve("text", ["nonesuch"], SHIPPED)


def test_a_row_asked_for_a_kind_it_does_not_serve_is_refused():
    with pytest.raises(ProviderRefused, match="does not serve image"):
        chain.resolve("image", ["openrouter"], SHIPPED)


def test_nothing_credentialed_names_the_first_unmet_requirement(monkeypatch):
    """What `GET /health` shows, and it must be a variable name rather than a value."""
    for name in ("GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(name)
    with pytest.raises(ProviderRefused) as caught:
        chain.walk("text", None, SHIPPED, lambda row: pytest.fail("called"), chain.stamped)
    assert caught.value.reason == "unconfigured"
    assert caught.value.detail == "GEMINI_API_KEY is not set"


def test_a_stated_chain_with_no_credentials_reports_that_chains_own_first_requirement(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    with pytest.raises(ProviderRefused) as caught:
        chain.walk("text", ["cloudflare"], SHIPPED, lambda row: pytest.fail("called"), chain.stamped)
    assert caught.value.detail == "CLOUDFLARE_API_TOKEN is not set"


def test_the_walk_calls_the_real_text_function_through_one_seam(monkeypatch):
    """The chain and the call fit together: this is the only test that runs both."""
    seen: list[str] = []

    def completion(**kwargs):
        seen.append(kwargs["model"])
        if len(seen) == 1:
            raise __import__("litellm").RateLimitError(message="429", llm_provider="p", model="m")
        return __import__("litellm").ModelResponse(
            model=kwargs["model"],
            choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}],
        )

    monkeypatch.setattr(call, "completion", completion)
    result = chain.walk(
        "text", None, SHIPPED, lambda row: call.text("hello", row=row, as_json=True), chain.stamped
    )
    assert seen == ["gemini/gemini-3.1-flash-lite", "cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast"]
    assert result.answer.provider_id == "cloudflare"
    assert result.answer.attempts == ("gemini-free", "cloudflare")
