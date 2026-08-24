from pathlib import Path

from vocabgen.anki.media import article_media_paths
from vocabgen.anki.preview import render_preview
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


def test_render_preview_without_media_still_renders_article(tmp_path):
    output = tmp_path / "preview" / "article.html"

    render_preview(
        make_article(),
        REPOSITORY_ROOT / "templates",
        tmp_path / "cache",
        output,
    )

    html = output.read_text(encoding="utf-8")
    assert "añorar" in html
    assert "Añoro mi hogar." in html
    assert "Emotional usage." in html
    assert "Literary usage." in html
    assert "<audio" not in html


def test_render_preview_links_existing_cached_media_relatively(tmp_path):
    article = make_article()
    cache = tmp_path / "cache"
    media = article_media_paths(article, cache)
    for path in media.all_files():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"media")
    output = tmp_path / "preview" / "article.html"

    render_preview(
        article,
        REPOSITORY_ROOT / "templates",
        cache,
        output,
    )

    html = output.read_text(encoding="utf-8")
    assert f"../cache/images/{media.word.image_name}" in html
    assert f"../cache/audio/{media.word.audio_name}" in html
    assert f"../cache/images/{media.meanings[0].image_name}" in html
    assert f"../cache/audio/{media.meanings[0].audio_name}" in html
