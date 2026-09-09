"""Media file names for Anki notes.

Anki stores media as loose files in one flat directory shared by every deck, so a name has to
survive a filesystem, a sync protocol and a mobile client without being rewritten. Accents, spaces
and punctuation are the three things that do not, so they go.
"""

from __future__ import annotations

from slugify import slugify


def slugify_filename(value: str) -> str:
    """Lowercase ASCII with underscores: accents folded, punctuation dropped."""
    return slugify(value, separator="_", allow_unicode=False)
