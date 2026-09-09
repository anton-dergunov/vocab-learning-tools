"""The two online connectors.

An external entry is render-only: it carries the source's own part of speech as free text in
`posLabel` and never reaches the article parser, which is why what comes back here is the same shape
the offline compiler writes into an artifact.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from acervo.errors import ApiError
from acervo.services.dictionaries.markup import plain_text

USER_AGENT = "Acervo/1.0 (self-hosted vocabulary store; +https://acervo.example.com)"
TIMEOUT_SECONDS = 20

__all__ = ["SOURCES", "fetch_json", "free_dictionary", "plain_text", "wikimedia"]


def fetch_json(url: str) -> Any:
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        raise ApiError(
            502, "dictionary_unreachable", "The dictionary service could not be reached."
        ) from None
    # A 404 is an answer, not a failure: it means the source genuinely has no entry for the word.
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise ApiError(
            502, "dictionary_failed", f"The dictionary service answered with status {response.status_code}."
        )
    try:
        return response.json()
    except ValueError:
        raise ApiError(
            502, "dictionary_unusable", "The dictionary service returned an unreadable answer."
        ) from None


def _trimmed(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _pruned(entry: dict[str, Any]) -> dict[str, Any]:
    """Drop empties, so an online answer is the same shape the compiler writes into an artifact."""
    return {
        key: value
        for key, value in entry.items()
        if value is not None and value != "" and not (isinstance(value, list) and not value)
    }


def free_dictionary(word: str, language: str) -> list[dict[str, Any]]:
    """freedictionaryapi.com.

    Wiktionary-derived but its own field shape: `partOfSpeech`, `pronunciations[].text`, and
    `senses[].definition` as a *string* where wiktextract has a list.
    """
    payload = fetch_json(
        "https://freedictionaryapi.com/api/v1/entries/"
        f"{quote(language or 'en', safe='')}/{quote(word, safe='')}"
    )
    if not payload or not payload.get("entries"):
        return []
    entries = []
    for entry in payload["entries"]:
        senses = []
        for sense in entry.get("senses") or []:
            definition = _trimmed(sense.get("definition"))
            if not definition:
                continue
            mapped: dict[str, Any] = {"definition": definition}
            examples = [_trimmed(text) for text in (sense.get("examples") or []) if _trimmed(text)][:3]
            if examples:
                mapped["examples"] = [{"text": text} for text in examples]
            senses.append(mapped)
        sounds = [sound for sound in (entry.get("pronunciations") or []) if _trimmed(sound.get("text"))]
        mapped_entry = _pruned(
            {
                "headword": _trimmed(payload.get("word")) or word,
                "language": (entry.get("language") or {}).get("code") or language or None,
                "posLabel": _trimmed(entry.get("partOfSpeech")) or None,
                "ipa": _trimmed(sounds[0].get("text")) if sounds else None,
                "senses": senses,
            }
        )
        if mapped_entry.get("senses"):
            entries.append(mapped_entry)
    return entries


def wikimedia(word: str, language: str) -> list[dict[str, Any]]:
    """The Wikimedia REST definition endpoint.

    It lives only on en.wiktionary.org — a per-language host 404s on everything — and keys its answer
    by language *inside* the response. Definitions arrive as HTML fragments carrying wiki-link markup,
    so mapping means stripping it.
    """
    payload = fetch_json(
        f"https://en.wiktionary.org/api/rest_v1/page/definition/{quote(word, safe='')}"
    )
    if not payload:
        return []
    wanted = _trimmed(language)
    codes = [wanted] if wanted and payload.get(wanted) else list(payload.keys())
    entries = []
    for code in codes:
        for group in payload.get(code) or []:
            senses = []
            for item in group.get("definitions") or []:
                definition = plain_text(item.get("definition"))
                if not definition:
                    continue
                sense: dict[str, Any] = {"definition": definition}
                examples = [
                    {
                        "text": plain_text(sample.get("example")),
                        "translation": plain_text(sample.get("translation")) or None,
                    }
                    for sample in (item.get("parsedExamples") or [])
                ]
                examples = [sample for sample in examples if sample["text"]][:3]
                if examples:
                    sense["examples"] = examples
                senses.append(sense)
            if not senses:
                continue
            entries.append(
                _pruned(
                    {
                        "headword": word,
                        "language": code,
                        "posLabel": _trimmed(group.get("partOfSpeech")) or None,
                        "senses": senses,
                    }
                )
            )
    return entries


SOURCES = {"freedictionaryapi": free_dictionary, "wikimedia-rest": wikimedia}
