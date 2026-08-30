"""The YAML editor is CodeMirror, and it must look like the rest of Acervo.

It replaced a hand-written surface: a transparent `<textarea>` laid over a separately rendered copy
of the same text. Two independent layouts had to agree pixel for pixel, and every way they could
disagree was a visible bug — text drawn over text, a selection that stopped short, typing that
landed somewhere else. CodeMirror draws the caret and the glyphs together, so that class of failure
is gone by construction rather than by a rule that has to be maintained.

What still has to be maintained is the look. The editor arrives with its own default theme, and
nothing forces it to use Acervo's palette or its mono face — so the theme is asserted here rather
than left to be noticed later, when the editor quietly stops matching the interface around it.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANE = ROOT / "web" / "src" / "YamlPane.tsx"
STYLES = ROOT / "web" / "src" / "styles.css"


def theme() -> str:
    source = PANE.read_text()
    start = source.index("const THEME = EditorView.theme(")
    return source[start:source.index("\n});", start)]


def test_the_editor_uses_the_interface_font_and_measure():
    """The same mono face and line box as every other code surface. CodeMirror's default is a
    generic monospace at a different size, which reads as a different application."""
    scroller = theme()
    assert 'fontFamily: "var(--mono)"' in scroller
    assert 'fontSize: "12.5px"' in scroller
    assert 'lineHeight: "18px"' in scroller


def test_the_document_colours_come_from_the_palette():
    """Keys, strings, numbers and comments in Acervo's colours, not CodeMirror's defaults."""
    source = PANE.read_text()
    start = source.index("const YAML_COLOURS = HighlightStyle.define(")
    colours = source[start:source.index("\n]);", start)]
    for token in ("propertyName", "tags.string", "tags.number", "tags.comment"):
        assert token in colours, f"{token} is no longer given a colour"
    # Every colour is a variable, so a palette change reaches the editor with everything else.
    for value in re.findall(r'color: "([^"]+)"', colours):
        assert value.startswith("var(--"), f"{value} is a literal, so the editor will drift from the theme"


def test_the_caret_and_selection_are_the_accent_colour():
    marked = theme()
    assert 'caretColor: "var(--core)"' in marked
    # Semi-transparent on purpose: an opaque band hides the characters it is meant to be marking.
    assert "color-mix(in srgb, var(--core) 26%, transparent)" in marked


def test_the_editor_fills_the_surface_that_bounds_it():
    """A composer gives the editor a bounded height; the editor has to take it, or it grows to its
    content and the pinned save bar is pushed off the screen again."""
    css = STYLES.read_text()
    assert ".code-scroll .cm-editor { height: 100%; }" in css
    assert 'height: "100%"' in theme()


def test_the_gutter_divider_is_declared_where_it_wins():
    """A CodeMirror theme rule outranks the stylesheet, so a divider set outside this block is
    overridden by the block's own `border: none` and simply never appears."""
    assert 'borderRight: "1px solid var(--rule-soft)"' in theme()
