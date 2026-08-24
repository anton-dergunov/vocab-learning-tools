from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Iterator, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from ..fileops import atomic_write, slugify_filename


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ArticleExample(BaseModel):
    """Example sentence and media prompt for one distinct meaning."""

    model_config = ConfigDict(extra="forbid")

    spanish_phrase: NonEmptyString
    english_translation: NonEmptyString
    image_prompt: NonEmptyString
    comment: Optional[NonEmptyString] = None


class ArticleMeaning(BaseModel):
    """One meaning of an extended vocabulary article."""

    model_config = ConfigDict(extra="forbid")

    meaning: NonEmptyString
    example: ArticleExample


class ArticleExtended(BaseModel):
    """Validated JSON article used to generate vocabulary study media and cards.

    ``word`` is the canonical field name for either a single word or a phrase.
    Each meaning's image prompt lives with the example it illustrates.
    """

    model_config = ConfigDict(extra="forbid")

    word: NonEmptyString
    translation: NonEmptyString
    image_prompt: NonEmptyString
    meanings: List[ArticleMeaning] = Field(min_length=1)
    notes: List[NonEmptyString] = Field(default_factory=list)

    @classmethod
    def from_json(cls, value: str | bytes) -> ArticleExtended:
        """Validate an article from JSON text."""
        return cls.model_validate_json(value)

    def to_json(self) -> str:
        """Serialize the canonical schema as readable UTF-8 JSON."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def load_from_file(cls, path: str | Path) -> ArticleExtended:
        """Read and validate an article from a JSON file."""
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def save_to_file(
        self,
        directory: str | Path,
        filename: Optional[str] = None,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Atomically save the article under ``directory``.

        The default filename is derived from ``word``. Existing articles are not
        replaced unless ``overwrite`` is explicitly enabled.
        """
        directory = Path(directory)
        filename = filename or f"{slugify_filename(self.word)}.json"
        relative_name = Path(filename)
        if relative_name.is_absolute() or relative_name.name != filename:
            raise ValueError("filename must be a single relative file name")
        path = directory / filename
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        atomic_write(path, self.to_json() + "\n")
        return path

    def iter_image_prompts(self) -> Iterator[str]:
        """Iterate the article prompt followed by every example prompt."""
        yield self.image_prompt
        for meaning in self.meanings:
            yield meaning.example.image_prompt

    def iter_spanish_phrases(self) -> Iterator[str]:
        """Iterate the Spanish example phrases in meaning order."""
        for meaning in self.meanings:
            yield meaning.example.spanish_phrase


class ArticleExtendedCollection:
    """Directory-backed collection of canonical extended-article JSON files."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def list_files(self) -> List[Path]:
        return sorted(self.directory.glob("*.json"))

    def __len__(self) -> int:
        return len(self.list_files())

    def read_all(self) -> List[ArticleExtended]:
        articles = []
        for path in self.list_files():
            try:
                articles.append(ArticleExtended.load_from_file(path))
            except (OSError, ValidationError) as exc:
                raise ValueError(f"Failed to load extended article {path}: {exc}") from exc
        return articles

    def add(self, article: ArticleExtended, *, overwrite: bool = False) -> Path:
        return article.save_to_file(self.directory, overwrite=overwrite)

    def get_by_word(self, word: str) -> Optional[ArticleExtended]:
        path = self.directory / f"{slugify_filename(word)}.json"
        if not path.exists():
            return None
        try:
            return ArticleExtended.load_from_file(path)
        except (OSError, ValidationError) as exc:
            raise ValueError(f"Failed to load extended article {path}: {exc}") from exc
