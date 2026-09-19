"""The other two calls' contracts, and the one style rule the story pipeline has of its own."""

from __future__ import annotations

import pytest

from acervo.stories import illustrate, types
from acervo.stories.translate import parse_reply as parse_translation
from acervo.stories.write import Part

PARTS = (
    Part("La panadería", "Marcos vio un perro asombroso."),
    Part("El pan", "El perro empezó a ladrar."),
    Part("La cuenta", "Pagó con una moneda."),
)


def test_a_translation_is_read_when_it_matches_part_for_part():
    done = parse_translation({
        "title": "The amazing dog",
        "parts": [
            {"heading": "The bakery", "text": "Marcos saw an amazing dog."},
            {"heading": "The bread", "text": "The dog started to bark."},
            {"heading": "The bill", "text": "It paid with a coin."},
        ],
    }, PARTS)
    assert done.title == "The amazing dog"
    assert done.parts[1].text == "The dog started to bark."


@pytest.mark.parametrize("count", [2, 4])
def test_a_translation_with_the_wrong_number_of_parts_is_refused(count):
    """The failure this exists for is not "a bad translation" — it is every later translation
    landing under the wrong picture, which reads as a bad translation and is nearly impossible to
    diagnose from the page."""
    with pytest.raises(ValueError, match="3 parts"):
        parse_translation(
            {"title": "t", "parts": [{"text": f"part {i}"} for i in range(count)]}, PARTS
        )


def test_an_empty_translated_part_is_refused():
    with pytest.raises(ValueError, match="empty"):
        parse_translation({"title": "t", "parts": [
            {"text": "one"}, {"text": "   "}, {"text": "three"},
        ]}, PARTS)


def test_briefs_are_read_one_per_part():
    briefed = illustrate.parse_reply({
        "cast": "MARCOS: a thin man in a green jacket.",
        "world": "A Spanish street on a Saturday morning.",
        "parts": [{"brief": f"brief {i}"} for i in range(3)],
    }, PARTS)
    assert briefed.cast.startswith("MARCOS")
    assert len(briefed.briefs) == 3


def test_briefs_that_do_not_cover_every_part_are_refused():
    with pytest.raises(ValueError, match="3 parts"):
        illustrate.parse_reply({"parts": [{"brief": "only one"}]}, PARTS)


def test_the_style_is_appended_to_the_brief_rather_than_asked_for_in_it():
    """`images/compose.py`'s rule, and the reason the brief prompt forbids naming a style: the same
    brief in another style has to be one substitution, not another call."""
    style = types.load_types()  # noqa: F841 — loaded to prove the table reads
    from acervo.images.styles import load_styles

    drawn = illustrate.compose("A dog sits outside a bakery", load_styles()["comic-book"])
    assert drawn.startswith("A dog sits outside a bakery.")
    assert illustrate.FRAME in drawn
    assert "no letters, words, numbers" in drawn


def test_one_story_gets_one_style_for_every_part():
    """The opposite of a sense image, where variety across a word's senses is the whole point. Four
    pictures in four styles do not read as four parts of one story."""
    table = types.load_types()
    funny = table["funny"]
    chosen = {table.style_for(funny, "storyabc123456") for _ in range(5)}
    assert len(chosen) == 1, "the style must not move between parts of one story"
    assert chosen.pop() in funny.styles


def test_a_type_whose_styles_are_all_switched_off_still_draws_something():
    """The owner switched those styles off, not this kind of story."""
    table = types.load_types()
    chosen = table.style_for(table["funny"], "storyabc123456", allowed={"surrealism"})
    assert chosen == "surrealism"


def test_every_style_a_type_names_actually_exists():
    """The two tracked files are edited separately, so nothing but this notices a typo — and a
    styleId that names nothing would draw in no style at all."""
    from acervo.images.styles import load_styles

    known = {style.id for style in load_styles().styles}
    for story_type in types.load_types().types:
        unknown = [one for one in story_type.styles if one not in known]
        assert not unknown, f"{story_type.id} names unknown styles {unknown}"
        assert story_type.styles, f"{story_type.id} offers no styles"
        assert story_type.brief, f"{story_type.id} has no direction to give the writer"
