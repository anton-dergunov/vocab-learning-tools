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


@pytest.mark.parametrize("stylesheet", STYLESHEETS, ids=lambda path: path.name)
def test_the_three_layers_declare_one_line_height(stylesheet):
    """A single rule sets the metric for the gutter and for the pre/textarea pair. Two different
    line heights is the same bug in a different place, so keep them declared together."""
    text = stylesheet.read_text()
    for selector in [".gutter {", ".code-scroll pre, .code-scroll textarea {"]:
        start = text.index(selector)
        block = text[start:text.index("}", start)]
        assert "line-height: 20px" in block, f"{selector} no longer states the shared line height"
