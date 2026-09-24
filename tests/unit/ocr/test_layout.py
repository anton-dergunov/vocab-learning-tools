"""From an engine's words to a page: what `web/src/photoText.ts` hit-tests against.

Ported from the spike's own tests (`experiments/photo-capture/test_spike.py`) where the behaviour is
the same, and extended where the shipped shape says more — lines, sentence word ids, offsets.
"""

from __future__ import annotations

import re

from acervo.models.results import OcrWord
from acervo.ocr import layout
from acervo.ocr.segment import spans_of

WIDTH, HEIGHT = 1000, 500


def words(*lines: list[tuple[str, str | None]], paragraph_of=None) -> list[OcrWord]:
    """Words laid out one printed line after another, 100 px wide each, 40 px a line."""
    found = []
    for number, line in enumerate(lines):
        for column, (text, after) in enumerate(line):
            x, y = 10 + column * 110, 10 + number * 40
            found.append(OcrWord(
                text=text,
                polygon=((x, y), (x + 100, y), (x + 100, y + 30), (x, y + 30)),
                confidence=0.9 if text != "borroso" else 0.3,
                break_after=after,
                block=0,
                paragraph=paragraph_of(number) if paragraph_of else 0,
            ))
    return found


def full_stop(text: str) -> list[tuple[int, int]]:
    """A stand-in for SaT: a sentence ends at terminal punctuation followed by a space."""
    return spans_of(text, re.split(r"(?<=[.!?])\s+", text))


def test_a_word_hyphenated_across_a_line_break_is_one_word_with_two_polygons():
    page = layout.page(words(
        [("La", "space"), ("pala-", "eol")],
        [("bra", "space"), ("dicha.", "eol")],
    ), WIDTH, HEIGHT, full_stop)
    assert page["text"] == "La palabra dicha."
    joined = next(word for word in page["words"] if word["text"] == "palabra")
    assert len(joined["polygons"]) == 2
    assert page["text"][joined["start"]:joined["end"]] == "palabra"
    assert [line["wordIds"] for line in page["lines"]] == [
        ["w0", joined["id"]], [joined["id"], "w2"]
    ], "tapping either half finds it, on either line"


def test_vision_marking_the_hyphen_as_a_break_joins_it_too():
    page = layout.page(words(
        [("mun", "hyphen")],
        [("do.", "eol")],
    ), WIDTH, HEIGHT, full_stop)
    assert page["text"] == "mundo."


def test_a_hyphen_before_a_capital_is_a_name_not_a_broken_word():
    page = layout.page(words(
        [("Atelman-", "eol")],
        [("Fourcade", "space"), ("dijo.", "eol")],
    ), WIDTH, HEIGHT, full_stop)
    assert page["text"] == "Atelman- Fourcade dijo."


def test_punctuation_vision_reports_as_a_word_is_glued_to_the_word_before():
    page = layout.page(words([("Baile", None), (",", "space"), ("tango", None), (".", "eol")]),
                       WIDTH, HEIGHT, full_stop)
    assert page["text"] == "Baile, tango."
    assert [word["text"] for word in page["words"]] == ["Baile", ",", "tango", "."]


def test_a_paragraph_ends_a_line_whatever_break_the_engine_reported():
    page = layout.page(words(
        [("Capítulo", "space"), ("3", None)],
        [("Era", "space"), ("tarde.", "eol")],
        paragraph_of=lambda number: number,
    ), WIDTH, HEIGHT, full_stop)
    assert page["text"] == "Capítulo 3 Era tarde."
    assert len(page["lines"]) == 2


def test_sentences_name_their_words_and_their_offsets():
    page = layout.page(words(
        [("Se", "space"), ("fue.", "space"), ("Volvió", "space"), ("tarde.", "eol")],
    ), WIDTH, HEIGHT, full_stop)
    first, second = page["sentences"]
    assert (first["text"], first["wordIds"]) == ("Se fue.", ["w0", "w1"])
    assert (second["text"], second["wordIds"]) == ("Volvió tarde.", ["w2", "w3"])
    assert page["text"][second["start"]:second["end"]] == "Volvió tarde."


def test_the_first_sentence_is_cut_off_when_it_opens_in_lower_case_and_the_last_when_unterminated():
    page = layout.page(words(
        [("y", "space"), ("se", "space"), ("fue.", "space"), ("Luego", "space"), ("volvió", "eol")],
    ), WIDTH, HEIGHT, full_stop)
    first, last = page["sentences"]
    assert (first["truncatedStart"], first["truncatedEnd"]) == (True, False)
    assert (last["truncatedStart"], last["truncatedEnd"]) == (False, True)


def test_an_opening_mark_is_not_a_cut():
    page = layout.page(words([("¿Qué", "space"), ("hora", "space"), ("es?", "eol")]),
                       WIDTH, HEIGHT, full_stop)
    assert page["sentences"][0]["truncatedStart"] is False
    assert page["sentences"][0]["truncatedEnd"] is False


def test_coordinates_are_normalised_to_the_image_and_lines_are_outlined():
    page = layout.page(words([("Hola", "space"), ("mundo.", "eol")]), WIDTH, HEIGHT, full_stop)
    assert page["words"][0]["polygons"] == [[[0.01, 0.02], [0.11, 0.02], [0.11, 0.08], [0.01, 0.08]]]
    assert page["lines"][0]["polygon"] == [[0.01, 0.02], [0.22, 0.02], [0.22, 0.08], [0.01, 0.08]]


def test_a_low_confidence_word_is_kept_and_says_so():
    page = layout.page(words([("un", "space"), ("borroso", "eol")]), WIDTH, HEIGHT, full_stop)
    assert page["words"][1]["confidence"] == 0.3


def test_a_page_with_no_text_is_an_empty_page():
    assert layout.page([], WIDTH, HEIGHT, full_stop) == {"text": "", "words": [], "lines": [], "sentences": []}


def test_spans_are_found_in_order_and_trimmed():
    text = "Uno. Uno. Dos."
    assert spans_of(text, ["Uno. ", "Uno. ", "Dos."]) == [(0, 4), (5, 9), (10, 14)]
