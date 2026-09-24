"""Which earlier pictures a story's later picture is drawn from — by who and where, never by position.

The case the module exists for is *La invención del Post-it*: one man in a laboratory, then years
later a different man in a church. A positional rule hands the second man the first man's face.
"""

from __future__ import annotations

import pytest

from acervo.stories import continuity
from acervo.stories.continuity import Reference


def labels(*parts: tuple[list[str], str, str]) -> dict:
    characters = sorted({one for who, _scene, _change in parts for one in who})
    scenes = sorted({scene for _who, scene, _change in parts})
    return {
        "characters": [{"id": one, "description": f"{one} as drawn"} for one in characters],
        "scenes": [{"id": one, "description": f"the {one}"} for one in scenes],
        "parts": [{"characters": who, "scene": scene, "change": change}
                  for who, scene, change in parts],
    }


POST_IT = continuity.parse_reply(labels(
    (["spencer"], "lab", ""),
    (["art_fry"], "church", ""),
    (["spencer", "art_fry"], "lab", ""),
    (["spencer"], "lab", "years later; the lab is covered in yellow notes"),
), 4)


def test_a_part_with_nobody_and_nowhere_seen_before_is_given_nothing():
    assert continuity.references(POST_IT, 0) == ()
    assert continuity.references(POST_IT, 1) == (), "a different man in a different place"


def test_each_returning_person_and_place_is_served_by_the_last_picture_that_showed_it():
    assert continuity.references(POST_IT, 2) == (
        Reference(0, ("spencer", "scene:lab")),
        Reference(1, ("art_fry",)),
    )
    # Spencer and the lab were both last seen in part 3, so one picture serves both.
    assert continuity.references(POST_IT, 3) == (Reference(2, ("spencer", "scene:lab")),)


def test_a_part_whose_picture_is_missing_is_passed_over_for_the_one_before_it():
    chosen = continuity.references(POST_IT, 3, drawn=lambda part: part != 2)
    assert chosen == (Reference(0, ("spencer", "scene:lab")),)


def test_never_more_than_two_and_the_most_recent_are_kept():
    many = continuity.parse_reply(labels(
        (["ana"], "street", ""), (["luis"], "flat", ""), (["eva"], "park", ""),
        (["ana", "luis", "eva"], "street", ""),
    ), 4)
    chosen = continuity.references(many, 3)
    assert [reference.part for reference in chosen] == [1, 2]
    assert continuity.MAX_REFERENCES == 2


def test_the_prompt_says_who_to_keep_whose_place_it_is_and_who_must_not_be_drawn():
    chosen = continuity.references(POST_IT, 3)
    text = continuity.reference_lines(POST_IT, 3, chosen)
    assert "Reference 1 is the picture from part 3" in text
    assert "SPENCER" in text and "same face" in text
    assert "This moment is in the same place" in text
    assert "It also shows ART FRY, who is not in this moment: do not draw them." in text
    assert "yellow notes" in text and "follow this and not the reference" in text


def test_a_reference_chosen_for_a_person_says_its_setting_is_not_this_one():
    chosen = continuity.references(POST_IT, 2)
    text = continuity.reference_lines(POST_IT, 2, chosen)
    second = text.split("Reference 2")[1]
    assert "Its setting is not where this moment happens" in second


def test_the_template_carries_the_lines_and_the_picture():
    chosen = continuity.references(POST_IT, 3)
    text = continuity.compose("{references}\n\nThe new picture: {picture}", POST_IT, 3, chosen,
                              "A man in a lab.")
    assert text.startswith("Reference 1")
    assert text.endswith("The new picture: A man in a lab.")


@pytest.mark.parametrize("payload, problem", [
    ({"characters": [], "scenes": [{"id": "lab"}], "parts": [{"scene": "lab"}]}, "2 parts"),
    ({"characters": [], "scenes": [{"id": "lab"}],
      "parts": [{"characters": ["fry"], "scene": "lab"}] * 2}, "never declared"),
    ({"characters": [], "scenes": [{"id": "lab"}],
      "parts": [{"scene": "church"}] * 2}, "never declared"),
    ({"characters": [{"id": "Spencer Silver"}], "scenes": [], "parts": []}, "slug"),
    ("not an object", "JSON object"),
])
def test_labels_that_do_not_hold_their_shape_are_refused_by_name(payload, problem):
    with pytest.raises(ValueError, match=problem):
        continuity.parse_reply(payload, 2)
