"""The article conversation, against a real model. Gated off, because this one costs money.

Everything about the route's *shape* is in `tests/unit/server/test_chat.py`, which runs offline
against a stub. What only a live call can tell you is the half a stub cannot fake: that the prompt
actually produces the JSON object it asks for, that a real model addresses the ids in the document
it was given rather than inventing them, that "small, or nothing" holds — and, most important, that
a question which should change nothing comes back with no proposal at all.

    set -a; . ./.env; set +a
    RUN_LIVE_CHAT_TESTS=true .venv/bin/python -m pytest tests/integration/test_chat_live.py -v -s

Roughly one model call per test. The document below is a real Acervo projection, ids and all.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from acervo.services.chat import run_chat
from acervo.settings import settings as read_settings

pytestmark = pytest.mark.integration

SENSE = "kq2m7x1p4vd9r0s"
EXAMPLE = "b8n4k2j7w1q5z0c"

DOCUMENT = f"""# el disfraz — Spanish
# Every record keeps its id. Delete a block to remove it; omit an id to add something new.

id: zx4p8m2v6n1t7wq
language: es
headword: el disfraz
lemma: disfraz
ipa: /disˈfɾaθ/
pos: noun
gender: masculine
register: neutral
emoji: 🎭
status: active
topics: [Appearance]
shortGloss: costume; disguise
notes:
  - Common around Carnival.
senses:
  - id: {SENSE}
    order: 0
    definition: Traje que se usa para parecer otra persona o un personaje.
    definitionLang: es
    glosses:
      - {{lang: en, terms: [costume, disguise]}}
    examples:
      - id: {EXAMPLE}
        text: El disfraz de pirata viene con un garfio.
        translation: The pirate costume comes with a hook.
        origin: llm
        approved: true
"""

NEIGHBOURS = [
    {"headword": "el traje", "shortGloss": "suit; outfit"},
    {"headword": "la máscara", "shortGloss": "mask"},
]


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def gated():
    if os.environ.get("RUN_LIVE_CHAT_TESTS") != "true":
        pytest.skip("live chat tests are gated; set RUN_LIVE_CHAT_TESTS=true to run them")
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("no GEMINI_API_KEY in the environment")
    # The default is the container's `/app/prompts`; on a workstation the tracked files are here.
    os.environ.setdefault("ACERVO_PROMPTS_PATH", str(REPOSITORY_ROOT / "prompts"))


def ask(question: str, **overrides):
    body = {
        "subject": {"kind": "article", "lexemeId": "zx4p8m2v6n1t7wq",
                    "document": DOCUMENT, "focus": None},
        "neighbours": NEIGHBOURS,
        "turns": [{"role": "you", "text": question}],
        **overrides,
    }
    answered = run_chat(read_settings(), owner=None, body=body)
    print(f"\n--- {question}\n{answered['reply']}\n    followUps: {answered['followUps']}")
    if answered["proposal"]:
        print(f"    summary: {answered['proposal']['summary']}")
        for op in answered["proposal"]["ops"]:
            print(f"    op: {op}")
    else:
        print("    proposal: none")
    return answered


def ids_in(proposal) -> set[str]:
    """Every record id an operation names. All of them must already be in the document."""
    found: set[str] = set()
    for op in proposal["ops"]:
        for field in ("target", "senseId", "after"):
            value = op.get(field)
            if isinstance(value, str):
                found.add(value.split(":", 1)[1] if ":" in value else value)
        for value in op.get("ids") or []:
            found.add(value.split(":", 1)[1] if ":" in value else value)
    return {one for one in found if one and one != "lexeme"}


def test_it_explains_without_proposing_anything():
    """The most common correct answer, and the one a chat that edits must get right."""
    answered = ask("What is the difference between «el disfraz» and «el traje»?")
    assert answered["reply"]
    assert answered["proposal"] is None, "a question is not a request to change the entry"
    assert len(answered["followUps"]) <= 3


def test_it_declines_to_change_something_that_is_not_wrong():
    answered = ask("Is «Traje que se usa para parecer otra persona» actually an error?")
    assert answered["proposal"] is None
    assert answered["reply"]


def test_it_proposes_a_note_and_addresses_only_ids_the_document_carries():
    answered = ask("Add a note about how it differs from «el traje».")
    proposal = answered["proposal"]
    assert proposal, "an explicit request to add a note should propose one"
    assert len(proposal["ops"]) <= 12
    assert ids_in(proposal) <= {"zx4p8m2v6n1t7wq", SENSE, EXAMPLE}
    assert any(op["op"] == "set" and op.get("field") == "notes" for op in proposal["ops"])
    # `notes` takes the whole list, so a proposal that drops what is already there is a rewrite of
    # the section rather than an addition to it.
    notes = next(op["value"] for op in proposal["ops"] if op.get("field") == "notes")
    assert any("Carnival" in str(line) for line in notes), "it dropped the note that was already there"


def test_a_sentence_the_owner_supplies_becomes_an_attestation():
    answered = ask("I heard this on the radio: «Se disfrazó de médico para entrar.»")
    proposal = answered["proposal"]
    assert proposal
    kinds = [op["op"] for op in proposal["ops"]]
    assert "addAttestation" in kinds, "a sentence they met is an attestation, not just an example"
    added = next(op for op in proposal["ops"] if op["op"] == "addAttestation")
    assert added["ref"]
    example = next((op for op in proposal["ops"] if op["op"] == "addExample"), None)
    if example is not None:
        assert example.get("fromAttestation") == added["ref"]
        # Provenance is derived by the applier; the model must not try to set it.
        assert "origin" not in example["example"]


def test_it_adds_one_example_rather_than_rewriting_the_sense():
    answered = ask("Give me one more example, in a shop.")
    proposal = answered["proposal"]
    assert proposal
    assert len(proposal["ops"]) <= 3, "one more example is one operation, not a rewrite"
    assert all(op["op"] in ("addExample", "addAttestation") for op in proposal["ops"])
    assert ids_in(proposal) <= {"zx4p8m2v6n1t7wq", SENSE, EXAMPLE}


def test_it_refuses_to_rebuild_the_article():
    answered = ask("Rewrite this whole entry from scratch, every field, much better.")
    # Either it says no and proposes nothing, or it proposes something small. What it must not do is
    # come back with a rewrite dressed as an edit — `applyOps` would refuse that on the device, and
    # the turn would be wasted.
    if answered["proposal"]:
        assert len(answered["proposal"]["ops"]) <= 12
    assert answered["reply"]


def test_a_dictionary_entry_is_never_proposed_against():
    body = {
        "subject": {"kind": "reference", "headword": "el disfraz", "language": "es"},
        "reference": "## Wiktionary\nel disfraz\n1. costume, fancy dress\n2. disguise, pretence",
        "referenceSources": ["Wiktionary"],
        "neighbours": NEIGHBOURS,
        "turns": [{"role": "you", "text": "Is this worth keeping? What does it actually mean?"}],
    }
    answered = run_chat(read_settings(), owner=None, body=body)
    print(f"\n--- reference subject\n{answered['reply']}\n    capture: {answered['capture']}")
    assert answered["reply"]
    # There is nothing editable on screen, so there is nothing to propose against.
    assert answered["proposal"] is None
