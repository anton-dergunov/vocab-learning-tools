"""External dictionaries, ported case for case from the hook suite this replaces."""

from __future__ import annotations

import json

import httpx
import pytest


def write_metadata(directory, identifier, **overrides):
    (directory / f"{identifier}.json").write_text(
        json.dumps(
            {
                "id": identifier, "name": f"Dictionary {identifier}", "sourceLang": "es",
                "targetLang": "en", "tier": "fields", "licence": "CC BY-SA 4.0",
                "attribution": "Wiktionary contributors.", "entryCount": 10, "keyCount": 12,
                "blobBytes": 100, "indexBytes": 40, "schemaVersion": 1, **overrides,
            }
        )
    )


@pytest.fixture
def held(server):
    write_metadata(server.dictionaries, "kaikki-es-es")
    write_metadata(server.dictionaries, "cc-cedict", sourceLang="zh-Hans")
    return server


@pytest.fixture
def source(monkeypatch):
    """Stands in for the third party, and records what it was asked for."""
    calls: list[dict] = []
    queued: list = []

    def get(url, *, headers=None, timeout=None, **_kwargs):
        calls.append({"url": url, "headers": dict(headers or {})})
        answer = queued.pop(0) if queued else httpx.Response(404, text="")
        if isinstance(answer, Exception):
            raise answer
        return answer

    from acervo.services.dictionaries import online

    monkeypatch.setattr(online.httpx, "get", get)
    return type("Source", (), {"calls": calls, "queue": queued})()


# ── what the server says it holds ───────────────────────────────────────────


def test_it_lists_the_artifacts_on_disk_by_id(held):
    answer = held.get("/dictionaries")
    assert answer.status_code == 200
    assert [row["id"] for row in answer.json()["data"]["dictionaries"]] == ["cc-cedict", "kaikki-es-es"]


def test_it_carries_the_licence_and_attribution_the_interface_has_to_show(held):
    first = held.get("/dictionaries").json()["data"]["dictionaries"][0]
    assert first["licence"] == "CC BY-SA 4.0"
    assert first["attribution"] == "Wiktionary contributors."


def test_it_carries_the_byte_counts_a_remote_read_is_sized_by(held):
    """`blobBytes` and `indexBytes` are the size handed to the range reader, so a listing without
    them breaks reading a dictionary the device has not installed."""
    first = held.get("/dictionaries").json()["data"]["dictionaries"][0]
    assert first["blobBytes"] == 100
    assert first["indexBytes"] == 40


def test_it_ignores_a_half_written_artifact_rather_than_failing_the_whole_list(held):
    (held.dictionaries / "broken.json").write_text("{ not json")
    answer = held.get("/dictionaries")
    assert answer.status_code == 200
    assert [row["id"] for row in answer.json()["data"]["dictionaries"]] == ["cc-cedict", "kaikki-es-es"]


def test_the_listing_needs_the_owner_to_be_signed_in(held):
    assert held.client.get("/api/acervo/v1/dictionaries").status_code == 401


# ── the online connectors ───────────────────────────────────────────────────


def lookup(server, name, **query):
    parameters = "&".join(f"{key}={value}" for key, value in query.items())
    return server.get(f"/dictionaries/online/{name}?{parameters}")


def test_it_percent_encodes_the_headword(server, source):
    """A first spike run counted four "transport failures" on each API. They were the same four
    words, and the cause was a missing percent-encoding rather than anything about the sources."""
    source.queue.append(httpx.Response(200, json={"word": "de repente", "entries": []}))
    lookup(server, "freedictionaryapi", word="de%20repente", language="es")
    assert "de%20repente" in source.calls[0]["url"]
    assert source.calls[0]["headers"]["User-Agent"].startswith("Acervo/")


def test_it_maps_freedictionaryapis_own_field_shape(server, source):
    source.queue.append(
        httpx.Response(
            200,
            json={
                "word": "picar",
                "entries": [
                    {
                        "language": {"code": "es"},
                        "partOfSpeech": "verb",
                        "pronunciations": [{"type": "ipa", "text": "/piˈkaɾ/"}],
                        "senses": [
                            {"definition": "to itch", "examples": ["una tela que pica"]},
                            {"definition": ""},
                        ],
                    }
                ],
            },
        )
    )
    entry = lookup(server, "freedictionaryapi", word="picar", language="es").json()["data"]["entries"][0]
    assert entry["headword"] == "picar"
    assert entry["posLabel"] == "verb"
    assert entry["ipa"] == "/piˈkaɾ/"
    assert [sense["definition"] for sense in entry["senses"]] == ["to itch"]
    assert entry["senses"][0]["examples"] == [{"text": "una tela que pica"}]


def test_it_strips_the_wiki_markup_wikimedia_returns_inside_its_definitions(server, source):
    source.queue.append(
        httpx.Response(
            200,
            json={
                "es": [
                    {
                        "partOfSpeech": "Verb",
                        "language": "Spanish",
                        "definitions": [
                            {
                                "definition": 'to <a rel="mw:WikiLink" href="/wiki/itch">itch</a>',
                                "parsedExamples": [
                                    {
                                        "example": "una tela que <b>pica</b>",
                                        "translation": "a cloth that itches",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "en": [{"partOfSpeech": "Noun", "definitions": [{"definition": "something else"}]}],
            },
        )
    )
    entries = lookup(server, "wikimedia-rest", word="picar", language="es").json()["data"]["entries"]
    assert len(entries) == 1, "only the language asked for"
    assert entries[0]["senses"][0]["definition"] == "to itch"
    assert entries[0]["senses"][0]["examples"] == [
        {"text": "una tela que pica", "translation": "a cloth that itches"}
    ]


def test_it_returns_every_language_when_none_is_asked_for(server, source):
    source.queue.append(
        httpx.Response(
            200,
            json={
                "es": [{"partOfSpeech": "Verb", "definitions": [{"definition": "to itch"}]}],
                "pt": [{"partOfSpeech": "Verb", "definitions": [{"definition": "picar"}]}],
            },
        )
    )
    entries = lookup(server, "wikimedia-rest", word="picar").json()["data"]["entries"]
    assert [entry["language"] for entry in entries] == ["es", "pt"]


def test_a_word_the_source_does_not_hold_is_an_absence_not_a_failure(server, source):
    """The two sources disagree about how to say it: one answers 200 with an empty list, the other
    404. Conflating either with a transport error understates coverage, which it once did."""
    source.queue.append(httpx.Response(200, json={"word": "zzzz", "entries": []}))
    assert lookup(server, "freedictionaryapi", word="zzzz").json()["data"]["entries"] == []

    source.queue.append(httpx.Response(404, text=""))
    assert lookup(server, "wikimedia-rest", word="zzzz").json()["data"]["entries"] == []


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (httpx.ConnectError("connection refused"), "dictionary_unreachable"),
        (httpx.Response(500, text=""), "dictionary_failed"),
        (httpx.Response(200, text="not json"), "dictionary_unusable"),
    ],
)
def test_it_says_so_when_the_source_is_unreachable_or_broken(server, source, answer, code):
    source.queue.append(answer)
    refused = lookup(server, "freedictionaryapi", word="picar")
    assert refused.status_code == 502
    assert refused.json()["error"]["code"] == code


def test_it_refuses_an_unknown_source_and_a_missing_word(server, source):
    assert lookup(server, "wordnik", word="picar").status_code == 404
    assert lookup(server, "freedictionaryapi", word="").status_code == 400


def test_a_lookup_needs_the_owner_to_be_signed_in(server):
    answer = server.client.get("/api/acervo/v1/dictionaries/online/freedictionaryapi?word=picar")
    assert answer.status_code == 401
