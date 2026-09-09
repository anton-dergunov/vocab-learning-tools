"""Turning a source's markup into the plain text an external entry carries.

The regex this replaces — `<[^>]*>` and a whitespace collapse — got five things wrong on the markup
Wikimedia actually returns. A `>` inside an attribute ended the match early and leaked the rest of the
tag into the definition; `<style>` contents were flattened into the text rather than dropped; nested
`<li>` sub-senses ran together into one sentence; entities arrived at the client raw; and a prose
`a < b` swallowed everything up to the next `>`.

A tokeniser rather than a tree, deliberately. This is a streaming text extraction, so the only state
it needs is "am I inside a discarded element", which is a depth counter — and a tokeniser has no tree
to misbuild on the sloppy markup a third party sends. When something here has to *emit* markup rather
than flatten it, that wants a spec-compliant sanitiser and this is not it.

The discard set is `web/src/externalHtml.ts`'s, so the two ends of the same job agree about what
`<script>` means.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

# Removed with their contents. Kept in step with `DISCARDED` in `web/src/externalHtml.ts`: flattening
# a stylesheet into a definition is how `.ib-brac{display:none}` ends up looking like a translation.
DISCARDED = frozenset(
    {
        "script", "style", "iframe", "object", "embed", "link", "meta", "form", "input",
        "button", "select", "textarea", "svg", "audio", "video", "canvas", "noscript", "head",
    }
)

# A boundary between two of these is a boundary between two readable things, so it becomes a space
# rather than nothing. Without it Wiktionary's nested sub-senses arrive as one run-on sentence.
SEPARATED = frozenset(
    {
        "br", "p", "div", "li", "ul", "ol", "dl", "dt", "dd", "tr", "td", "th",
        "table", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "summary", "details",
    }
)

_SPACES = re.compile(r"\s+")

# Invisible characters wiki markup uses for typesetting, which survive a whitespace collapse because
# none of them is `\s`. A soft hyphen or a zero-width space sitting inside a word makes two strings
# that read identically compare unequal, which is the kind of bug nobody finds by looking.
# ZWNJ and ZWJ are deliberately *not* here: they are semantic in Persian, Arabic and Indic scripts
# and in emoji sequences, and dropping them would corrupt the word rather than tidy it.
_INVISIBLE = str.maketrans({"\u00ad": None, "\u200b": None, "\ufeff": None})


class _Text(HTMLParser):
    """Collects the readable text of a fragment and nothing else."""

    def __init__(self) -> None:
        # `convert_charrefs` is what decodes `&amp;` and `&nbsp;`; the regex left both on the wire.
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._discarding = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in DISCARDED:
            self._discarding += 1
        elif tag in SEPARATED:
            self._parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        # `<br/>` never reaches `handle_starttag`, and it is the most common separator of the lot.
        if tag in SEPARATED:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in DISCARDED and self._discarding:
            self._discarding -= 1
        elif tag in SEPARATED:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._discarding:
            self._parts.append(data)

    def text(self) -> str:
        joined = "".join(self._parts).translate(_INVISIBLE)
        return _SPACES.sub(" ", joined).strip()


def plain_text(markup: Any) -> str:
    """The readable text of `markup`, with entities decoded and hidden content dropped."""
    if markup is None:
        return ""
    parser = _Text()
    parser.feed(str(markup))
    parser.close()
    return parser.text()
