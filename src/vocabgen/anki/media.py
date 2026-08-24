from __future__ import annotations

import hashlib
import os
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Tuple

from ..data.article_extended import ArticleExtended
from ..data.media_collection import MediaCollection
from ..fileops import slugify_filename


class MediaProvider(Protocol):
    def synthesize(self, text: str, output_path: str) -> None: ...


@dataclass(frozen=True)
class NoteMedia:
    image_path: Path
    audio_path: Path

    @property
    def image_name(self) -> str:
        return self.image_path.name

    @property
    def audio_name(self) -> str:
        return self.audio_path.name


@dataclass(frozen=True)
class ArticleMedia:
    word: NoteMedia
    meanings: Tuple[NoteMedia, ...]

    def all_files(self) -> Tuple[Path, ...]:
        files = [self.word.image_path, self.word.audio_path]
        for media in self.meanings:
            files.extend((media.image_path, media.audio_path))
        return tuple(files)


def _identity_stem(value: str, *, max_slug_length: int = 64) -> str:
    slug = slugify_filename(value) or "item"
    normalized = " ".join(
        unicodedata.normalize("NFKC", value).strip().casefold().split()
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:max_slug_length]}--{digest}"


def article_media_paths(article: ArticleExtended, cache_dir: str | Path) -> ArticleMedia:
    """Return deterministic cache paths without creating or generating files."""
    cache_dir = Path(cache_dir)
    word_identity = _identity_stem(article.word)
    image_dir = cache_dir / "images"
    audio_dir = cache_dir / "audio"

    word = NoteMedia(
        image_path=image_dir / f"{word_identity}--word.jpg",
        audio_path=audio_dir / f"{word_identity}--word.mp3",
    )
    meanings = []
    for meaning in article.meanings:
        phrase_identity = _identity_stem(
            meaning.example.spanish_phrase,
            max_slug_length=48,
        )
        stem = f"{word_identity}--meaning--{phrase_identity}"
        meanings.append(
            NoteMedia(
                image_path=image_dir / f"{stem}.jpg",
                audio_path=audio_dir / f"{stem}.mp3",
            )
        )
    return ArticleMedia(word=word, meanings=tuple(meanings))


def _synthesize_atomically(
    provider: MediaProvider,
    text: str,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}.",
        suffix=output_path.suffix,
        dir=output_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()
    try:
        provider.synthesize(text, str(temporary_path))
        if not temporary_path.is_file():
            raise RuntimeError(
                f"Media provider did not create expected output: {temporary_path}"
            )
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def generate_article_media(
    article: ArticleExtended,
    cache_dir: str | Path,
    image_provider: MediaProvider,
    tts_provider: MediaProvider,
    *,
    force: bool = False,
) -> ArticleMedia:
    """Generate missing article media and return every associated cache path."""
    cache_dir = Path(cache_dir)
    # Constructing the collections establishes the two canonical cache folders.
    MediaCollection(cache_dir, "images")
    MediaCollection(cache_dir, "audio")
    media = article_media_paths(article, cache_dir)

    jobs = [
        (image_provider, article.image_prompt, media.word.image_path),
        (tts_provider, article.word, media.word.audio_path),
    ]
    for meaning, meaning_media in zip(article.meanings, media.meanings):
        jobs.extend(
            [
                (
                    image_provider,
                    meaning.example.image_prompt,
                    meaning_media.image_path,
                ),
                (
                    tts_provider,
                    meaning.example.spanish_phrase,
                    meaning_media.audio_path,
                ),
            ]
        )

    for provider, text, output_path in jobs:
        if force or not output_path.is_file():
            _synthesize_atomically(provider, text, output_path)
    return media
