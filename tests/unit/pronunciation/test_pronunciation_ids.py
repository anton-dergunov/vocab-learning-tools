"""The derived id of a pronunciation, and its agreement with the interface.

The other half of this check is `web/src/ids.test.ts`, which pins the same vectors against
`web/src/ids.ts`. When the two disagree the symptom is a second clip row for one field rather than an
error, so nothing catches it but this pair of tests.
"""

from acervo.clips.ids import clip_example_id
from acervo.images.ids import image_prompt_id
from acervo.pronunciation.ids import ID_LENGTH, pronunciation_id


def test_the_derived_id_is_the_one_the_interface_derives_too():
    assert pronunciation_id("lexeme", "lexemepicar0001") == "hl08nur0wl9h0n1"
    assert pronunciation_id("example", "oj3y4cakuelbgrd") == "3p733vjo4detewl"
    # Empty inputs exercise the padding, which is where a hand-written SHA-256 goes wrong.
    assert pronunciation_id("sense", "") == "6nv0f3exl21x8za"
    assert pronunciation_id("", "") == "wjkov1ozu2c9fj5"


def test_ids_are_acervo_shaped_and_keyed_on_what_is_read():
    minted = pronunciation_id("example", "oj3y4cakuelbgrd")
    assert len(minted) == ID_LENGTH and minted.isalnum() and minted.islower()
    assert minted != pronunciation_id("attestation", "oj3y4cakuelbgrd")


def test_a_pronunciation_id_is_neither_a_picture_id_nor_a_clip_id():
    assert pronunciation_id("sense", "sensepicaritch0") != image_prompt_id("sensepicaritch0")
    assert pronunciation_id("sense", "sensepicaritch0") != clip_example_id("sensepicaritch0", "")
