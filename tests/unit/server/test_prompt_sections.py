"""Optional sections in a tracked prompt, and the two ways they could go wrong quietly.

A prompt is content, not code, and a setting that includes or drops part of one is still content —
so the mechanism is markers a person can read in the file rather than a template engine. What is
worth testing is the part that could fail silently: a section stuck on, and a marker nobody supplies.
"""

from __future__ import annotations

import pytest

from acervo.errors import ApiError
from acervo.services.prompts import forget_prompts, prompt_text, sections

TEXT = """Always said.

<!-- if: selfContainedOnly -->
Only sometimes said.
<!-- end -->

Also always said.
"""


def test_a_section_is_kept_when_its_option_is_on():
    assert "Only sometimes said." in sections(TEXT, {"selfContainedOnly": True})


def test_a_section_is_dropped_when_its_option_is_off():
    kept = sections(TEXT, {"selfContainedOnly": False})
    assert "Only sometimes said." not in kept
    assert "Always said." in kept and "Also always said." in kept
    assert "<!--" not in kept, "the markers are not sent to the model either"


def test_an_option_nothing_supplies_is_refused_rather_than_assumed():
    """A misspelled marker that silently stopped being sent is the kind of thing nobody notices for
    months, and these files change together with the code that reads them."""
    with pytest.raises(ApiError) as raised:
        sections("<!-- if: typoed -->\nx\n<!-- end -->\n", {"selfContainedOnly": True})
    assert raised.value.code == "prompt_option_unknown"


@pytest.mark.parametrize("broken", [
    "<!-- if: opt -->\nx\n",                   # no end
    "<!-- if: opt -->x\n<!-- end -->\n",       # text on the marker line
    "x\n<!-- end -->\n",                       # an end with no beginning
])
def test_a_marker_the_reader_cannot_parse_is_refused(broken):
    """Left alone it would reach the model as literal HTML, and its section would be silently
    *always on* — which is the failure worth catching, not the stray comment."""
    with pytest.raises(ApiError) as raised:
        sections(broken, {"opt": False})
    assert raised.value.code == "prompt_marker_malformed"


def test_a_prompt_with_no_markers_needs_no_options():
    assert sections("Just text.\n", {}) == "Just text."


def test_the_cache_holds_the_file_rather_than_the_rendered_text(tmp_path):
    """The trap this shape exists to avoid: caching the *output* would make whichever setting
    arrived first stick for the life of the process, so one owner's choice would leak to the next."""
    forget_prompts()
    (tmp_path / "sample.md").write_text(TEXT, encoding="utf-8")

    on = prompt_text(tmp_path, "sample", {"selfContainedOnly": True})
    off = prompt_text(tmp_path, "sample", {"selfContainedOnly": False})
    again = prompt_text(tmp_path, "sample", {"selfContainedOnly": True})

    assert "Only sometimes said." in on
    assert "Only sometimes said." not in off
    assert again == on
    forget_prompts()


def test_the_shipped_clip_prompt_carries_exactly_the_option_the_service_supplies(tmp_path):
    """The two halves of this are a file and a call site, in different languages' worth of distance
    from each other. `selfContainedOnly` appearing in one and not the other is a live bug."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    forget_prompts()
    off = prompt_text(root / "prompts", "acervo_clip_select", {"selfContainedOnly": False})
    on = prompt_text(root / "prompts", "acervo_clip_select", {"selfContainedOnly": True})
    forget_prompts()

    assert len(on) > len(off)
    assert "followed on its own" in on and "followed on its own" not in off
    # Off is the default, and it has to read as a whole prompt rather than as one with a hole in it.
    assert off.startswith("You choose recorded speech")
    assert "## What makes a clip good" in off
    assert "<!--" not in off and "<!--" not in on
