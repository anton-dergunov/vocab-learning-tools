"""The story contract: what `parse_reply` refuses, and why each refusal exists.

Most of these are here because a real call produced them — see `experiments/story-quality/`. The
synonym case in particular is not hypothetical: it happened on the first call ever made.
"""

from __future__ import annotations

import pytest

from acervo.stories.write import (
    MAX_PART_CHARS, StoryRefused, Written, is_form_of, parse_reply,
)

WORDS = [
    {"id": "lexemeasombr01", "headword": "asombroso", "lemma": "asombroso"},
    {"id": "lexemeladrar01", "headword": "ladrar", "lemma": "ladrar"},
]


def story(**overrides):
    payload = {
        "title": "El perro asombroso",
        "emoji": "🐕",
        "parts": [
            {"heading": "La panadería", "text": "Marcos vio un perro asombroso en la calle."},
            {"heading": "El pan", "text": "El perro empezó a ladrar delante del mostrador."},
            {"heading": "La cuenta", "text": "Pagó con una moneda. Marcos no dijo nada a nadie."},
        ],
        "words": [
            {"lexemeId": "lexemeasombr01", "forms": ["asombroso"]},
            {"lexemeId": "lexemeladrar01", "forms": ["ladrar"]},
        ],
    }
    payload.update(overrides)
    return payload


def test_a_well_formed_story_is_read_whole():
    written = parse_reply(story(), WORDS)
    assert written.title == "El perro asombroso"
    assert len(written.parts) == 3
    assert written.parts[0].heading == "La panadería"
    assert written.forms["lexemeasombr01"] == ("asombroso",)
    assert written.unused([word["id"] for word in WORDS]) == ()


def test_a_synonym_reported_as_the_word_is_discarded_and_the_word_reads_as_unused():
    """**The first real call did exactly this**, and the first parser accepted it.

    Asked for `asombroso`, the model wrote a story without it and reported `sorprende` — a synonym
    that *is* in the text, so "does this string appear" passed. The reader marks what is reported,
    so the learner would have seen a different word highlighted and taught as the one they are
    learning. Silently teaching a falsehood is worse than an unmarked word.
    """
    written = parse_reply(story(
        parts=[
            {"heading": "Uno", "text": "Marcos se sorprende mucho al ver al perro."},
            {"heading": "Dos", "text": "El perro empezó a ladrar delante del mostrador."},
            {"heading": "Tres", "text": "Pagó con una moneda y se marchó."},
        ],
        words=[
            {"lexemeId": "lexemeasombr01", "forms": ["sorprende"]},
            {"lexemeId": "lexemeladrar01", "forms": ["ladrar"]},
        ],
    ), WORDS)
    assert "lexemeasombr01" not in written.forms
    assert written.unused([word["id"] for word in WORDS]) == ("lexemeasombr01",)
    # The word that really was used is untouched: one bad report does not cost the whole story.
    assert written.forms["lexemeladrar01"] == ("ladrar",)


def test_a_form_that_was_never_written_is_discarded():
    """The reader searches the text for this string. One that is not there would mark nothing."""
    written = parse_reply(story(words=[
        {"lexemeId": "lexemeasombr01", "forms": ["asombrosísimo"]},
    ]), WORDS)
    assert written.unused(["lexemeasombr01"]) == ("lexemeasombr01",)


def test_inflected_forms_are_kept():
    written = parse_reply(story(
        parts=[
            {"heading": "Uno", "text": "Vio una cosa asombrosa y otra más asombrosas todavía."},
            {"heading": "Dos", "text": "El perro ladró dos veces."},
            {"heading": "Tres", "text": "Nadie dijo nada."},
        ],
        words=[
            {"lexemeId": "lexemeasombr01", "forms": ["asombrosa", "asombrosas"]},
            {"lexemeId": "lexemeladrar01", "forms": ["ladró"]},
        ],
    ), WORDS)
    assert written.forms["lexemeasombr01"] == ("asombrosa", "asombrosas")
    assert written.forms["lexemeladrar01"] == ("ladró",)


def test_an_id_nobody_asked_about_is_dropped_rather_than_refused():
    """`clips/select.py`'s rule: a hallucinated id is a prompt bug, not a reason to lose a story."""
    written = parse_reply(story(words=[
        {"lexemeId": "lexemeasombr01", "forms": ["asombroso"]},
        {"lexemeId": "lexemenothing1", "forms": ["perro"]},
    ]), WORDS)
    assert set(written.forms) == {"lexemeasombr01"}


@pytest.mark.parametrize("payload, complaint", [
    ({"title": ""}, "no title"),
    ({"parts": []}, "between"),
    ({"parts": [{"heading": "One", "text": "Solo una parte."}]}, "between"),
    ({"words": "not a list"}, "did not say which words"),
])
def test_a_reply_that_ignored_the_shape_is_refused(payload, complaint):
    with pytest.raises(ValueError) as raised:
        parse_reply(story(**payload), WORDS)
    assert complaint in str(raised.value)


def test_a_part_too_long_to_fit_a_screen_is_refused():
    """Not a style preference: a part is drawn under a picture on one screen, and the reader's one
    promise is that it does not have to be scrolled."""
    with pytest.raises(ValueError, match="too long"):
        parse_reply(story(parts=[
            {"heading": "Uno", "text": "a" * (MAX_PART_CHARS + 1)},
            {"heading": "Dos", "text": "Corto."},
            {"heading": "Tres", "text": "Corto."},
        ]), WORDS)


def test_a_refusal_is_its_own_kind_of_answer():
    """Not a shape failure — the writer judged, so trying another model would only pay twice."""
    with pytest.raises(StoryRefused) as raised:
        parse_reply({"refused": True, "reason": "one of those words is a slur"}, WORDS)
    assert raised.value.reason == "one of those words is a slur"


@pytest.mark.parametrize("form, word, expected", [
    ("asombrosa", "asombroso", True),
    ("asombrosos", "asombroso", True),
    ("ladró", "ladrar", True),
    ("hormigas", "hormiga", True),
    ("empeñó", "empeñarse", True),
    ("sorprende", "asombroso", False),
    ("perro", "asombroso", False),
    ("casa", "hogar", False),
    # Accents are normalised away, so a form differing only in one still matches its word.
    ("panaderias", "panadería", True),
])
def test_whether_a_form_belongs_to_a_word(form, word, expected):
    assert is_form_of(form, word, word) is expected


def test_a_suppletive_form_is_a_known_false_negative():
    """Documented rather than fixed. `is_form_of` holds no language data and must not grow any;
    the cost is an unmarked word, which is visible, while the opposite error is silent."""
    assert is_form_of("fue", "ir", "ir") is False


def test_unused_names_every_word_the_story_did_not_reach():
    written = Written(title="t", emoji="", parts=(), forms={"a": ("x",)})
    assert written.unused(["a", "b", "c"]) == ("b", "c")
