from __future__ import annotations
import os
import shutil
from pathlib import Path
from typing import Iterable
import tempfile
import datetime


def atomic_write(path: Path, data: str, encoding: str = "utf-8") -> None:
    """
    Write `data` to `path` atomically using a temp file + rename.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # create temp file next to destination to ensure same filesystem for rename
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(data)
        # On POSIX, this rename is atomic.
        os.replace(tmp_path, path)
    finally:
        # if tmp exists still, attempt cleanup
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def append_to_file(path: Path, content: str, encoding: str = "utf-8") -> None:
    """
    Append `content` to a file, ensuring parent exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding=encoding) as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")


def read_text(path: Path, encoding: str = "utf-8") -> str:
    with open(path, "r", encoding=encoding) as f:
        return f.read()


def backup_file(path: Path, keep_timestamp: bool = True) -> Path:
    """
    Create a timestamped backup copy of path and return its Path.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    bak_path = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(str(path), str(bak_path))
    return bak_path
