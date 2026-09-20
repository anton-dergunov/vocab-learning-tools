"""Cutting a part into passages: what `tile` guarantees whatever the model did.

The one property that matters is the first: however badly the model copies, **the passages join back
to the part exactly**, so what a voice reads is always what the story says. The rest are the ways a
real model can get that wrong — `experiments/story-audio-segmentation/` measured 25 clean answers in
25, so each of these is a case constructed on purpose, not one that was seen.
"""

from __future__ import annotations

import pytest

from acervo.stories.narrate import (
    MAX_SEGMENTS, Segment, chunks, parse_reply, tile,
)

TEXT = (
    "Cada martes, Mateo abría su taller. Durante cincuenta años, su familia salaba pescado. "
    "«¡Qué frío!», dijo él. Nadie contestó."
)


def said(*texts: str, direction: str = "calm") -> list[Segment]:
    return [Segment(text=one, direction=direction) for one in texts]


def joined(tiled) -> str:
    return "".join(segment.text for segment in tiled.segments)


def test_a_faithful_answer_is_kept_as_it_came_and_the_whitespace_goes_to_the_passage_before():
    tiled = tile(TEXT, said(
        "Cada martes, Mateo abría su taller.",
        "Durante cincuenta años, su familia salaba pescado.",
        "«¡Qué frío!», dijo él.",
        "Nadie contestó.",
    ))

    assert joined(tiled) == TEXT
    assert (tiled.dropped, tiled.filled) == (0, 0)
    assert [one.direction for one in tiled.segments] == ["calm"] * 4
    assert tiled.segments[0].text == "Cada martes, Mateo abría su taller. ", "the space stays with the sentence"
    assert not tiled.segments[-1].text.endswith(" ")


def test_a_sentence_the_model_left_out_is_read_undirected_rather_than_skipped():
    tiled = tile(TEXT, said(
        "Cada martes, Mateo abría su taller.",
        "«¡Qué frío!», dijo él.",
        "Nadie contestó.",
    ))

    assert joined(tiled) == TEXT
    assert (tiled.dropped, tiled.filled) == (0, 1)
    gap = tiled.segments[1]
    assert gap.text.strip() == "Durante cincuenta años, su familia salaba pescado."
    assert gap.direction == "", "nobody said how to read it, so the voice reads it its own way"


def test_a_sentence_the_model_reworded_is_dropped_and_the_original_is_read_instead():
    tiled = tile(TEXT, said(
        "Cada martes, Mateo abría su taller.",
        "Durante medio siglo, su familia salaba pescado.",  # not in the text
        "«¡Qué frío!», dijo él.",
        "Nadie contestó.",
    ))

    assert joined(tiled) == TEXT
    assert (tiled.dropped, tiled.filled) == (1, 1)
    assert "medio siglo" not in joined(tiled), "the model's words never reach the voice"
    assert "cincuenta años" in joined(tiled)


def test_a_line_break_turned_into_a_space_still_matches():
    text = "Primera frase.\nSegunda frase."

    tiled = tile(text, said("Primera frase.", "Segunda frase."))

    assert joined(tiled) == text
    assert (tiled.dropped, tiled.filled) == (0, 0)


def test_a_quotation_mark_the_model_left_off_is_glued_on_not_sent_to_a_voice_alone():
    text = "Dijo: «Hola». Luego se fue."

    tiled = tile(text, said("Dijo: «Hola", "Luego se fue."))

    assert joined(tiled) == text
    assert (tiled.dropped, tiled.filled) == (0, 0), "a gap with no word in it is not a passage"
    assert tiled.segments[0].text.startswith("Dijo: «Hola».")


def test_passages_out_of_order_lose_the_one_that_ran_backwards():
    tiled = tile(TEXT, said(
        "Nadie contestó.",
        "Cada martes, Mateo abría su taller.",
    ))

    assert joined(tiled) == TEXT
    assert tiled.dropped == 1, "the second is behind where the first ended, so it is not found again"


def test_an_answer_that_matches_nothing_is_the_whole_part_undirected():
    tiled = tile(TEXT, said("Something else entirely."))

    assert joined(tiled) == TEXT
    assert len(tiled.segments) == 1
    assert tiled.segments[0].direction == ""


def test_leading_and_trailing_words_the_model_missed_are_kept():
    tiled = tile("Antes. Medio. Después.", said("Medio."))

    assert joined(tiled) == "Antes. Medio. Después."
    assert [one.direction for one in tiled.segments] == ["", "calm", ""]


@pytest.mark.parametrize("text", ["", "   ", "¿?"])
def test_text_with_nothing_to_say_still_joins_back(text):
    assert joined(tile(text, said("Hola."))) == text


# ── the reply's shape ───────────────────────────────────────────────────────


def test_a_reply_is_read_into_passages_and_directions_are_kept_short_and_on_one_line():
    segments = parse_reply({"segments": [
        {"text": "  Hola.  ", "direction": "Warm\nand   slow. " + "x" * 400},
        {"text": "Adiós."},
    ]})

    assert segments[0].text == "Hola."
    assert "\n" not in segments[0].direction and len(segments[0].direction) <= 200
    assert segments[1].direction == ""


@pytest.mark.parametrize("payload, why", [
    (None, "not a JSON object"),
    ({}, "no segments"),
    ({"segments": []}, "no segments"),
    ({"segments": "Hola."}, "no segments"),
    ({"segments": ["Hola."]}, "not an object"),
    ({"segments": [{"text": "  "}]}, "empty"),
    ({"segments": [{"text": "x"}] * (MAX_SEGMENTS + 1)}, "more than a part can hold"),
])
def test_a_reply_that_does_not_hold_its_shape_is_refused(payload, why):
    with pytest.raises(ValueError, match=why):
        parse_reply(payload)


# ── a part too long for one call ────────────────────────────────────────────


def test_a_part_that_fits_is_one_passage_with_no_direction():
    assert chunks(TEXT) == (Segment(text=TEXT),)


def test_a_part_too_long_for_a_voice_is_cut_at_sentence_ends_in_bytes_not_characters():
    sentence = "La cañería sonó tres veces. "  # accented: more bytes than characters
    text = (sentence * 200).rstrip()

    pieces = chunks(text, limit=1000)

    assert len(pieces) > 1
    assert "".join(one.text for one in pieces) == text
    assert all(len(one.text.encode("utf-8")) <= 1000 for one in pieces)
    assert all(one.text.rstrip().endswith(".") for one in pieces), "never cut inside a sentence"
    assert all(one.direction == "" for one in pieces)
