import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from vocabgen.data.article_extended import (
    ArticleExtended,
    ArticleExtendedCollection,
)


@pytest.fixture
def article_data():
    return {
        "word": "añorar",
        "translation": "to yearn for",
        "image_prompt": "A distant home at dusk, no text",
        "meanings": [
            {
                "meaning": "To miss something deeply",
                "example": {
                    "spanish_phrase": "Añoro mi hogar.",
                    "english_translation": "I miss my home.",
                    "image_prompt": "A traveler remembering a warm home, no text",
                    "comment": "A heartfelt sense of absence.",
                },
            }
        ],
        "notes": ["More literary than extrañar."],
    }


@pytest.fixture
def article(article_data):
    return ArticleExtended.model_validate(article_data)


def test_validates_canonical_schema_and_iterates_media_fields(article):
    assert article.word == "añorar"
    assert article.meanings[0].example.spanish_phrase == "Añoro mi hogar."
    assert list(article.iter_image_prompts()) == [
        "A distant home at dusk, no text",
        "A traveler remembering a warm home, no text",
    ]
    assert list(article.iter_spanish_phrases()) == ["Añoro mi hogar."]


def test_json_round_trip_preserves_unicode_and_canonical_shape(article):
    serialized = article.to_json()
    restored = ArticleExtended.from_json(serialized)

    assert "añorar" in serialized
    assert restored == article
    assert "entry" not in json.loads(serialized)
    assert "image_prompt" not in json.loads(serialized)["meanings"][0]


def test_rejects_legacy_entry_field(article_data):
    article_data["entry"] = article_data.pop("word")

    with pytest.raises(ValidationError):
        ArticleExtended.model_validate(article_data)


def test_rejects_meaning_level_image_prompt(article_data):
    meaning = article_data["meanings"][0]
    meaning["image_prompt"] = meaning["example"].pop("image_prompt")

    with pytest.raises(ValidationError):
        ArticleExtended.model_validate(article_data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("word", " "),
        ("translation", ""),
        ("image_prompt", " "),
        ("meanings", []),
    ],
)
def test_rejects_empty_required_content(article_data, field, value):
    article_data[field] = value

    with pytest.raises(ValidationError):
        ArticleExtended.model_validate(article_data)


def test_repository_sample_uses_canonical_schema():
    repository_root = Path(__file__).parents[3]

    article = ArticleExtended.load_from_file(repository_root / "input.json")

    assert article.word == "anhelar"
    assert len(article.meanings) == 4
    assert all(meaning.example.image_prompt for meaning in article.meanings)


def test_anki_prompt_example_is_valid_canonical_json():
    repository_root = Path(__file__).parents[3]
    prompt = (repository_root / "prompts" / "anki_prompt_spanish.txt").read_text(
        encoding="utf-8"
    )
    example_json = prompt.split("Example:\n\n", 1)[1].split(
        "\n\nNow do the same",
        1,
    )[0]

    article = ArticleExtended.from_json(example_json)

    assert article.word == "añorar"
    assert len(article.meanings) == 4


def test_extended_collection_adds_reads_and_finds_articles(tmp_path, article):
    collection = ArticleExtendedCollection(tmp_path / "vocabulary")
    assert len(collection) == 0

    path = collection.add(article)

    assert path.name == "anorar.json"
    assert len(collection) == 1
    assert collection.read_all() == [article]
    assert collection.get_by_word("añorar") == article
    assert collection.get_by_word("missing") is None

    with pytest.raises(FileExistsError):
        collection.add(article)

    assert collection.add(article, overwrite=True) == path


def test_extended_collection_reports_invalid_cached_json(tmp_path):
    collection = ArticleExtendedCollection(tmp_path)
    invalid = tmp_path / "broken.json"
    invalid.write_text('{"word": "incomplete"}', encoding="utf-8")

    with pytest.raises(ValueError, match=r"broken\.json"):
        collection.read_all()


def test_save_rejects_path_traversal(tmp_path, article):
    with pytest.raises(ValueError, match="single relative file name"):
        article.save_to_file(tmp_path, "../outside.json")
