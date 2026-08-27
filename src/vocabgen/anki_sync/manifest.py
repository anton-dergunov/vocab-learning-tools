from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SyncManifestNote(BaseModel):
    """One Acervo-owned note to create or update in Anki."""

    model_config = ConfigDict(extra="forbid")

    note_id: UUID
    lexeme_id: UUID
    deck: NonEmptyString
    sentence: NonEmptyString
    translation: NonEmptyString
    comment_html: str = ""
    tags: list[NonEmptyString] = Field(default_factory=list)
    image_path: str | None = None
    audio_path: str | None = None

    @model_validator(mode="after")
    def validate_managed_values(self) -> SyncManifestNote:
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must be unique")
        unmanaged = [tag for tag in self.tags if not tag.startswith("acervo::")]
        if unmanaged:
            raise ValueError("manifest tags must use the acervo:: namespace")
        if self.image_path is not None and not self.image_path.strip():
            raise ValueError("image_path cannot be blank")
        if self.audio_path is not None and not self.audio_path.strip():
            raise ValueError("audio_path cannot be blank")
        return self

    def media_source(self, kind: str, manifest_dir: Path) -> Path | None:
        """Resolve a media path while preventing traversal outside the payload."""
        value = self.image_path if kind == "image" else self.audio_path
        if value is None:
            return None
        relative = Path(value)
        if relative.is_absolute():
            raise ValueError(f"{kind}_path must be relative to the manifest")
        root = manifest_dir.resolve()
        source = (root / relative).resolve()
        if not source.is_relative_to(root):
            raise ValueError(f"{kind}_path escapes the manifest directory: {value}")
        if not source.is_file():
            raise FileNotFoundError(source)
        return source


class SyncManifest(BaseModel):
    """Versioned rendered-note input for the Anki robot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    notes: list[SyncManifestNote] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_version_and_identities(self) -> SyncManifest:
        if self.schema_version != 1:
            raise ValueError(
                f"Unsupported manifest schema_version {self.schema_version}; expected 1"
            )
        identities = [note.note_id for note in self.notes]
        if len(identities) != len(set(identities)):
            raise ValueError("note_id values must be unique within a manifest")
        return self

    @classmethod
    def load(cls, path: str | Path) -> tuple[SyncManifest, Path]:
        manifest_path = Path(path).expanduser().resolve()
        manifest = cls.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        manifest.validate_media(manifest_path.parent)
        return manifest, manifest_path.parent

    def validate_media(self, manifest_dir: Path) -> None:
        for note in self.notes:
            note.media_source("image", manifest_dir)
            note.media_source("audio", manifest_dir)
