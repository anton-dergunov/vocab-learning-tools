"""The derived id of a clip example, and its agreement with the interface.

The other half of this check is `web/src/ids.test.ts`, which pins the same vectors against
`web/src/ids.ts`. Two writers converge on one row only because both compute the same id, and when
they disagree the symptom is a duplicate example rather than an error — so nothing catches it but
this pair of tests.
"""

from acervo.clips.ids import ID_LENGTH, clip_example_id
from acervo.images.ids import image_prompt_id

SENSE = "sensepicaritch0"
SEGMENT = "seg_1f4c9a2b7e6d5c3a0b91"


def test_the_derived_id_is_the_one_the_interface_derives_too():
    assert clip_example_id(SENSE, SEGMENT) == "6b34r20hqwnhbwj"
    assert clip_example_id("oj3y4cakuelbgrd", "seg_0000000000000000000") == "g8wb7iyop0teah3"
    # Empty inputs exercise the padding, which is where a hand-written SHA-256 goes wrong.
    assert clip_example_id(SENSE, "") == "qnfybb75s2smt0o"
    assert clip_example_id("", "") == "39upl9iwx14c6jl"


def test_ids_are_acervo_shaped_and_stable():
    minted = clip_example_id(SENSE, SEGMENT)
    assert len(minted) == ID_LENGTH
    assert minted.isalnum() and minted.islower()
    assert minted == clip_example_id(SENSE, SEGMENT)


def test_the_pair_is_the_identity_rather_than_the_sense_alone():
    """A sense may hold clips from several segments; two writers picking one segment may not."""
    first = clip_example_id(SENSE, SEGMENT)
    assert first != clip_example_id(SENSE, "seg_ffffffffffffffffffff")
    assert first != clip_example_id("sensepicarchop0", SEGMENT)


def test_a_clip_id_is_not_a_picture_id():
    """Separate namespaces, so one sense's picture and its clip can never collide."""
    assert clip_example_id(SENSE, "") != image_prompt_id(SENSE)
