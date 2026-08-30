"""The settings dialog holds more than fits on a screen, so it has to be bounded and scrollable.

It was neither. `.settings` declared `overflow: hidden` with no height limit, which is harmless
while the contents are short and silently fatal once they are not: the moment vocabularies and
topics became editable the dialog grew past the window, and everything below the fold — the topic
list, sign out, the delete confirmation — could not be reached or even seen.

The fix has two halves and needs both. A bound on the dialog without a scrolling body just clips;
a scrolling body without a bound never overflows in the first place, so it never scrolls.
"""

import pathlib

STYLESHEET = pathlib.Path(__file__).resolve().parents[2] / "web" / "src" / "styles.css"


def declarations(selector: str) -> dict[str, str]:
    text = STYLESHEET.read_text()
    start = text.index(f"\n{selector} {{")
    block = text[start:text.index("}", start)]
    found = {}
    for declaration in block.split(";"):
        name, _, value = declaration.partition(":")
        if name.strip() and value.strip():
            found[name.strip()] = value.strip()
    return found


def test_the_dialog_is_bounded_by_the_window():
    settings = declarations(".settings")
    assert "max-height" in settings, "the dialog can grow past the screen again"
    assert "100%" in settings["max-height"] or "vh" in settings["max-height"]
    # A fixed header and tab strip above a scrolling panel; grid or block would let the body size
    # to its content and push the bound out again.
    assert settings.get("display") == "flex"
    assert settings.get("flex-direction") == "column"


def test_the_panel_scrolls_rather_than_clipping():
    body = declarations(".settings-body")
    assert body.get("overflow-y") == "auto", "settings content taller than the dialog is unreachable"
    # The subtle half. A flex item defaults to `min-height: auto` and will not shrink below its
    # content, so without this the panel grows the dialog past its bound and is clipped by the
    # `overflow: hidden` above it — overflow-y on its own scrolls nothing.
    assert body.get("min-height") == "0"
    # Without this a scroll that reaches the end keeps going in the page behind the dialog.
    assert body.get("overscroll-behavior") == "contain"


def test_the_header_and_tabs_do_not_scroll_away():
    assert declarations(".settings header").get("flex") == "none"
    assert "none" in declarations(".settings-nav").get("flex", "")
