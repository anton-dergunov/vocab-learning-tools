"""Asking for a loop: the route, the rows it writes, and the job it queues.

The generator is faked at the HTTP boundary and fed the responses recorded from the real one in
`tests/unit/loops/fixtures/`, so this is a test of Acervo's half and never of the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from graph_records import lexeme, sense, vocabulary

from acervo.loops.client import Loop, Operation

FIXTURES = Path(__file__).resolve().parents[1] / "loops" / "fixtures"
LEXIBEAT_URL = "http://lexibeat:8000/api/v1"


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class GeneratorStub:
    """Answers the four calls Acervo makes, and remembers what it was asked."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.bodies: list[dict] = []
        self.operation = recorded("queued")
        self.schema = recorded("schema")
        self.failure: Exception | None = None
        self.started: list[dict] = []

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        request = httpx.Request(method, url, json=kwargs.get("json"))
        self.calls.append(request)
        if kwargs.get("json"):
            self.bodies.append(kwargs["json"])
        if self.failure is not None:
            raise self.failure
        path = httpx.URL(url).path
        if path.endswith("/schema"):
            return httpx.Response(200, json=self.schema)
        if path.endswith("/health"):
            return httpx.Response(200, json=recorded("health"))
        if method == "POST":
            self.started.append(kwargs.get("json") or {})
        return httpx.Response(200, json=self.operation)

    def get(self, url: str, **kwargs) -> httpx.Response:
        return httpx.Response(200, content=b"ID3-a-finished-track",
                              headers={"content-type": "audio/mpeg"})


@pytest.fixture
def generator(server, monkeypatch) -> GeneratorStub:
    stub = GeneratorStub()
    monkeypatch.setattr(server.settings, "lexibeat_url", LEXIBEAT_URL)

    class Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def request(self, method, url, **kwargs):
            return stub.request(method, url, **kwargs)

        def get(self, url, **kwargs):
            return stub.get(url, **kwargs)

    monkeypatch.setattr("acervo.loops.client.httpx.Client", Client)
    return stub


def words(server, count: int = 3, **overrides):
    """A vocabulary and `count` loop-eligible words."""
    made = []
    server.push({"vocabularies": [vocabulary()]})
    for index in range(count):
        entry = lexeme(headword=f"palabra{index}", lemma=f"palabra{index}", status="active",
                       primaryGloss=f"word {index}", emotion="plainly", **overrides)
        server.push({"lexemes": [entry], "senses": [sense(entry["id"])]})
        made.append(entry)
    return made


def ask(server, ids, **overrides):
    body = {"deviceId": "device000000001", "language": "es", "lexemeIds": ids}
    return server.post("/loops", {**body, **overrides})


# ── the schema passthrough ──────────────────────────────────────────────────


def test_the_generators_catalogues_are_read_rather_than_copied(server, generator):
    answer = server.get("/loops/schema")
    assert answer.status_code == 200, answer.text
    body = answer.json()["data"]
    assert set(body["patterns"]) == {"retrieval", "alternating"}
    assert "auto" in body["families"]
    assert body["productionBundle"] is True
    # One route, written out. Nothing concatenates a path a client sent.
    assert [httpx.URL(str(call.url)).path for call in generator.calls] == ["/api/v1/schema"]


def test_no_generator_configured_is_said_rather_than_crashed(server):
    assert server.get("/loops/schema").status_code == 503


# ── asking for one ──────────────────────────────────────────────────────────


def test_a_loop_is_written_with_its_words_and_no_track_yet(server, generator):
    made = words(server, 3)
    answer = ask(server, [one["id"] for one in made])
    assert answer.status_code == 202, answer.text
    body = answer.json()["data"]

    loop = body["loop"]
    # Derived state: an absent reference is the whole of what "not rendered" means. There is no
    # status column to disagree with it.
    assert loop["audioRef"] is None and loop["audioMime"] is None
    assert loop["durationSeconds"] is None
    assert loop["language"] == "es" and loop["pattern"] == "retrieval"
    assert body["job"]["kind"] == "loop" and body["job"]["subject"]["id"] == loop["id"]

    items = server.pull().json()["data"]["changes"]["loopItems"]
    assert [row["position"] for row in items] == [0, 1, 2]
    assert [row["sourceText"] for row in items] == ["palabra0", "palabra1", "palabra2"]
    assert [row["targetText"] for row in items] == ["word 0", "word 1", "word 2"]
    # Not timed yet, which the loop's own empty reference is what says.
    assert all(row["endSeconds"] == 0 for row in items)


def test_the_words_are_the_ids_that_were_sent_in_the_order_they_were_sent(server, generator):
    made = words(server, 3)
    reversed_ids = [one["id"] for one in reversed(made)]
    ask(server, reversed_ids)
    items = server.pull().json()["data"]["changes"]["loopItems"]
    assert [row["lexemeId"] for row in sorted(items, key=lambda r: r["position"])] == reversed_ids


def test_loops_are_numbered_after_the_last_one_in_that_language(server, generator):
    made = words(server, 2)
    first = ask(server, [made[0]["id"]]).json()["data"]["loop"]
    second = ask(server, [made[1]["id"]]).json()["data"]["loop"]
    assert second["position"] > first["position"]


# ── what it refuses ─────────────────────────────────────────────────────────


def test_a_word_with_no_single_term_to_speak_is_refused_by_name(server, generator):
    """Refused rather than silently dropped: a loop of two words where three were asked for, with
    nothing saying which went missing, is worse than a refusal. Nothing backfills `primaryGloss`."""
    made = words(server, 2)
    server.push({"vocabularies": [vocabulary()]})
    bare = lexeme(headword="singloss", lemma="singloss", status="active", primaryGloss=None)
    server.push({"lexemes": [bare], "senses": [sense(bare["id"])]})

    answer = ask(server, [made[0]["id"], bare["id"]])
    assert answer.status_code == 422
    assert "singloss" in answer.text
    # And nothing was written: a refused loop is not a half-made one.
    assert server.pull().json()["data"]["changes"]["loops"] == []


def test_a_word_another_account_holds_is_not_found(server, other, generator):
    made = words(server, 1)
    other.push({"vocabularies": [vocabulary()]})
    stranger = lexeme(status="active", primaryGloss="theirs")
    other.push({"lexemes": [stranger]})
    assert ask(server, [made[0]["id"], stranger["id"]]).status_code == 404


@pytest.mark.parametrize("ids", [[], ["not-an-id"], ["aaaaaaaaaaaaaaa"] * 2])
def test_a_list_that_is_not_words_is_refused(server, generator, ids):
    words(server, 1)
    assert ask(server, ids).status_code in (400, 404)


def test_two_languages_in_one_loop_are_refused(server, generator):
    made = words(server, 1)
    server.push({"vocabularies": [vocabulary(id="vocaben00000001", language="en",
                                             definitionLang="en", glossLangs=["ru"], notesLang="ru")]})
    english = lexeme(language="en", headword="turmoil", lemma="turmoil", status="active",
                     primaryGloss="turmoil")
    server.push({"lexemes": [english], "senses": [sense(english["id"], definitionLang="en")]})
    assert ask(server, [made[0]["id"], english["id"]]).status_code == 400


# ── trying again ────────────────────────────────────────────────────────────


def test_try_again_on_a_loop_queues_another_render_rather_than_a_second_loop(server, generator):
    made = words(server, 1)
    loop = ask(server, [made[0]["id"]]).json()["data"]["loop"]
    answer = server.post("/jobs", {"kind": "loop", "subject": {"kind": "loop", "id": loop["id"]}})
    assert answer.status_code == 202, answer.text
    assert answer.json()["data"]["subject"]["id"] == loop["id"]
    # Still one loop: the row already existed, so this re-renders it.
    assert len(server.pull().json()["data"]["changes"]["loops"]) == 1


def test_trying_again_on_a_loop_that_is_not_yours_is_not_found(server, generator):
    assert server.post(
        "/jobs", {"kind": "loop", "subject": {"kind": "loop", "id": "aaaaaaaaaaaaaaa"}}
    ).status_code == 404


# ── a server without its samples ────────────────────────────────────────────


def test_a_loop_is_refused_before_anything_is_written_when_there_is_no_sample_pack(server, generator):
    """Fifteen of the sixteen bed families name sampled instruments, so a pack-less render dies on
    `No samples cached for …` — how far it gets depends on which voices the seed draws. Refusing in
    a second beats failing in four minutes, and the sentence says what to do about it."""
    generator.schema = {**recorded("schema"), "production_bundle": False}
    made = words(server, 1)
    answer = server.post("/loops", {"deviceId": "device000000001", "language": "es",
                                    "lexemeIds": [made[0]["id"]]})
    assert answer.status_code == 409
    body = answer.json()["error"]
    assert body["code"] == "loops_no_samples"
    assert "--install-samples" in body["message"]
    # Nothing was written: no row, and therefore no job either.
    assert server.pull().json()["data"]["changes"]["loops"] == []
    assert generator.started == []


def test_the_music_the_dialog_chose_reaches_the_render(server, generator):
    made = words(server, 1)
    answer = server.post("/loops", {"deviceId": "device000000001", "language": "es",
                                    "lexemeIds": [made[0]["id"]], "family": "acoustic-flow"})
    assert answer.status_code == 202
    # It rides on the job rather than on the row: an instruction for the render, not a fact about
    # the loop — whose own `styleId` records what the render *chose*.
    assert answer.json()["data"]["job"]["input"] == {"family": "acoustic-flow"}


def test_music_the_generator_does_not_offer_is_refused_rather_than_sent(server, generator):
    made = words(server, 1)
    answer = server.post("/loops", {"deviceId": "device000000001", "language": "es",
                                    "lexemeIds": [made[0]["id"]], "family": "polka"})
    assert answer.status_code == 400
    assert "polka" in answer.json()["error"]["message"]


def test_the_generators_own_words_survive_into_acervos_refusal():
    """The code is ours because the interface branches on it; the sentence is theirs because only
    they know what went wrong. Keeping only the constant is how "No samples cached for 'salamander'"
    became "the loop generator refused the request"."""
    from acervo.loops.client import LoopError
    from acervo.services.loops import refusal

    raised = refusal(LoopError("refused", "No samples cached for 'salamander'."))
    assert raised.code == "loops_failed"
    assert "salamander" in raised.message
    # And a refusal that said nothing still reads as a sentence rather than trailing off.
    assert refusal(LoopError("busy", "")).message.endswith(".")
