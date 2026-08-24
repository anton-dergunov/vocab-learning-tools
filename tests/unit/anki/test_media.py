from pathlib import Path

import pytest

from vocabgen.anki.media import article_media_paths, generate_article_media
from vocabgen.data.article_extended import ArticleExtended


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
            "notes": [],
        }
    )


class FakeProvider:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = []

    def synthesize(self, text: str, output_path: str) -> None:
        self.calls.append((text, Path(output_path)))
        Path(output_path).write_bytes(self.payload)


def test_article_media_paths_are_deterministic_and_namespaced(tmp_path):
    article = make_article()

    first = article_media_paths(article, tmp_path)
    second = article_media_paths(article, tmp_path)

    assert first == second
    assert first.word.image_path.parent == tmp_path / "images"
    assert first.word.audio_path.parent == tmp_path / "audio"
    assert first.word.image_path.name.startswith("anorar--")
    assert "--meaning--" in first.meanings[0].image_path.name


def test_generate_article_media_reuses_cache_and_can_force_regeneration(tmp_path):
    article = make_article()
    images = FakeProvider(b"image")
    audio = FakeProvider(b"audio")

    media = generate_article_media(article, tmp_path, images, audio)

    assert [text for text, _ in images.calls] == ["word image", "example image"]
    assert [text for text, _ in audio.calls] == ["añorar", "Añoro mi hogar."]
    assert all(path.is_file() for path in media.all_files())
    assert all(".tmp" not in path.name for path in media.all_files())

    generate_article_media(article, tmp_path, images, audio)
    assert len(images.calls) == 2
    assert len(audio.calls) == 2

    generate_article_media(article, tmp_path, images, audio, force=True)
    assert len(images.calls) == 4
    assert len(audio.calls) == 4


def test_failed_media_generation_does_not_publish_partial_file(tmp_path):
    class FailingProvider:
        def synthesize(self, text: str, output_path: str) -> None:
            Path(output_path).write_bytes(b"partial")
            raise RuntimeError("generation failed")

    article = make_article()
    expected = article_media_paths(article, tmp_path).word.image_path

    with pytest.raises(RuntimeError, match="generation failed"):
        generate_article_media(
            article,
            tmp_path,
            FailingProvider(),
            FakeProvider(b"audio"),
        )

    assert not expected.exists()
    assert not list((tmp_path / "images").iterdir())
