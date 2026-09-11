"""The prompts, read from disk by name at request time.

They are content, not code: tracked once at the repository root, copied into the image, and changed
without changing the code that builds a request out of them. Markdown, because they *are* Markdown —
headings, tables and emphasis throughout — and naming them so means they render where they are read.

A prompt may carry a block that only some owners want:

    <!-- if: selfContainedOnly -->
    …text…
    <!-- end -->

HTML comments rather than a template engine, for two reasons. A prompt contains literal braces — the
clip selector shows the model a JSON shape — so `{{` and `{%` would become characters every future
prompt has to avoid, and a stray one would change meaning rather than read as text. And an HTML
comment disappears when the file is rendered, so the marker costs the reader nothing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from acervo.errors import ApiError

# The raw file, never the rendered text. Rendering depends on the caller's options, and caching the
# result would make whichever setting arrived first stick for the life of the process.
_cache: dict[str, str] = {}

_SECTION = re.compile(
    r"^[ \t]*<!--[ \t]*if:[ \t]*(?P<name>[A-Za-z][A-Za-z0-9]*)[ \t]*-->[ \t]*\n"
    r"(?P<body>.*?)"
    r"^[ \t]*<!--[ \t]*end[ \t]*-->[ \t]*\n?",
    re.DOTALL | re.MULTILINE,
)


def prompt_text(directory: Path, name: str, options: Mapping[str, bool] | None = None) -> str:
    """One prompt, with its optional sections resolved against `options`."""
    return sections(_raw(directory, name), options or {}, name)


def _raw(directory: Path, name: str) -> str:
    cached = _cache.get(name)
    if cached:
        return cached
    try:
        text = (Path(directory) / f"{name}.md").read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if not text:
        raise ApiError(
            500,
            "prompt_missing",
            f"The Acervo server is missing its '{name}' prompt, so it cannot build entries.",
        )
    _cache[name] = text
    return text


def sections(text: str, options: Mapping[str, bool], name: str = "prompt") -> str:
    """Keep the blocks whose option is on, drop the rest.

    An option the caller did not name **raises**. These are tracked files changed together with the
    code that reads them, so a misspelled marker is a bug a test should catch — not a section that
    quietly stops being sent, which is the kind of thing nobody notices for months.
    """

    def resolve(match: re.Match[str]) -> str:
        option = match.group("name")
        if option not in options:
            raise ApiError(
                500,
                "prompt_option_unknown",
                f"The '{name}' prompt asks for an option called '{option}', which nothing supplies.",
            )
        return match.group("body") if options[option] else ""

    resolved = _SECTION.sub(resolve, text).strip()
    # A marker the pattern did not consume — trailing text on the marker line, a missing `end`, a
    # typo in the syntax itself. Left alone it would reach the model as literal HTML and, worse,
    # its section would silently be *always on*. Same argument as an unknown option name.
    leftover = next((marker for marker in ("<!-- if:", "<!-- end") if marker in resolved), None)
    if leftover is not None:
        raise ApiError(
            500,
            "prompt_marker_malformed",
            f"The '{name}' prompt has a section marker the reader could not parse. "
            "Markers go on their own line, as `<!-- if: optionName -->` and `<!-- end -->`.",
        )
    return resolved


def forget_prompts() -> None:
    """Drop the cache. For tests that write a prompt directory per case."""
    _cache.clear()
