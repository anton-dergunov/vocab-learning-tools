from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional


class MediaCollection:
    """Directory-backed collection for one kind of generated media."""

    def __init__(self, base_dir: str | Path, kind: str):
        kind_path = Path(kind)
        if not kind or kind_path.is_absolute() or kind_path.name != kind:
            raise ValueError("kind must be a single relative directory name")
        self.directory = Path(base_dir) / kind
        self.directory.mkdir(parents=True, exist_ok=True)

    def list_files(self) -> List[Path]:
        return sorted(path for path in self.directory.iterdir() if path.is_file())

    def path_for(self, name: str) -> Path:
        name_path = Path(name)
        if not name or name_path.is_absolute() or name_path.name != name:
            raise ValueError("name must be a single relative file name")
        return self.directory / name

    def exists(self, name: str) -> bool:
        return self.path_for(name).is_file()

    def add_from_bytes(
        self,
        name: str,
        data: bytes,
        *,
        overwrite: bool = False,
    ) -> Path:
        path = self.path_for(name)
        if path.exists() and not overwrite:
            raise FileExistsError(path)

        temporary_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary_path.write_bytes(data)
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return path

    def add_from_path(
        self,
        source: str | Path,
        name: Optional[str] = None,
        *,
        overwrite: bool = False,
    ) -> Path:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(source)
        path = self.path_for(name or source.name)
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        shutil.copy2(source, path)
        return path
