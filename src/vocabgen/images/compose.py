"""Brief + style -> the prompt the image model sees, and the version that identifies both.

The full prompt is composed, never stored. `docs/acervo-sense-images.md` §04: what is recorded is
the brief, the style id and the prompt version, and those three plus the tracked files reproduce
this string exactly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .styles import Style

# Appended to every prompt, whatever the style. The constraints that are about the *card* rather
# than about the picture: no text, one dominant subject, a fully rendered scene.
FRAME = (
    "One square illustration. The scene is fully rendered and fully inhabited — no silhouettes, no "
    "flat icons, no diagram, no empty schematic space. A single subject dominates the frame and "
    "everything else is arranged around it. Absolutely no text anywhere in the image: no letters, "
    "words, numbers, captions, labels, signage, logos, watermarks or pseudo-text."
)


def compose(brief: str, style: Style) -> str:
    return f"{brief.strip().rstrip('.')}. {style.brief.strip().rstrip('.')}. {FRAME}"


def prompt_version(template_path: str | Path, style_digest: str) -> str:
    """Identifies the template and the style table together.

    A change to either changes it, which is what tells a later run that a cached brief predates the
    wording currently in the repository.
    """
    template = hashlib.sha256(Path(template_path).read_bytes()).hexdigest()[:12]
    frame = hashlib.sha256(FRAME.encode()).hexdigest()[:6]
    return f"img-{template}-{style_digest}-{frame}"
