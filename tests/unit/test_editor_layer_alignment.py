"""The YAML editor stacks three text layers that must share one text metric: a gutter, a
syntax-highlighted `<pre>`, and the transparent `<textarea>` that actually holds the caret.

They are laid out independently, so nothing in the DOM forces them to agree — and when they
disagreed the failure was quiet and confusing rather than obvious. The UA stylesheet declares
`code { font-family: monospace }`, and a declaration beats an inherited value, so the highlight
layer rendered in the system mono face while the textarea used IBM Plex Mono. Measured in Chrome,
that gave the `<pre>` a 21px line box against the textarea's 20px: the caret drifted a full line
every twenty rows and selections landed off the text they covered.

`font: inherit` on the `code` element is what keeps the layers on one metric. The application and
the prototype must both carry it, per the rule that they change together.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
STYLESHEETS = [
    ROOT / "web" / "src" / "styles.css",
    ROOT / "design" / "ui-prototype" / "acervo.css",
]


@pytest.mark.parametrize("stylesheet", STYLESHEETS, ids=lambda path: path.name)
def test_highlight_layer_shares_the_textarea_font(stylesheet):
    assert ".code-scroll pre code { font: inherit; }" in stylesheet.read_text()


def _declared(stylesheet, selector, prop):
    text = stylesheet.read_text()
    start = text.index(selector)
    block = text[start:text.index("}", start)]
    for declaration in block.split(";"):
        name, _, value = declaration.partition(":")
        if name.strip() == prop:
            return value.strip()
    raise AssertionError(f"{selector} in {stylesheet.name} no longer declares {prop}")


EDITOR_LAYERS = [".gutter {", ".code-scroll pre, .code-scroll textarea {"]


@pytest.mark.parametrize("stylesheet", STYLESHEETS, ids=lambda path: path.name)
def test_the_three_layers_share_one_line_height(stylesheet):
    """Whatever the value is, the gutter and the pre/textarea pair must state the same one. Two
    different line heights is the same drift in a different place."""
    values = {selector: _declared(stylesheet, selector, "line-height") for selector in EDITOR_LAYERS}
    assert len(set(values.values())) == 1, f"the editor layers disagree on line-height: {values}"


@pytest.mark.parametrize("stylesheet", STYLESHEETS, ids=lambda path: path.name)
def test_the_line_box_stays_close_to_the_caret(stylesheet):
    """The caret is drawn over the font's content area — about 1.26x the font size, and not
    something CSS can resize — while the selection band is the full line box. Let the line box grow
    far beyond the caret and the band starts reading as floating above the text it covers."""
    line_height = float(_declared(stylesheet, EDITOR_LAYERS[1], "line-height").removesuffix("px"))
    font_size = float(_declared(stylesheet, EDITOR_LAYERS[1], "font-size").removesuffix("px"))
    caret = font_size * 1.26
    assert caret <= line_height <= caret + 3, (
        f"a {line_height}px line box around a ~{caret:.1f}px caret leaves "
        f"{(line_height - caret) / 2:.1f}px of band on each side"
    )
