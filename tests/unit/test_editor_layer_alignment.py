"""The YAML editor lays a transparent `<textarea>` over a highlighted copy of the same text, beside
a column of line numbers. All three must share one text metric.

Nothing in the DOM forces them to agree, and when they disagreed the failure was quiet rather than
obvious. The UA stylesheet declares `code { font-family: monospace }`, and a declaration beats an
inherited value, so the highlight rendered in the system mono face while the textarea used IBM Plex
Mono. Measured in Chrome that gave the highlight a 21px line box against the textarea's 20px: the
caret drifted a full line every twenty rows and selections landed off the text they covered.

Declaring every layer in one rule is what makes that impossible rather than merely fixed. The
application and the prototype must both carry it, per the rule that they change together.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
STYLESHEETS = [
    ROOT / "web" / "src" / "styles.css",
    ROOT / "design" / "ui-prototype" / "acervo.css",
]
LAYERS = ".editor-grid .ln, .editor-grid textarea, .editor-grid .ln-no"


def _declared(stylesheet, selector, prop):
    text = stylesheet.read_text()
    # Anchored on the opening brace: one selector is a prefix of another here, and matching the
    # bare text would read the wrong rule and quietly report the wrong value.
    start = text.index(f"\n{selector} {{")
    block = text[text.index("{", start) + 1:text.index("}", start)]
    for declaration in block.split(";"):
        name, _, value = declaration.partition(":")
        if name.strip() == prop:
            return value.strip()
    raise AssertionError(f"{selector} in {stylesheet.name} no longer declares {prop}")


@pytest.mark.parametrize("stylesheet", STYLESHEETS, ids=lambda path: path.name)
def test_every_layer_is_declared_on_one_metric(stylesheet):
    """One rule for all three, so a change cannot reach one layer and miss another."""
    assert LAYERS in stylesheet.read_text(), "the editor layers no longer share one declaration"
    for prop in ("font-family", "font-size", "line-height"):
        assert _declared(stylesheet, LAYERS, prop), f"{prop} is no longer stated for every layer"


@pytest.mark.parametrize("stylesheet", STYLESHEETS, ids=lambda path: path.name)
def test_the_line_box_stays_close_to_the_caret(stylesheet):
    """The caret is drawn over the font's content area — about 1.26x the font size, and not
    something CSS can resize — while the selection band is the full line box. Let the line box grow
    far beyond the caret and the band starts reading as floating above the text it covers."""
    line_height = float(_declared(stylesheet, LAYERS, "line-height").removesuffix("px"))
    font_size = float(_declared(stylesheet, LAYERS, "font-size").removesuffix("px"))
    caret = font_size * 1.26
    assert caret <= line_height <= caret + 3, (
        f"a {line_height}px line box around a ~{caret:.1f}px caret leaves "
        f"{(line_height - caret) / 2:.1f}px of band on each side"
    )


@pytest.mark.parametrize("stylesheet", STYLESHEETS, ids=lambda path: path.name)
def test_an_empty_line_still_occupies_its_row(stylesheet):
    """A blank line is an empty element. Without a floor it collapses to nothing and every line
    below it sits one row higher than the caret that belongs to it."""
    assert _declared(stylesheet, ".editor-grid .ln, .editor-grid textarea", "min-height") == "18px"
