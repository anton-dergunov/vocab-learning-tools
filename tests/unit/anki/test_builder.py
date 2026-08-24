import json
import zipfile
from pathlib import Path

import pytest

from vocabgen.anki.builder import (
    DEFAULT_DECK_ID,
    DEFAULT_MODEL_ID,
    build_deck,
    meaning_note_guid,
    word_note_guid,
    write_package,
)
from vocabgen.anki.media import article_media_paths
from vocabgen.anki.media import ArticleMedia
from vocabgen.data.article_extended import ArticleExtended


REPOSITORY_ROOT = Path(__file__).parents[3]


def make_article() -> ArticleExtended:
    return ArticleExtended.model_validate(
        {
            "word": "añorar",
            "translation": "to yearn for",
            "image_prompt": "word image",
            "meanings": [
                {
                    "meaning": "To miss deeply",
                    "example": {
                        "spanish_phrase": "Añoro mi hogar.",
                        "english_translation": "I miss my home.",
                        "image_prompt": "example image",
                        "comment": "Emotional usage.",
                    },
                }
            ],
            "notes": ["Literary usage."],
        }
    )


def test_note_guids_are_deterministic_namespaced_and_normalized():
    assert word_note_guid(" AÑORAR ") == word_note_guid("añorar")
    assert meaning_note_guid("añorar", "Añoro mi hogar.") == meaning_note_guid(
        "AÑORAR",
        "  Añoro   mi hogar. ",
    )
    assert word_note_guid("añorar") != meaning_note_guid(
        "añorar",
        "Añoro mi hogar.",
    )
    assert meaning_note_guid("añorar", "La misma frase.") != meaning_note_guid(
        "extrañar",
        "La misma frase.",
    )


def test_build_deck_preserves_card_structure_comments_and_media(tmp_path):
    article = make_article()
    media = article_media_paths(article, tmp_path / "cache")

    deck, media_files = build_deck(
        article,
        media,
        REPOSITORY_ROOT / "templates",
    )

    assert deck.deck_id == DEFAULT_DECK_ID
    assert len(deck.notes) == 2
    assert deck.notes[0].model.model_id == DEFAULT_MODEL_ID
    assert deck.notes[0].guid == word_note_guid(article.word)
    assert deck.notes[1].guid == meaning_note_guid(
        article.word,
        article.meanings[0].example.spanish_phrase,
    )
    assert "Literary usage." in deck.notes[0].fields[2]
    assert "Emotional usage." in deck.notes[0].fields[2]
    assert "Emotional usage." in deck.notes[1].fields[2]
    assert media.word.image_name in deck.notes[0].fields[2]
    assert media.meanings[0].audio_name in deck.notes[1].fields[2]
    assert media_files == media.all_files()


def test_write_package_embeds_every_media_file(tmp_path):
    article = make_article()
    media = article_media_paths(article, tmp_path / "cache")
    for path in media.all_files():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.suffix.encode("ascii"))
    deck, media_files = build_deck(
        article,
        media,
        REPOSITORY_ROOT / "templates",
    )
    output = tmp_path / "decks" / "article.apkg"

    write_package(deck, media_files, output)

    with zipfile.ZipFile(output) as package:
        names = package.namelist()
        media_manifest = json.loads(package.read("media"))
    assert "collection.anki2" in names or "collection.anki21" in names
    assert set(media_manifest.values()) == {path.name for path in media_files}
    assert all(str(index) in names for index in range(len(media_files)))


def test_write_package_rejects_missing_media(tmp_path):
    article = make_article()
    media = article_media_paths(article, tmp_path / "cache")
    deck, media_files = build_deck(
        article,
        media,
        REPOSITORY_ROOT / "templates",
    )

    with pytest.raises(FileNotFoundError, match="Missing generated media"):
        write_package(deck, media_files, tmp_path / "article.apkg")


def test_build_deck_rejects_article_media_mismatch(tmp_path):
    article = make_article()
    complete_media = article_media_paths(article, tmp_path / "cache")
    incomplete_media = ArticleMedia(word=complete_media.word, meanings=())

    with pytest.raises(ValueError, match="Article/media mismatch"):
        build_deck(
            article,
            incomplete_media,
            REPOSITORY_ROOT / "templates",
        )
