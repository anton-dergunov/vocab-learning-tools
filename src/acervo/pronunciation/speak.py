"""Saying one piece of text, over a chain of speech models, in its own language.

Two decisions live here and nowhere else.

**Only a model that speaks the language is asked.** The catalogue says which languages each model
covers — Aura is English, Google's WaveNet voices exist per language, Gemini's speak anything — and a
pair that cannot say Russian is left out of the walk for Russian rather than asked and refused. When
nothing in the chain can, that is its own answer (`NoVoice`), because "your chain has no Russian
voice" is something the owner can fix and a refusal from the first provider would hide it.

**A direction reaches only a voice that can follow one.** The emotion is sent where the answering
model declares `style: instruction`, and the result says whether it was, so the stored clip records
the delivery it actually got rather than the one that was hoped for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from acervo.models import chain
from acervo.models import call as provider
from acervo.models.catalogue import Catalogue
from acervo.models.errors import ProviderUnavailable
from acervo.models.results import AudioResult

# Only what a direction needs in order to read naturally ("Say this Spanish sentence…"). An unknown
# tag is used as it is; a voice that takes directions understands `pt-BR` perfectly well.
LANGUAGE_NAMES = {
    "es": "Spanish", "en": "English", "ru": "Russian", "zh": "Mandarin Chinese", "pt": "Portuguese",
    "fr": "French", "de": "German", "it": "Italian", "ja": "Japanese", "ko": "Korean",
}

CALLERS = {"plain": "pronounce-word", "expressive": "pronounce-sentence", "selection": "pronounce-selection"}


class NoVoice(Exception):
    """Nothing in the chain speaks this language."""

    def __init__(self, language: str) -> None:
        super().__init__(language)
        self.language = language


@dataclass(frozen=True)
class Spoken:
    result: AudioResult
    # The direction actually sent, or None when there was none or the voice could not take it.
    direction: str | None


def language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language.split("-")[0].lower(), language)


def direction(template: str, emotion: str, language: str) -> str:
    """The template with its two blanks filled. `replace` rather than `format`: an emotion is free text."""
    return template.strip().replace("{language}", language_name(language)).replace("{emotion}", emotion)


def speakers(chosen: Sequence[chain.Choice] | None, catalogue: Catalogue, language: str) -> tuple[chain.Candidate, ...]:
    """The pairs in this chain that can say something in `language`, in order."""
    return tuple(
        candidate for candidate in chain.resolve("audio", chosen, catalogue)
        if candidate.row.speaks(candidate.model, language)
    )


def speak(
    text: str,
    language: str,
    *,
    chosen: Sequence[chain.Choice] | None,
    catalogue: Catalogue,
    style: str | None = None,
    voice: Callable[[str, str, str], str | None] = lambda provider_id, model, language: None,
    caller: str = "pronounce-word",
    hedge_after: float | None = None,
) -> Spoken:
    """Say `text`, falling through the chain on the usual retryable failures.

    `voice(provider, model, language)` is the owner's choice for a pair, and a name the model does not
    declare for that language is ignored rather than sent — a voice picked for WaveNet must not reach
    Gemini, which would refuse it.
    """
    everyone = chain.resolve("audio", chosen, catalogue)
    if not everyone:
        raise chain.unconfigured("audio", chosen, catalogue)
    able = [candidate for candidate in everyone if candidate.row.speaks(candidate.model, language)]
    if not able:
        raise NoVoice(language)

    def ask(candidate: chain.Candidate) -> AudioResult:
        row, model = candidate.row, candidate.model
        offered = row.voices_for(model, language)
        preferred = voice(row.id, model, language)
        result = provider.speech(
            text, row=row, model=model, language=language,
            voice=preferred if preferred and (not offered or preferred in offered) else None,
            style=style if style and row.style_for(model) == "instruction" else None,
        )
        if not result.data:
            raise ProviderUnavailable("empty", "the model returned no audio", provider_id=row.id, model=model)
        return result

    result: AudioResult = chain.walk(
        "audio", [candidate.named for candidate in able], catalogue, ask, chain.stamped,
        caller=caller, hedge_after=hedge_after,
    )
    answered = catalogue.find(result.answer.provider_id)
    sent = style if style and answered.style_for(result.answer.model) == "instruction" else None
    return Spoken(result=result, direction=sent)


EXTENSIONS = {"audio/mpeg": "mp3", "audio/wav": "wav", "audio/ogg": "ogg", "audio/flac": "flac"}


def extension_for(mime: str) -> str:
    return EXTENSIONS.get(mime, "bin")
