from __future__ import annotations

import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Tuple

import genanki
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..data.article_extended import ArticleExtended
from .media import ArticleMedia


DEFAULT_MODEL_ID = 1607392319
DEFAULT_DECK_ID = 2059400110
DEFAULT_DECK_NAME = "Spanish Vocabulary"
MODEL_NAME = "VocabgenSpanishArticle"


def _normalize_identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().casefold().split())


def word_note_guid(word: str) -> str:
    return genanki.guid_for("vocabgen", _normalize_identity(word), "word")


def meaning_note_guid(word: str, spanish_phrase: str) -> str:
    return genanki.guid_for(
        "vocabgen",
        _normalize_identity(word),
        "meaning",
        _normalize_identity(spanish_phrase),
    )


def _template_environment(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_deck(
    article: ArticleExtended,
    media: ArticleMedia,
    template_dir: str | Path,
    *,
    model_id: int = DEFAULT_MODEL_ID,
    deck_id: int = DEFAULT_DECK_ID,
    deck_name: str = DEFAULT_DECK_NAME,
) -> Tuple[genanki.Deck, Tuple[Path, ...]]:
    """Build an in-memory Anki deck and return its associated media files."""
    if len(media.meanings) != len(article.meanings):
        raise ValueError(
            "Article/media mismatch: "
            f"{len(article.meanings)} meanings, {len(media.meanings)} media entries"
        )
    template_dir = Path(template_dir)
    css = (template_dir / "anki.css").read_text(encoding="utf-8")
    environment = _template_environment(template_dir)
    word_comment = environment.get_template("word_comment.html")
    meaning_comment = environment.get_template("meaning_comment.html")

    model = genanki.Model(
        model_id,
        MODEL_NAME,
        fields=[
            {"name": "Sentence"},
            {"name": "Translation"},
            {"name": "Comment"},
        ],
        templates=[
            {
                "name": "Card 1",
                "qfmt": '<div class="phrase">{{Sentence}}</div>',
                "afmt": (
                    "{{FrontSide}}<hr id=\"answer\">"
                    '<div class="translation">{{Translation}}</div>{{Comment}}'
                ),
            }
        ],
        css=css,
    )
    deck = genanki.Deck(deck_id, deck_name)

    deck.add_note(
        genanki.Note(
            model=model,
            fields=[
                article.word,
                article.translation,
                word_comment.render(data=article, media=media.word),
            ],
            guid=word_note_guid(article.word),
        )
    )

    for meaning, meaning_media in zip(article.meanings, media.meanings):
        example = meaning.example
        deck.add_note(
            genanki.Note(
                model=model,
                fields=[
                    example.spanish_phrase,
                    example.english_translation,
                    meaning_comment.render(
                        meaning=meaning,
                        data=article,
                        media=meaning_media,
                    ),
                ],
                guid=meaning_note_guid(article.word, example.spanish_phrase),
            )
        )

    return deck, media.all_files()


def write_package(
    deck: genanki.Deck,
    media_files: Tuple[Path, ...],
    output_path: str | Path,
) -> Path:
    """Write an Anki package atomically and require every media file to exist."""
    output_path = Path(output_path)
    missing = [path for path in media_files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing generated media: {missing[0]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.",
        suffix=".apkg",
        dir=output_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()
    try:
        genanki.Package(
            deck,
            media_files=[str(path) for path in media_files],
        ).write_to_file(str(temporary_path))
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path
