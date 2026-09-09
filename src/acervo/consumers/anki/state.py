"""What Anki knows about a word's scheduling, as Acervo records it.

The content goes out and the FSRS state comes back: this is the second half. One row per
*(lexeme, system)*, keyed by system so a second learning tool never collides with Anki.

The robot already exports everything a row needs; this decides how a note's cards collapse into one
row, and what has nowhere to go.
"""

from __future__ import annotations

from typing import Any

from acervo.domain.ids import new_record_id, now_instant

SYSTEM = "anki"

# Exported per card and deliberately not stored. `queue`, `suspended` and `flag` are Anki's own
# review furniture with no column here, and inventing columns for them means rebuilding the database
# for information Acervo does not read.
UNSTORED = ("queue", "suspended", "flag")


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def collapse(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """A note's cards as the one set of numbers a row holds.

    The Acervo note type has exactly one template, so in practice this collapses one card. The rule
    still has to be written down for the day it does not: counts add up, because every review of
    every card was a review of this word; the memory state comes from the *least stable* card,
    because that is the one that will come up first and the one that says how well the word is
    actually known; and the last review is the most recent of any of them.
    """
    if not cards:
        return {
            "reps": 0, "lapses": 0, "stability": 0.0, "difficulty": 0.0,
            "retrievability": 0.0, "lastReview": None,
        }
    weakest = min(cards, key=lambda card: _number(card.get("stability")))
    reviews = [card.get("last_review") for card in cards if card.get("last_review")]
    return {
        "reps": sum(int(card.get("reps") or 0) for card in cards),
        "lapses": sum(int(card.get("lapses") or 0) for card in cards),
        "stability": _number(weakest.get("stability")),
        "difficulty": _number(weakest.get("difficulty")),
        # Bounded to (0, 1] by the schema; a card never reviewed has no retrievability rather than a
        # zero, and zero would read as "certainly forgotten".
        "retrievability": min(1.0, max(0.0, _number(weakest.get("retrievability")))),
        "lastReview": max(reviews) if reviews else None,
    }


def study_states(
    exported: dict[str, Any],
    held: dict[str, dict[str, Any]],
    live_lexemes: set[str],
    *,
    device_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The `studyStates` change set for one `export-state`, and the notes left out of it.

    `held` is what the account already has, keyed by lexeme id, and it is what makes this an update
    rather than a first write: a record the graph holds must state the revision it was edited from,
    and must keep the id and `createdAt` it already has.

    A note whose lexeme the account does not hold is skipped rather than refused. That is an ordinary
    state, not a mismatch: a word removed in Acervo keeps its card in the collection until someone
    deletes it there, and one such note must not stop the other nine hundred from being written.
    """
    at = now_instant()
    changes: list[dict[str, Any]] = []
    skipped: list[str] = []
    for note in exported.get("notes") or []:
        lexeme_id = str(note.get("lexeme_id") or "")
        if not lexeme_id:
            continue
        if lexeme_id not in live_lexemes:
            skipped.append(str(note.get("note_id") or lexeme_id))
            continue
        stored = held.get(lexeme_id)
        numbers = collapse(list(note.get("cards") or []))
        changes.append(
            {
                "id": stored["id"] if stored else new_record_id(),
                "lexemeId": lexeme_id,
                "system": SYSTEM,
                "noteId": int(note.get("anki_note_id") or 0),
                "cardIds": [int(identifier) for identifier in note.get("card_ids") or []],
                **numbers,
                "syncedAt": at,
                "deleted": False,
                "createdAt": stored["createdAt"] if stored else at,
                "editedAt": at,
                "editedBy": device_id,
                "revision": int(stored["revision"]) if stored else 0,
            }
        )
    return changes, skipped


def held_by_lexeme(changes: dict[str, list[dict]]) -> dict[str, dict[str, Any]]:
    """This account's existing Anki rows, by lexeme. A tombstoned one is reused rather than replaced:
    the id is still taken, and a second row for the same pair is not what the key means."""
    return {
        str(record["lexemeId"]): record
        for record in changes.get("studyStates") or []
        if record.get("system") == SYSTEM
    }
