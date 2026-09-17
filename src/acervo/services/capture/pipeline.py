"""One capture, proposed: resolve, the vocabulary checks, the duplicate check, compose, the draft.

Shared by the interactive route, which returns the proposal for review, and the headless capture
job, which saves it to the Inbox. Nothing here writes.
"""

from __future__ import annotations

from typing import Any

from acervo.errors import ApiError
from acervo.models import Answer
from acervo.repository import graph
from acervo.services.capture.coerce import reference_of, trimmed
from acervo.services.capture.compose import compose
from acervo.services.capture.draft import draft_from
from acervo.services.capture.resolve import resolve
from acervo.settings import Settings

TEXT_LIMIT = 20000
SEPARATORS = {"", "---", "***", "___"}


def leading_blanks(lines: list[str]) -> int:
    """Blank lines and rules at the front of a window, skipped without a model call."""
    count = 0
    while count < len(lines) and lines[count].strip() in SEPARATORS:
        count += 1
    return count


def logical_block(lines: list[str]) -> int:
    """How far to skip when the front of a window could not be read as a word at all.

    Blocks in notes files are separated by a blank line or a rule often enough that this keeps a walk
    moving past junk without spending a call on every single line.
    """
    for index, line in enumerate(lines):
        if index and line.strip() in SEPARATORS:
            while index < len(lines) and lines[index].strip() in SEPARATORS:
                index += 1
            return index
    return len(lines)


def _passed_over(*calls: Answer) -> list[dict[str, str]]:
    """Which providers were asked before the one that answered, and why they were not it.

    A fall-through is otherwise completely silent. The entry names the model that wrote it, but a
    provider at the head of the owner's order that is quietly broken looks exactly like one they
    never chose — and they would go on believing it is the one building their words.

    Deduplicated across the two model calls: a provider that refused both is one thing that is
    wrong, not two.
    """
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for call in calls:
        for provider, model, reason in call.passed_over:
            seen.setdefault((provider, model), {"provider": provider, "model": model, "reason": reason})
    return list(seen.values())


def _foldable(resolution: dict[str, Any], body: dict[str, Any]) -> dict[str, Any] | None:
    """What this capture carried that the entry already held may not have.

    `resolution["sentences"]` is the learner's own text, corrected — a dictionary's examples never
    reach it (`coerce.reference_of`), which is exactly what makes folding it in safe: everything
    here can legitimately become an attestation on the stored word.

    None when the capture was just the word again, which is the common case and not worth offering.
    """
    sentences = resolution["sentences"]
    note = trimmed(body.get("note")) or None
    reference = reference_of(body)
    if not sentences and not note and reference is None:
        return None
    return {"sentences": sentences, "reference": reference is not None, "note": note}


def propose(settings: Settings, account: str, body: dict[str, Any]) -> dict[str, Any]:
    """Resolve and compose one entry from `body`, and write nothing.

    What a person reviews in the Add view, and what the headless capture job saves. The order is
    contract: the vocabulary checks come before generation, so an unkept language never spends a
    model call; the duplicate check comes after resolve and before compose, so a repeat capture
    costs one call rather than two. No transaction is held across either model call.
    """
    vocabularies = graph.owner_vocabularies(account)
    resolution, resolving = resolve(settings, account, body, vocabularies)

    vocabulary = next(
        (entry for entry in vocabularies if entry["language"] == resolution["language"]), None
    )
    if vocabulary is None:
        # Deliberately before generation: building an article for a language the owner does not keep
        # would spend a model call on something with nowhere to go.
        raise ApiError(
            409,
            "language_not_configured",
            f"This looks like {resolution['language']}, which you have no vocabulary for yet. "
            "Add it in Settings, then capture this again.",
        )
    if not vocabulary["glossLangs"]:
        raise ApiError(
            409,
            "language_not_configured",
            f"Your {resolution['language']} vocabulary has no translation language set, so an entry "
            "cannot be built. Choose one in Settings.",
        )

    duplicates = graph.duplicate_lexemes(
        account, resolution["language"], resolution["headword"], resolution["lemma"]
    )
    if duplicates:
        # A repeat capture is an addition, not an entry (design §05). Merging it into the word it
        # belongs to is the article conversation's job, and this branch already knows everything
        # that job needs: resolve has run, so the learner's own sentences are in hand, separated
        # from anything a dictionary supplied. No second model call, and no merge path here — the
        # interface opens the stored article and asks one ordinary question.
        return {
            "resolution": resolution, "duplicates": duplicates, "draft": None,
            "passedOver": _passed_over(resolving),
            "foldable": _foldable(resolution, body),
        }

    topics = graph.owner_topics(account)
    # The model that answered, not the one that was asked first: with a chain, those differ the
    # moment a provider is rate limited, and the entry must record the one that did the work.
    answer, composing = compose(settings, account, resolution, body, vocabulary, topics)
    draft = draft_from(answer, resolution, body, vocabulary, topics, composing.model)

    return {
        "resolution": resolution, "duplicates": [], "draft": draft,
        "passedOver": _passed_over(resolving, composing),
        # Total rather than conditional: a field that is sometimes absent is a field every reader
        # has to guess about.
        "foldable": None,
    }
