"""Every surface that can hold more than fits on a screen must be bounded and must scroll.

Neither the settings dialog nor the add sheet was. Both declared `overflow: hidden` with no height
limit, which is harmless while the contents are short and silently fatal once they are not: the
surface grows past the window and its own title and buttons become unreachable. It happened twice,
so the shape is now a contract shared by the settings overlay and the composer.

The fix has two halves and needs both. A bound without a scrolling body just clips; a scrolling body
without a bound never overflows, so it never scrolls. And the body must be allowed to shrink — a
flex item defaults to `min-height: auto` and refuses to go below its content, which reintroduces the
clipping through the back door.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "web" / "src" / "styles.css"
PROTOTYPE = ROOT / "design" / "ui-prototype" / "acervo.css"


def declarations(stylesheet: pathlib.Path, selector: str) -> dict[str, str]:
    text = re.sub(r"/\*.*?\*/", "", stylesheet.read_text(), flags=re.S)
    start = text.index(f"\n{selector} {{")
    body = text[text.index("{", start) + 1:text.index("}", start)]
    found = {}
    for declaration in body.split(";"):
        name, _, value = declaration.partition(":")
        if name.strip() and value.strip():
            found[name.strip()] = value.strip()
    return found


# ── the settings overlay ─────────────────────────────────────────────────

def test_the_settings_dialog_is_bounded_by_the_window():
    settings = declarations(APP, ".settings")
    assert "max-height" in settings, "the dialog can grow past the screen again"
    assert "100%" in settings["max-height"] or "vh" in settings["max-height"]
    assert settings.get("display") == "flex"
    assert settings.get("flex-direction") == "column"


def test_the_settings_panel_scrolls_rather_than_clipping():
    body = declarations(APP, ".settings-body")
    assert body.get("overflow-y") == "auto", "settings content taller than the dialog is unreachable"
    assert body.get("min-height") == "0"
    assert body.get("overscroll-behavior") == "contain"


def test_the_settings_header_and_tabs_do_not_scroll_away():
    assert declarations(APP, ".settings header").get("flex") == "none"
    assert "none" in declarations(APP, ".settings-nav").get("flex", "")


# ── the composer ─────────────────────────────────────────────────────────
# Both stylesheets, because the prototype is the design and they change together.

@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_composer_is_a_bounded_column(stylesheet):
    composer = declarations(stylesheet, ".composer")
    assert composer.get("display") == "flex"
    assert composer.get("flex-direction") == "column"
    # It fills what contains it rather than sizing to its contents, which is what gives the body
    # something to scroll inside.
    assert composer.get("height") == "100%"
    assert composer.get("min-height") == "0"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_composer_body_is_the_only_thing_that_scrolls(stylesheet):
    body = declarations(stylesheet, ".composer-body")
    assert body.get("overflow-y") == "auto"
    assert body.get("min-height") == "0", "a flex item will not shrink below its content without this"
    assert body.get("overscroll-behavior") == "contain"
    # The region around a composer must not scroll too, or the pinned bars drift out of view.
    assert declarations(stylesheet, ".main.composing").get("overflow") == "hidden"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_composer_head_and_actions_stay_put(stylesheet):
    assert declarations(stylesheet, ".composer-head").get("flex") == "none"
    assert declarations(stylesheet, ".composer-actions").get("flex") == "none"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_editor_takes_the_height_instead_of_nesting_a_second_scrollbar(stylesheet):
    fill = declarations(stylesheet, ".composer-body.fill")
    assert fill.get("overflow") == "hidden", "two scroll regions for one document"
    assert declarations(stylesheet, ".composer-body.fill .code-scroll").get("min-height") == "0"


# ── long lines ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_a_long_line_wraps_by_default(stylesheet):
    wrapped = declarations(stylesheet, ".code-scroll.wrap .ln, .code-scroll.wrap textarea")
    assert wrapped.get("white-space") == "pre-wrap"
    # Without this a single unbroken token — a URL, a long id — still escapes the column.
    assert wrapped.get("overflow-wrap") == "anywhere"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_grid_is_wider_than_the_container_when_wrapping_is_off(stylesheet):
    """Scrolling needs something to scroll across. Sizing the grid to its content is what gives
    `.code-scroll` an overflow to move through, rather than clipping the line where it runs out."""
    grid = declarations(stylesheet, ".code-scroll:not(.wrap) .editor-grid")
    assert grid.get("width") == "max-content"
    assert declarations(stylesheet, ".editor-grid").get("min-width") == "100%"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_textarea_takes_its_height_from_the_content_rather_than_a_script(stylesheet):
    """The height used to be measured with `scrollHeight` and set in an effect keyed on the text, so
    resizing the window rewrapped the content without rewrapping the box: the highlight was clipped
    to a stale height while the textarea above it laid out correctly — invisible, selectable text.
    Stretching it over the grid rows means the content sizes the box and a resize just works."""
    textarea = declarations(stylesheet, ".editor-grid textarea")
    assert textarea.get("height") == "100%"
    assert declarations(stylesheet, ".editor-grid").get("display") == "grid"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_a_line_number_sits_in_its_line_own_row(stylesheet):
    """One row per logical line is what lets a number stay beside a line that wraps to three."""
    assert declarations(stylesheet, ".ln-no").get("position") == "sticky"
    assert declarations(stylesheet, ".ln-no").get("grid-column") == "1"
    assert declarations(stylesheet, ".code-scroll.numbered .ln").get("grid-column") == "2"
