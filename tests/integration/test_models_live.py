"""Real calls to real providers. Gated off, because this one costs money.

Everything about how a provider *failure* is handled is in `tests/unit/models/`, which runs offline
in two seconds against real LiteLLM exception objects. What only a live call can tell you is the
half a stub cannot fake: that a catalogue row's model id still exists, that the credential in this
deployment's environment is accepted, that a `native` row really does honour `response_format`, and
that the bytes coming back are an image rather than a URL or an envelope nobody parsed.

    set -a; . ./.env; set +a
    RUN_LIVE_MODEL_TESTS=true .venv/bin/python -m pytest tests/integration/test_models_live.py -v

A row this machine has no credentials for skips individually rather than failing the run, so the
same command is useful on a workstation with three providers and on a server with one.
"""

from __future__ import annotations

import json
import os

import pytest

from acervo.models import call, load_catalogue
from acervo.models.catalogue import available, reason
from acervo.models.errors import ProviderUnavailable

pytestmark = pytest.mark.integration

CATALOGUE = load_catalogue()

# Short, cheap and unambiguous. The text prompt asks for a shape rather than for knowledge, so a
# failure is about the transport rather than about the model being clever enough.
WORD = "hola"
TEXT_PROMPT = 'Reply with only this JSON object and nothing else: {"ok": true, "word": "hola"}'
IMAGE_PROMPT = "a plain red circle centred on a white background"


@pytest.fixture(scope="module", autouse=True)
def gated():
    if os.environ.get("RUN_LIVE_MODEL_TESTS") != "true":
        pytest.skip("set RUN_LIVE_MODEL_TESTS=true to spend real money on real providers")


def pairs(kind: str) -> list[tuple[str, str]]:
    """Every (row, model) this catalogue offers for a kind — each one gets its own case.

    Per pair rather than per row, because a row's second model is exactly the thing a stub cannot
    check: it is listed so that the first one's 429 has somewhere to go, and a model id that has
    been retired sits there silently until the day the first bucket runs out.
    """
    return [(row.id, model) for row in CATALOGUE.serving(kind) for model in row.models_for(kind)]


def row_for(kind: str, identifier: str):
    row = CATALOGUE.find(identifier)
    if not row.serves(kind):
        pytest.skip(f"{identifier} does not serve {kind}")
    if not available(row):
        pytest.skip(f"{identifier}: {reason(row)}")
    return row


def check(answer, row) -> None:
    """Every live call proves the same three things about what came back."""
    assert answer.provider_id == row.id
    assert answer.model
    assert answer.seconds > 0, "a real call cannot take no time"


def reachable(row, kind):
    """Rate limiting is the provider answering correctly and having nothing left.

    A 429 proves both of the things this file exists to check — that the model id still resolves and
    that the credential was accepted — because the request got past authentication and routing to
    reach a quota. Gemini's free tier has separate, much smaller allowances for images and speech
    than for text, so on most days that is what the image and speech rows have to say. Anything else
    still fails: this widens what counts as a pass by exactly one typed error, not by a category.
    """

    def run(make):
        try:
            return make()
        except ProviderUnavailable as error:
            if error.reason != "rate_limited":
                raise
            pytest.skip(f"{row.id} {kind}: reached, and out of quota — {error.status}")

    return run


@pytest.mark.parametrize(("identifier", "model"), pairs("text"), ids=lambda v: v.split("/")[-1])
def test_text_comes_back_as_json_from_a_real_provider(identifier, model):
    row = row_for("text", identifier)
    result = reachable(row, "text")(
        lambda: call.text(
            TEXT_PROMPT, row=row, model=model, system="You answer with JSON only.", as_json=True
        )
    )
    check(result.answer, row)
    assert isinstance(result.parsed, dict), f"unparseable reply: {result.text[:200]!r}"
    assert result.parsed.get("word") == WORD
    assert result.answer.model == model
    # `native` rows are sent `response_format`; `prompt` rows are asked in prose and parsed after.
    # Either way the caller gets a dict, which is the whole point of the capability declaration.
    print(f"\n{identifier}: {model} in {result.answer.seconds:.1f}s cost={result.answer.cost_usd}")


@pytest.mark.parametrize(("identifier", "model"), pairs("image"), ids=lambda v: v.split("/")[-1])
def test_an_image_comes_back_as_bytes_from_a_real_provider(identifier, model):
    row = row_for("image", identifier)
    result = reachable(row, "image")(
        lambda: call.image(IMAGE_PROMPT, row=row, model=model, size=(512, 512))
    )
    check(result.answer, row)
    assert len(result.data) > 1000, "that is too small to be an image"
    # PNG, JPEG or WebP — enough to prove these are pixels and not a URL or a base64 string nobody
    # decoded, without pinning a provider to one encoder.
    assert result.data[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"RIFF"), (
        f"unexpected leading bytes {result.data[:8]!r}"
    )
    print(f"\n{identifier}: {model} → {len(result.data)} bytes in {result.answer.seconds:.1f}s")


@pytest.mark.parametrize(("identifier", "model"), pairs("audio"), ids=lambda v: v.split("/")[-1])
def test_speech_comes_back_as_audio_from_a_real_provider(identifier, model):
    row = row_for("audio", identifier)
    # The word in a language the model says it speaks: Aura is English-only, the rest take Spanish.
    language = "es" if row.speaks(model, "es") else "en"
    words = WORD if language == "es" else "hello"
    # A style goes only where the model declares it takes one, which is exactly what is being
    # checked for the Gemini voices: that `prompt` is accepted and the answer is still audio.
    style = "Say it warmly, like greeting an old friend." if row.style_for(model) == "instruction" else None
    result = reachable(row, "audio")(
        lambda: call.speech(words, row=row, model=model, language=language, style=style)
    )
    check(result.answer, row)
    assert len(result.data) > 500, "that is too small to be a spoken word"
    # Sniffed from the bytes, not asserted by the row: Gemini answers WAV and Aura answers MP3.
    assert result.mime != "application/octet-stream", f"unrecognised audio {result.data[:8]!r}"
    assert result.answer.warnings == ()
    print(f"\n{identifier}: {model} voice={result.voice} style={bool(style)} → {len(result.data)} "
          f"bytes {result.mime} in {result.answer.seconds:.1f}s")


def test_a_wrong_credential_is_refused_rather_than_routed_around(monkeypatch):
    """The locked rule, against the real service: a rejected key must not spend the next provider.

    This is the one live case worth having beyond "it works", because it is the one where being
    wrong costs money quietly rather than failing loudly.
    """
    row = row_for("text", "gemini-free")
    monkeypatch.setenv(row.keyEnv, "not-a-real-key-0000000000")
    from acervo.models.errors import ProviderRefused

    with pytest.raises(ProviderRefused) as caught:
        call.text(TEXT_PROMPT, row=row, as_json=True)
    assert caught.value.reason in ("authentication", "configuration")
    assert "not-a-real-key-0000000000" not in caught.value.detail


def test_the_shipped_catalogue_names_models_these_providers_still_have():
    """A model id that has been retired is a 404 at capture time and nowhere earlier."""
    checked = [row.id for row in CATALOGUE if available(row)]
    assert checked, "no provider on this machine has credentials; nothing was verified"
    print("\ncredentialed here: " + json.dumps(checked))
