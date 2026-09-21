"""Settings ▸ Rules: stored per owner, and appended to the text prompts that write for the owner."""

from __future__ import annotations

import pytest

from acervo.services.rules import LIMIT, with_rules

from graph_records import lexeme, sense, vocabulary

RULES = "I am vegan: never depict or mention meat or fish as food."


def systems_of(server):
    return [
        next((m["content"] for m in call["messages"] if m["role"] == "system"), None)
        for call in server.model.calls
    ]


def users_of(server):
    return [
        next((m["content"] for m in call["messages"] if m["role"] == "user"), "")
        for call in server.model.calls
    ]


@pytest.fixture
def ruled(server):
    assert server.put("/rules", {"rules": RULES}).status_code == 200
    return server


# ── the setting ─────────────────────────────────────────────────────────────


def test_there_are_none_until_the_owner_writes_some(server):
    answer = server.get("/rules")
    assert answer.status_code == 200
    assert answer.json()["data"] == {"rules": "", "chosen": False, "limit": LIMIT}


def test_they_are_stored_trimmed_and_read_back(server):
    answer = server.put("/rules", {"rules": f"  {RULES}\n"})
    assert answer.status_code == 200
    assert answer.json()["data"]["rules"] == RULES
    assert server.get("/rules").json()["data"] == {"rules": RULES, "chosen": True, "limit": LIMIT}


def test_emptying_them_is_allowed(ruled):
    assert ruled.put("/rules", {"rules": ""}).json()["data"]["rules"] == ""


def test_too_long_or_not_text_is_refused(server):
    assert server.put("/rules", {"rules": "x" * (LIMIT + 1)}).status_code == 400
    assert server.put("/rules", {"rules": 3}).status_code == 400
    assert server.get("/rules").json()["data"]["rules"] == ""


# ── where they go ───────────────────────────────────────────────────────────


def test_with_none_a_prompt_is_untouched(server):
    assert with_rules("The prompt.", server.owner) == "The prompt."


def test_with_some_they_close_the_prompt(ruled):
    joined = with_rules("The prompt.", ruled.owner)
    assert joined.startswith("The prompt.\n\n## The reader's standing rules")
    assert joined.endswith(RULES)


def test_capture_writes_the_entry_with_them_and_resolves_the_word_without(ruled):
    from test_capture import ARTICLE, RESOLUTION

    ruled.push({"vocabularies": [vocabulary()]})
    ruled.model.resolution = dict(RESOLUTION)
    ruled.model.article = dict(ARTICLE)
    assert ruled.capture().status_code == 200

    resolve, compose = systems_of(ruled)
    assert RULES not in resolve, "naming the word is not writing for the reader"
    assert RULES in compose


def test_the_article_conversation_carries_them(ruled):
    ruled.push({"vocabularies": [vocabulary()]})
    ruled.model.chat = {"reply": "Una respuesta.", "followUps": []}
    assert ruled.chat().status_code == 200
    assert RULES in systems_of(ruled)[0]


def test_a_picture_brief_carries_them(ruled):
    from acervo.services.images import brief_lexeme

    entry = lexeme()
    food = sense(entry["id"], definition="Dicho de un alimento, blando.", order=0)
    ruled.push({"vocabularies": [vocabulary()], "lexemes": [entry], "senses": [food]})
    ruled.model.brief = {"senses": [{
        "senseId": food["id"], "styleId": "oil-painting", "anchorExampleId": None,
        "situation": "a kitchen", "subject": "steamed carrots", "brief": "Steamed carrots.",
    }]}
    brief_lexeme(ruled.settings, ruled.owner, "device000000001", entry["id"])

    assert RULES in users_of(ruled)[0]
