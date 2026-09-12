"""The chat route: one turn in, prose and maybe a proposed edit out. It writes nothing.

What is asserted here is the wire contract — the limits the route enforces, which prompt answers
which subject, and which of `proposal` / `capture` each kind may return. Whether an operation *means*
anything is `web/src/articleEdit.ts`'s question: the document is a YAML string this layer
deliberately does not parse, because `yaml.ts` is the only place that projection is understood.
"""

from __future__ import annotations

import litellm
import pytest
from graph_records import vocabulary

PRIVATE = "provider details that must stay private"

REPLY = {
    "reply": "«el traje» is any outfit; «el disfraz» is worn to be taken for someone else.",
    "followUps": ["Add that to the notes", "One more example"],
}

PROPOSAL = {
    "summary": "Adds the contrast to the notes.",
    "ops": [{"op": "set", "target": "lexeme", "field": "notes", "value": ["Not el traje."]}],
}

CAPTURE = {"headword": "el disfraz", "referenceMode": "expand", "note": "they asked about theatre"}

REFERENCE_SUBJECT = {"kind": "reference", "headword": "el disfraz", "language": "es"}


@pytest.fixture
def talking(server):
    server.push({"vocabularies": [vocabulary()]})
    server.model.chat = {**REPLY, "proposal": dict(PROPOSAL)}
    server.model.chat_reference = {**REPLY, "capture": dict(CAPTURE)}
    return server


def prompts_of(server):
    return [
        next(message["content"] for message in call["messages"] if message["role"] == "user")
        for call in server.model.calls
    ]


def systems_of(server):
    return [
        next(message["content"] for message in call["messages"] if message["role"] == "system")
        for call in server.model.calls
    ]


# ── what it refuses, and how early ──────────────────────────────────────────


def test_it_needs_a_token(server):
    answered = server.client.post("/api/acervo/v1/chat", json={})
    assert answered.status_code == 401
    assert server.model.calls == []


def test_it_refuses_a_request_that_says_nothing_about_what_it_is_about(talking):
    answered = talking.chat(subject={"kind": "article", "document": ""})
    assert answered.status_code == 400
    assert answered.json()["error"]["code"] == "invalid_input"
    assert talking.model.calls == []


def test_it_refuses_a_subject_kind_it_does_not_know(talking):
    answered = talking.chat(subject={"kind": "corpus", "document": "x"})
    assert answered.status_code == 400
    assert talking.model.calls == []


def test_it_says_so_when_no_model_is_configured(server, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    answered = server.chat()
    assert answered.status_code == 503
    assert answered.json()["error"]["code"] == "capture_unavailable"
    # Nothing was attempted: an unconfigured server must not spend a round trip finding that out.
    assert server.model.calls == []


def test_it_refuses_a_wrong_schema_version(talking):
    answered = talking.chat(schemaVersion=2)
    assert answered.status_code == 409
    assert talking.model.calls == []


# ── the limits, enforced here rather than asked for in the prompt ───────────


def test_it_sends_only_the_last_eight_turns(talking):
    turns = [{"role": "you" if index % 2 == 0 else "acervo", "text": f"turn {index}"} for index in range(12)]
    talking.chat(turns=turns)
    asked = prompts_of(talking)[0]
    assert "turn 11" in asked
    assert "turn 4" in asked
    assert "turn 3" not in asked


def test_it_caps_the_document(talking):
    talking.chat(subject={"kind": "article", "lexemeId": "lexemepicar0001",
                          "document": "x" * 40000, "focus": None})
    assert "x" * 32000 in prompts_of(talking)[0]
    assert "x" * 32001 not in prompts_of(talking)[0]


def test_it_caps_the_reference(talking):
    talking.chat(reference="y" * 20000)
    asked = prompts_of(talking)[0]
    assert "y" * 8000 in asked
    assert "y" * 8001 not in asked


def test_it_caps_the_neighbours(talking):
    talking.chat(neighbours=[{"headword": f"word{index}", "shortGloss": None} for index in range(40)])
    asked = prompts_of(talking)[0]
    assert "word19" in asked
    assert "word20" not in asked


def test_it_clamps_the_reply_and_the_follow_ups(talking):
    talking.model.chat = {
        "reply": "z" * 4000,
        "followUps": ["a" * 80, "b", "c", "d"],
        "proposal": None,
    }
    answered = talking.chat().json()["data"]
    assert len(answered["reply"]) == 1200
    assert len(answered["followUps"]) == 3
    assert len(answered["followUps"][0]) == 40


def test_it_drops_a_proposal_with_too_many_operations_and_keeps_the_reply(talking):
    talking.model.chat = {
        **REPLY,
        "proposal": {
            "summary": "a rewrite",
            "ops": [{"op": "set", "target": "lexeme", "field": "emoji", "value": "x"}] * 20,
        },
    }
    answered = talking.chat().json()["data"]
    assert answered["proposal"] is None
    assert answered["reply"].startswith("«el traje»")


def test_one_malformed_operation_drops_the_whole_proposal(talking):
    talking.model.chat = {
        **REPLY,
        "proposal": {"summary": "…", "ops": [
            {"op": "set", "target": "lexeme", "field": "notes", "value": ["fine"]},
            {"op": "set", "target": "lexeme"},
        ]},
    }
    assert talking.chat().json()["data"]["proposal"] is None


def test_it_drops_an_operation_name_it_does_not_know(talking):
    talking.model.chat = {**REPLY, "proposal": {"summary": "…", "ops": [{"op": "rewrite"}]}}
    assert talking.chat().json()["data"]["proposal"] is None


def test_it_carries_a_well_formed_proposal_through(talking):
    answered = talking.chat().json()["data"]
    assert answered["proposal"]["ops"] == PROPOSAL["ops"]
    assert answered["proposal"]["summary"] == PROPOSAL["summary"]
    assert answered["modelId"]


# ── the two subjects, and what each may return ──────────────────────────────


def test_an_article_subject_reads_the_article_prompt(talking):
    talking.chat()
    assert "You answer a learner's question" in systems_of(talking)[0]


def test_a_reference_subject_reads_the_reference_prompt(talking):
    talking.chat(subject=dict(REFERENCE_SUBJECT))
    assert "You help a learner read" in systems_of(talking)[0]


def test_a_reference_subject_never_returns_a_proposal(talking):
    # The stub is told to propose one anyway: there is nothing editable on screen, so the field is
    # dropped rather than passed on. A dictionary entry is not the learner's to change.
    talking.model.chat_reference = {**REPLY, "proposal": dict(PROPOSAL), "capture": dict(CAPTURE)}
    answered = talking.chat(subject=dict(REFERENCE_SUBJECT)).json()["data"]
    assert answered["proposal"] is None
    assert answered["capture"]["headword"] == "el disfraz"


def test_an_article_subject_never_returns_a_capture(talking):
    talking.model.chat = {**REPLY, "proposal": None, "capture": dict(CAPTURE)}
    assert talking.chat().json()["data"]["capture"] is None


def test_it_drops_a_reference_mode_it_does_not_know(talking):
    talking.model.chat_reference = {**REPLY, "capture": {**CAPTURE, "referenceMode": "invent"}}
    answered = talking.chat(subject=dict(REFERENCE_SUBJECT)).json()["data"]
    assert answered["capture"]["referenceMode"] is None


def test_it_passes_the_focus_on_when_a_block_was_tapped(talking):
    talking.chat(subject={"kind": "article", "lexemeId": "lexemepicar0001",
                          "document": "headword: picar\n", "focus": "sense:sensepicaritch0"})
    assert "sense:sensepicaritch0" in prompts_of(talking)[0]


# ── what a bad answer is called ─────────────────────────────────────────────


def test_an_unparseable_answer_says_nothing_was_changed(talking):
    talking.model.text = "not json at all"
    answered = talking.chat()
    assert answered.status_code == 502
    assert answered.json()["error"]["code"] == "llm_unusable"
    assert answered.json()["error"]["message"].endswith("so nothing was changed.")


def test_an_answer_with_no_reply_is_unusable(talking):
    talking.model.chat = {"reply": "", "followUps": [], "proposal": dict(PROPOSAL)}
    answered = talking.chat()
    assert answered.status_code == 502
    assert answered.json()["error"]["code"] == "llm_unusable"


def test_a_rate_limited_chain_reports_itself_as_rate_limited(talking):
    talking.model.error = litellm.RateLimitError(
        message=PRIVATE, llm_provider="stub", model="gemini/gemini-3.1-flash-lite"
    )
    answered = talking.chat()
    assert answered.json()["error"]["code"] == "llm_rate_limited"
    # A provider's own error text routinely echoes the request back, key included.
    assert PRIVATE not in answered.text


def test_it_writes_nothing(talking):
    before = talking.pull().json()["data"]["cursor"]
    talking.chat()
    assert talking.pull().json()["data"]["cursor"] == before


def test_it_reads_a_nested_attestation_reference(talking):
    """A real model puts `fromAttestation` inside `example` about half the time.

    Missing it is silent: the applier would derive `origin: "llm"` for a sentence the learner
    actually met, and nothing downstream would ever notice the entry had lied about provenance.
    """
    talking.model.chat = {
        **REPLY,
        "proposal": {"summary": "…", "ops": [
            {"op": "addAttestation", "ref": "a1", "attestation": {"text": "Se disfrazó."}},
            {"op": "addExample", "senseId": "kq2m7x1p4vd9r0s",
             "example": {"text": "Se disfrazó.", "fromAttestation": "a1"}},
        ]},
    }
    ops = talking.chat().json()["data"]["proposal"]["ops"]
    assert ops[1]["fromAttestation"] == "a1"
    # Lifted, not duplicated: the applier reads one place.
    assert "fromAttestation" not in ops[1]["example"]
