from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..data.article_extended import ArticleExtended
from ..fileops import atomic_write
from .media import NoteMedia, article_media_paths


@dataclass(frozen=True)
class PreviewMedia:
    image_src: Optional[str]
    audio_src: Optional[str]


def _relative_source(path: Path, output_directory: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return Path(os.path.relpath(path, start=output_directory)).as_posix()


def _preview_media(media: NoteMedia, output_directory: Path) -> PreviewMedia:
    return PreviewMedia(
        image_src=_relative_source(media.image_path, output_directory),
        audio_src=_relative_source(media.audio_path, output_directory),
    )


def render_preview(
    article: ArticleExtended,
    template_dir: str | Path,
    cache_dir: str | Path,
    output_path: str | Path,
) -> Path:
    """Render a standalone HTML article preview using any existing cached media."""
    template_dir = Path(template_dir)
    output_path = Path(output_path)
    media = article_media_paths(article, cache_dir)
    output_directory = output_path.parent

    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(("html", "xml")),
    )
    template = environment.get_template("word_card.html")
    html = template.render(
        data=article,
        css=(template_dir / "anki.css").read_text(encoding="utf-8"),
        word_media=_preview_media(media.word, output_directory),
        meaning_media=tuple(
            _preview_media(item, output_directory) for item in media.meanings
        ),
    )
    atomic_write(output_path, html.rstrip() + "\n")
    return output_path
