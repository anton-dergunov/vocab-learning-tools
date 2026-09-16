"""Acervo's binding to pronunciation: the graph and settings in, a clip on disk and a row out.

The other half of the split `acervo.pronunciation` makes, exactly as `services/images.py` is for
pictures. That package knows what to say and how to ask for it; this module knows whose word it is,
which chain reads it, where the file goes and what Acervo's API calls a failure.

**A clip is written by the server, file and row together**, for the reason a picture is: nobody else
holds both. The file lands first, under a name that changes with every recording, and the row second
through `graph.merge_graph` — the same write every phone makes. So a device that cached the previous
recording by its reference simply misses the new one and fetches it, and the previous file is removed
only once the row naming its successor has landed.

Every operation is read (transaction) → model call (**no** transaction) → write (transaction).

A selection is the one thing said and not kept: it names no record, so there is no row to put it in
and nothing to make stale. It is spoken and returned, and the call log is its only trace.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from acervo.domain.ids import is_language, now_instant
from acervo.errors import ApiError
from acervo.models import ChainExhausted, ProviderError, journal, load_catalogue
from acervo.models.call import audio_mime
from acervo.models.catalogue import available
from acervo.pronunciation import encode, speak as speaking
from acervo.pronunciation.ids import pronunciation_id
from acervo.pronunciation.targets import COLLECTION, Target, current, target_in
from acervo.repository import graph, pronunciation_settings
from acervo.repository.pronunciation_settings import PREGENERATED
from acervo.services.models import chain_for, refusal
from acervo.services.prompts import prompt_text
from acervo.settings import Settings

STYLE_PROMPT = "acervo_pronounce_style"

# Route segment → target kind. The route is addressed by the record being read.
ROUTE_KINDS = {plural: kind for kind, plural in COLLECTION.items()}

CHAINS = {"plain": "audioPlain", "expressive": "audioExpressive"}

# How long a pair may stay silent before the next is asked beside it. Measured on 2026-09-15 against
# Cloud TTS: WaveNet and Standard answered a word in 0.3–1.2 s, a Gemini voice a sentence in 2–3 s.
# Somebody pressed a button and is waiting, so both are set just above the healthy tail.
HEDGE = {"plain": 3.0, "expressive": 8.0}

# A selection is read aloud from the page, not stored; this bounds what one press can cost.
UTTERANCE_LIMIT = 2000
CLIP_LIMIT = 4 * 1024 * 1024


# ── settings ────────────────────────────────────────────────────────────────


def settings_view(settings: Settings, owner: str) -> dict[str, Any]:
    """What the owner chose, and the voices each model in each order offers per vocabulary language.

    The voice lists travel with the settings for `images.settings_view`'s reason: the selects are
    meaningless without them, and one round trip cannot show a half-loaded screen.
    """
    catalogue = load_catalogue()
    chosen = pronunciation_settings.settings(owner)
    languages = [vocabulary["language"] for vocabulary in graph.owner_vocabularies(owner)]
    orders: dict[str, list[dict[str, Any]]] = {}
    for reading, chain_name in CHAINS.items():
        entries = []
        for candidate in _pairs(settings, owner, chain_name, catalogue):
            row, model = candidate
            entries.append({
                "provider": row.id,
                "providerLabel": row.label,
                "model": model,
                "available": available(row),
                "style": row.style_for(model),
                "voices": {
                    language: list(row.voices_for(model, language))
                    for language in languages if row.speaks(model, language)
                },
            })
        orders[reading] = entries
    return {**chosen, "languages": languages, "orders": orders}


def _pairs(settings: Settings, owner: str, chain_name: str, catalogue) -> list[tuple[Any, str]]:
    """Every pair in an order, credentialed or not, so a voice can be chosen before a key is set."""
    found = []
    for choice in chain_for(settings, owner, chain_name) or [
        (row.id, model) for row in catalogue.serving("audio") for model in row.models_for("audio")
    ]:
        identifier, model = (choice, None) if isinstance(choice, str) else choice
        try:
            row = catalogue.find(identifier)
        except KeyError:
            continue
        if not row.serves("audio"):
            continue
        for one in ([model] if model else row.models_for("audio")):
            if one in row.models_for("audio"):
                found.append((row, one))
    return found


def apply_settings(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validate a submitted document, store it, and answer with the whole readout."""
    changes: dict[str, Any] = {}
    if "pregenerate" in body:
        submitted = body["pregenerate"]
        if not isinstance(submitted, dict) or any(
            name not in PREGENERATED or not isinstance(value, bool) for name, value in submitted.items()
        ):
            raise ApiError(
                400, "invalid_input",
                f"Recording in advance takes true or false for {', '.join(PREGENERATED)}.",
            )
        changes["pregenerate"] = submitted
    if "expressive" in body:
        if not isinstance(body["expressive"], bool):
            raise ApiError(400, "invalid_input", "expressive must be true or false.")
        changes["expressive"] = body["expressive"]
    if "voices" in body:
        changes["voices"] = _voices(body["voices"])
    pronunciation_settings.save(owner, **changes)
    return settings_view(settings, owner)


def _voices(submitted: Any) -> dict[str, dict[str, dict[str, str]]]:
    """A voice document held to the catalogue: every provider, model and voice must exist."""
    if not isinstance(submitted, dict):
        raise ApiError(400, "invalid_input", "Voices must be {provider: {model: {language: voice}}}.")
    catalogue = load_catalogue()
    kept: dict[str, dict[str, dict[str, str]]] = {}
    for provider_id, models in submitted.items():
        try:
            row = catalogue.find(str(provider_id))
        except KeyError:
            raise ApiError(400, "unknown_provider", f"This server has no provider called {provider_id}.") from None
        if not row.serves("audio") or not isinstance(models, dict):
            raise ApiError(400, "unsupported_kind", f"{row.label} does not speak.")
        for model, languages in models.items():
            if model not in row.models_for("audio") or not isinstance(languages, dict):
                raise ApiError(400, "unknown_model", f"{row.label} does not offer {model} for speech.")
            for language, voice in languages.items():
                if voice in (None, ""):
                    continue
                offered = row.voices_for(model, str(language))
                if not is_language(str(language)) or (offered and voice not in offered):
                    raise ApiError(400, "unknown_voice", f"{model} has no voice {voice!r} for {language}.")
                kept.setdefault(row.id, {}).setdefault(model, {})[str(language)] = str(voice)
    return kept


# ── saying a record ─────────────────────────────────────────────────────────


def pronounce(settings: Settings, owner: str, device: str, route_kind: str, target_id: str,
              again: bool = False) -> dict[str, Any]:
    """The clip for one spoken field: the stored one while it is current, otherwise a new recording.

    `again` records it anew even when the stored clip is current — "Record again" after hearing a bad
    one. The row is rewritten at its derived id, so there is still exactly one clip per field.
    """
    started = time.monotonic()
    target, records = _target(owner, route_kind, target_id)
    clip_id = pronunciation_id(target.kind, target.id)
    existing = next((row for row in records.get("pronunciations", []) if row["id"] == clip_id), None)
    caller = speaking.CALLERS[target.reading]
    log = _logger(caller, target)

    if not again and current(existing, target):
        log(started, source="reused", clip=existing, result="stored")
        return existing  # type: ignore[return-value]
    source = "again" if again else ("stale" if existing and not existing.get("deleted") else "generated")

    preferences = pronunciation_settings.settings(owner)
    style = None
    if target.kind == "example" and target.emotion and preferences.expressive:
        style = speaking.direction(
            prompt_text(Path(settings.prompts_path), STYLE_PROMPT), target.emotion, target.language
        )
    spoken = _speak(
        settings, owner, target.text, target.language, target.reading, style, caller,
        lambda error: log(started, source=source, result=error, failed=True),
    )
    result = spoken.result
    # The provider answered with a master; what is kept is Opus. An answer that was already
    # compressed passes through untouched — see `pronunciation/encode.py`.
    kept, mime = encode.compact(result.data, result.mime)
    return _store(
        settings, owner, device, target, existing, clip_id, kept, mime,
        provider_id=result.answer.provider_id, model_id=result.answer.model, voice=result.voice,
        emotion=target.emotion if spoken.direction else None,
        on_logged=lambda clip, outcome: log(
            started, source=source, clip=clip, result=outcome, failed=outcome != "stored",
            bytes=len(kept), answered=f"{result.mime}:{len(result.data)}",
            attempts=len(result.answer.attempts), passed_over=_passed(result.answer),
            warnings="; ".join(result.answer.warnings), style="yes" if spoken.direction else ("dropped" if style else "no"),
        ),
    )


def restore(settings: Settings, owner: str, device: str, route_kind: str, target_id: str,
            data: bytes, spoken: dict[str, str]) -> dict[str, Any]:
    """Put back a clip an export carried, keeping who recorded it.

    Refused when the record no longer says what the clip says: a bundle's clip of a sentence that has
    since been edited is a recording of something else, and storing it would present it as current.
    """
    started = time.monotonic()
    target, records = _target(owner, route_kind, target_id)
    log = _logger("pronounce-restore", target)
    if spoken.get("text") != target.text:
        log(started, source="restored", result="stale", failed=True)
        raise ApiError(409, "stale_clip", "That recording is of different words than the record now holds.")
    mime = audio_mime(data)
    if mime == "application/octet-stream":
        raise ApiError(400, "unreadable_audio", "That file could not be read as audio.")
    provider_id, model_id = spoken.get("providerId", "").strip(), spoken.get("modelId", "").strip()
    if not provider_id or not model_id:
        raise ApiError(400, "invalid_input", "A restored clip must name the provider and model that recorded it.")
    clip_id = pronunciation_id(target.kind, target.id)
    existing = next((row for row in records.get("pronunciations", []) if row["id"] == clip_id), None)
    return _store(
        settings, owner, device, target, existing, clip_id, data, mime,
        provider_id=provider_id[:80], model_id=model_id[:240], voice=(spoken.get("voice") or None),
        emotion=(spoken.get("emotion") or None),
        on_logged=lambda clip, outcome: log(started, source="restored", clip=clip, result=outcome,
                                            failed=outcome != "stored"),
    )


def utterance(settings: Settings, owner: str, text: str, language: str) -> tuple[bytes, str, dict[str, str]]:
    """Say a selection. Nothing is stored; the answer is the audio and who said it."""
    started = time.monotonic()
    words = (text or "").strip()
    if not words or len(words) > UTTERANCE_LIMIT:
        raise ApiError(400, "invalid_input", f"Select between 1 and {UTTERANCE_LIMIT} characters to listen to.")
    if not is_language(language or ""):
        raise ApiError(400, "invalid_input", "language must be a BCP-47 language tag.")

    def failed(error: str) -> None:
        journal.outcome("pronounce-selection", True, lang=language, chars=len(words), text=words,
                        result=error, seconds=time.monotonic() - started)

    spoken = _speak(settings, owner, words, language, "plain", None, "pronounce-selection", failed)
    # Compressed like a stored clip, though nothing is stored: this one is downloaded before it can
    # be heard, and a master is four times the wait on a phone for audio that lives one playback.
    result = spoken.result
    audio, mime = encode.compact(result.data, result.mime)
    journal.outcome(
        "pronounce-selection", lang=language, chars=len(words), text=words,
        pair=f"{result.answer.provider_id}:{result.answer.model}", voice=result.voice,
        bytes=len(audio), answered=f"{result.mime}:{len(result.data)}", mime=mime, result="spoken",
        seconds=time.monotonic() - started,
    )
    return audio, mime, {
        "provider": result.answer.provider_id, "model": result.answer.model, "voice": result.voice or "",
    }


# ── shared ──────────────────────────────────────────────────────────────────


def _target(owner: str, route_kind: str, target_id: str) -> tuple[Target, dict[str, list[dict]]]:
    kind = ROUTE_KINDS.get(route_kind)
    lexeme_id = graph.lexeme_of(owner, kind, target_id) if kind else None
    records = graph.article_records(owner, lexeme_id) if lexeme_id else {}
    target = target_in(records, kind, target_id) if kind and lexeme_id else None
    if target is None:
        # One message for "no such record", "somebody else's" and "deleted", as everywhere else.
        raise ApiError(404, "not_found", "There is nothing there to pronounce.")
    return target, records


def _speak(settings: Settings, owner: str, text: str, language: str, reading: str,
           style: str | None, caller: str, on_failure) -> speaking.Spoken:
    preferences = pronunciation_settings.settings(owner)
    chain_name = CHAINS[reading]
    try:
        return speaking.speak(
            text, language,
            chosen=chain_for(settings, owner, chain_name), catalogue=load_catalogue(),
            style=style, voice=preferences.voice, caller=caller, hedge_after=HEDGE[reading],
        )
    except speaking.NoVoice:
        on_failure("no_model_for_language")
        raise ApiError(
            422, "no_voice_for_language",
            f"Nothing in your pronunciation order speaks {speaking.language_name(language)}. "
            "Add a model that does in Settings ▸ Providers.",
        ) from None
    except ChainExhausted as exhausted:
        error = refusal(exhausted.last, chain_name)
        on_failure(f"refused:{error.code}")
        raise error from None
    except ProviderError as failure:
        error = refusal(failure, chain_name)
        on_failure(f"refused:{error.code}")
        raise error from None


def _store(settings: Settings, owner: str, device: str, target: Target, existing: dict | None,
           clip_id: str, data: bytes, mime: str, *, provider_id: str, model_id: str,
           voice: str | None, emotion: str | None, on_logged) -> dict[str, Any]:
    """Write the file, then the row, then remove the file the row used to name."""
    if len(data) > CLIP_LIMIT:
        raise ApiError(400, "invalid_input", "That recording is too large to keep.")
    digest = hashlib.sha256(data).hexdigest()[:8]
    # From the stored lexeme id and the derived id — never from anything the request said.
    reference = f"audio/{target.lexeme_id}/{clip_id}-{digest}.{speaking.extension_for(mime)}"
    destination = Path(settings.media_path) / reference
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, destination)

    at = now_instant()
    row = {
        "id": clip_id,
        "lexemeId": target.lexeme_id,
        "targetKind": target.kind,
        "targetId": target.id,
        "text": target.text,
        "lang": target.language,
        "emotion": emotion,
        "audioRef": reference,
        "audioMime": mime,
        "providerId": provider_id,
        "modelId": model_id,
        "voice": voice,
        # A tombstone is revived at its stored revision: the id is derived, so this is its row.
        "deleted": False,
        "createdAt": (existing or {}).get("createdAt", at),
        "editedAt": at,
        "editedBy": device,
        "revision": (existing or {}).get("revision", 0),
    }
    try:
        graph.merge_graph(owner, device, {"pronunciations": [row]})
    except Exception:
        if reference != (existing or {}).get("audioRef"):
            destination.unlink(missing_ok=True)
        on_logged(row, "write_failed")
        raise
    previous = (existing or {}).get("audioRef")
    if previous and previous != reference:
        Path(settings.media_path).joinpath(previous).unlink(missing_ok=True)
    stored = graph.pronunciation(owner, clip_id) or row
    on_logged(stored, "stored")
    return stored


def _logger(caller: str, target: Target):
    def log(started: float, *, source: str, result: str, clip: dict | None = None, failed: bool = False,
            **extra: Any) -> None:
        journal.outcome(
            caller, failed,
            target=f"{target.kind}:{target.id}", lang=target.language, chars=len(target.text),
            text=target.text, emotion=target.emotion if target.kind == "example" else None,
            source=source,
            pair=f"{clip['providerId']}:{clip['modelId']}" if clip else None,
            voice=(clip or {}).get("voice"), ref=(clip or {}).get("audioRef"),
            mime=(clip or {}).get("audioMime"), result=result,
            seconds=time.monotonic() - started, **extra,
        )

    return log


def _passed(answer) -> str | None:
    return ",".join(f"{provider}:{model}:{reason}" for provider, model, reason in answer.passed_over) or None
