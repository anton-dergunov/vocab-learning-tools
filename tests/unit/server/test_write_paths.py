"""The two batch write paths, against the routes they actually use.

A job's write path is a client's write path — same route, same validation, same revision allocation
as a phone — so there is no point testing either against anything but the real thing. Both go through
`acervo.client`, pointed at the application in this process.
"""

from __future__ import annotations

import re

import pytest
from graph_records import DEVICE, lexeme, sense, vocabulary

from acervo.consumers.anki.state import held_by_lexeme, study_states
from acervo.images.ids import image_prompt_id, seed_for
from acervo.jobs.images.publish import plan_publish, publish
from acervo.jobs.images.run import Store

INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@pytest.fixture
def word(server):
    """One word with two senses, and the ids a run would have been derived from."""
    entry = lexeme(headword="picar", lemma="picar")
    first = sense(entry["id"], definition="Cortar en trozos.", order=0)
    second = sense(entry["id"], definition="Escocer la piel.", order=1)
    answer = server.push(
        {"vocabularies": [vocabulary()], "lexemes": [entry], "senses": [first, second]}
    )
    assert answer.status_code == 200, answer.text
    return entry, [first, second]


def run_directory(root, entry, senses, *, drawn=True):
    """A synthetic run: the record shape `run.py` writes, and a file where it says one is."""
    store = Store(root)
    for order, meaning in enumerate(senses):
        identifier = image_prompt_id(meaning["id"])
        reference = f"images/{entry['id']}/{identifier}.webp"
        store.write(
            store.record_path(identifier),
            {
                "id": identifier,
                "lexemeId": entry["id"],
                "senseId": meaning["id"],
                "prompt": f"a chopped onion, take {order}",
                "styleId": "flat-vector",
                "seed": seed_for(meaning["id"], 1),
                "modelId": "gemini-3.8-flash",
                "promptVersion": "img-abcdef012345-0123456789ab-c3f7d5",
                "imageRef": reference if drawn else None,
                "imageModelId": "gemini-3.1-flash-lite-image" if drawn else None,
                "attempts": 1,
                "failureReason": None,
                "blocked": False,
            },
        )
        if drawn:
            store.image_path(identifier).write_bytes(b"webp image bytes")
    return store


# ── images ──────────────────────────────────────────────────────────────────


def test_a_verified_run_lands_as_image_prompts_and_files_the_media_route_serves(server, word, tmp_path):
    entry, senses = word
    store = run_directory(tmp_path / "run", entry, senses)

    with server.api() as client:
        outcome = publish(
            store, client, media=server.media, device_id=DEVICE, report=lambda _line: None
        )

    assert outcome.ok, outcome.problems
    assert (outcome.written, outcome.copied) == (2, 2)

    written = server.pull().json()["data"]["changes"]["imagePrompts"]
    assert len(written) == 2
    stored = {record["senseId"]: record for record in written}
    for meaning in senses:
        record = stored[meaning["id"]]
        # The id is derived from the sense, which is what makes a run resumable and re-publishable.
        assert record["id"] == image_prompt_id(meaning["id"])
        assert record["revision"] > 0
        assert record["imageModelId"] == "gemini-3.1-flash-lite-image"
        assert INSTANT.match(record["createdAt"])
        # And the file is where the record says it is, behind the same auth as a dictionary.
        answer = server.client.get(f"/api/acervo/media/{record['imageRef']}", headers=server.auth)
        assert answer.status_code == 200
        assert answer.content == b"webp image bytes"


def test_publishing_twice_writes_nothing_the_second_time(server, word, tmp_path):
    """Re-posting a stored record at revision zero is a stale write, not a no-op, so what the account
    already holds has to be recognised rather than retried."""
    entry, senses = word
    store = run_directory(tmp_path / "run", entry, senses)
    quiet = {"media": server.media, "device_id": DEVICE, "report": lambda _line: None}

    with server.api() as client:
        first = publish(store, client, **quiet)
        second = publish(store, client, **quiet)

    assert first.written == 2
    assert (second.written, second.held) == (0, 2)


def test_a_run_naming_senses_the_account_does_not_hold_publishes_nothing(server, word, tmp_path):
    """The ids in a run were read from whatever database it ran against. Re-import a bundle and every
    sense is minted afresh, which leaves a run pointing at senses nobody holds — and the run
    directory is internally consistent either way, so `verify` cannot see it."""
    entry, senses = word
    store = run_directory(tmp_path / "run", entry, senses)
    stranded = sense("lexemegone00001", definition="Nowhere.")
    stranded_id = image_prompt_id(stranded["id"])
    store.write(
        store.record_path(stranded_id),
        {
            "id": stranded_id, "lexemeId": "lexemegone00001", "senseId": stranded["id"],
            "prompt": "a picture of nothing", "styleId": "flat-vector", "seed": 7,
            "modelId": "gemini-3.8-flash", "promptVersion": "img-a-b-c",
            "imageRef": f"images/lexemegone00001/{stranded_id}.webp",
            "imageModelId": "gemini-3.1-flash-lite-image",
        },
    )
    store.image_path(stranded_id).write_bytes(b"webp image bytes")

    lines: list[str] = []
    with server.api() as client:
        outcome = publish(
            store, client, media=server.media, device_id=DEVICE, report=lines.append
        )

    assert not outcome.ok
    assert "names a sense this account does not hold" in outcome.problems
    # Nothing at all, not "the good ones": a half-published run is worse than an unpublished one.
    assert outcome.written == 0
    assert server.pull().json()["data"]["changes"]["imagePrompts"] == []
    assert not list(server.media.rglob("*.webp"))
    assert any("Nothing was published" in line for line in lines)


def test_a_sense_the_writer_refused_is_not_a_fault_and_is_not_written(server, word, tmp_path):
    """A refusal is a finished outcome with no picture, not a gap to fill."""
    entry, senses = word
    store = run_directory(tmp_path / "run", entry, senses, drawn=False)
    queued, outcome = plan_publish(store, server.pull().json()["data"]["changes"])
    assert queued == []
    assert outcome.ok
    assert outcome.undrawn == 2


def test_an_inconsistent_run_directory_is_refused_before_the_graph_is_touched(server, word, tmp_path):
    entry, senses = word
    store = run_directory(tmp_path / "run", entry, senses)
    # A record claiming an image that is not on disk would become a broken `imageRef`.
    store.image_path(image_prompt_id(senses[0]["id"])).unlink()

    with server.api() as client:
        outcome = publish(
            store, client, media=server.media, device_id=DEVICE, report=lambda _line: None
        )

    assert not outcome.ok
    assert outcome.written == 0
    assert server.pull().json()["data"]["changes"]["imagePrompts"] == []


# ── study state ─────────────────────────────────────────────────────────────


def exported_for(entry, *, reps=4, stability=12.5, retrievability=0.9):
    """What `robot.export_state()` returns for one note, in its own shape."""
    return {
        "operation": "export-state",
        "sync": "complete",
        "notes": [
            {
                "note_id": "note00000000001",
                "lexeme_id": entry["id"],
                "anki_note_id": 17,
                "card_ids": [91],
                "cards": [
                    {
                        "anki_card_id": 91, "reps": reps, "lapses": 1, "queue": 2,
                        "suspended": False, "flag": 3, "stability": stability,
                        "difficulty": 5.2, "retrievability": retrievability,
                        "last_review": "2026-09-01T00:00:00.000Z",
                    }
                ],
            }
        ],
    }


def push_state(server, entry, **overrides):
    changes = server.pull().json()["data"]["changes"]
    live = {row["id"] for row in changes["lexemes"] if not row["deleted"]}
    rows, skipped = study_states(
        exported_for(entry, **overrides), held_by_lexeme(changes), live, device_id="ankiworker0001"
    )
    with server.api() as client:
        answer = client.push_graph({"studyStates": rows}, device_id="ankiworker0001")
    return answer, skipped


def test_anki_review_state_reaches_the_graph_with_a_new_revision(server, word):
    entry, _senses = word
    before = server.pull().json()["data"]["cursor"]

    answer, skipped = push_state(server, entry)

    assert skipped == []
    assert answer["cursor"] > before
    (row,) = server.pull().json()["data"]["changes"]["studyStates"]
    assert row["revision"] > before
    assert row["system"] == "anki"
    assert row["lexemeId"] == entry["id"]
    assert row["noteId"] == 17
    assert row["cardIds"] == [91]
    assert row["reps"] == 4
    assert 0 < row["retrievability"] < 1
    assert INSTANT.match(row["lastReview"])
    assert INSTANT.match(row["syncedAt"])


def test_a_second_pull_updates_the_same_row_rather_than_adding_one(server, word):
    """One row per (lexeme, system), so a nightly job must not accumulate a row a night."""
    entry, _senses = word
    push_state(server, entry, reps=4)
    push_state(server, entry, reps=9, stability=30.0, retrievability=0.98)

    rows = server.pull().json()["data"]["changes"]["studyStates"]
    assert len(rows) == 1
    assert rows[0]["reps"] == 9
    assert rows[0]["stability"] == 30.0


def test_a_review_timestamp_anki_would_have_produced_is_refused_by_the_route(server, word):
    """`.isoformat()` gives `+00:00` and six fractional digits. This is the shape the route wants,
    and the reason `instant_of` exists."""
    entry, _senses = word
    changes = server.pull().json()["data"]["changes"]
    live = {row["id"] for row in changes["lexemes"] if not row["deleted"]}
    rows, _ = study_states(
        exported_for(entry), held_by_lexeme(changes), live, device_id="ankiworker0001"
    )
    rows[0]["lastReview"] = "2026-09-01T00:00:00+00:00"
    answer = server.push({"studyStates": rows})
    assert answer.status_code == 400
    assert answer.json()["error"]["code"] == "invalid_record"
