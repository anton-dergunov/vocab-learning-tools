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
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, text=True)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(data)
        # On POSIX, this rename is atomic.
        os.replace(tmp, str(path))
    finally:
        # if tmp exists still, attempt cleanup
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
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
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") if keep_timestamp else ""
    bak_name = f"{path.name}.bak{('.' + timestamp) if timestamp else ''}"
    bak_path = path.parent / bak_name
    shutil.copy2(str(path), str(bak_path))
    return bak_path
