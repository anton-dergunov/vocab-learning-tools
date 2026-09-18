"""The take cache: FLAC masters, addressed by what they are recordings *of*.

A loop speaks each line three times, so a twelve-word loop is seventy-two recordings. This is what
stops that being seventy-two model calls every time, and it pays for itself twice: a word that
appears in two loops is recorded once, and a render that dies half way — a rate limit, a restart, a
deploy — resumes against the takes that already exist, which is what makes retrying cheap rather
than a second bill.

**The digest is the filename, so there is no table and no schema.** Nothing has to be kept in step
with the files, a half-written render leaves no rows to reconcile, and deleting a take is deleting a
file. The store is unbounded by design; `python -m acervo.admin takes prune` is how it is emptied,
deliberately by hand, the way dictionaries and media already are.

**`take` is in the key, and that is the subtle part.** The director note quantises a continuous
prosody into a small vocabulary of adjectives, so at low prosody strength two takes of the same word
can produce *byte-identical* instructions. Without the index the cache would hand back one recording
for both, and the repetition would sound **more** mechanical, not less. Nothing has noticed so far
only because there was no persistent cache and the providers are nondeterministic — two identical
prompts happen to give two different readings. A cache turns that accident into a guarantee in the
wrong direction.

**The pair is in the key too**, because the same words in a different voice are a different
recording. Which pair answers is not known until it has, so a read tries every pair the owner's order
offers and takes the first hit: a fall-through yesterday still answers today.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

# The extension is part of the contract: a take is read back and returned as-is, so what it is has
# to survive on disk. A provider that answered already-compressed keeps its own type.
EXTENSIONS = {"audio/flac": "flac", "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/wav": "wav"}
MIMES = {extension: mime for mime, extension in EXTENSIONS.items()}


def key(
    *, text: str, language: str, direction: str | None, take: int,
    provider: str, model: str, voice: str | None,
) -> str:
    """What makes two takes the same recording. Everything that changes the audio, and nothing else.

    Not the owner: the same words in the same voice are the same bytes for everybody, and keying on
    the account would record them once per account for no benefit. Nothing here is a secret — the
    text is the owner's own vocabulary and the digest is one-way — but the *files* are still
    server-local and never served, because a take is a cache and not a record's media.
    """
    parts = (text, language, direction or "", str(int(take)), provider, model, voice or "")
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def find(root: Path, digest: str) -> tuple[bytes, str] | None:
    """The stored take under this digest, whatever type it was kept as, or nothing."""
    for extension, mime in MIMES.items():
        path = _path(root, digest, extension)
        if path.is_file():
            try:
                return path.read_bytes(), mime
            except OSError:
                return None
    return None


def store(root: Path, digest: str, data: bytes, mime: str) -> Path:
    """Write one take, atomically. A concurrent render writing the same take is not a conflict."""
    path = _path(root, digest, EXTENSIONS.get(mime, "bin"))
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.part")
    partial.write_bytes(data)
    os.replace(partial, path)
    return path


def prune(root: Path, older_than_days: float, *, dry_run: bool = False) -> tuple[int, int]:
    """Delete takes untouched for this long. Returns how many went and how many bytes with them.

    Age is the file's own modification time, which a store rewrites — so a take a render used
    yesterday survives a prune that clears one from last year.
    """
    if not root.is_dir():
        return 0, 0
    cutoff = time.time() - older_than_days * 86400
    gone = freed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.name.endswith(".part"):
            continue
        try:
            stat = path.stat()
            if stat.st_mtime >= cutoff:
                continue
            if not dry_run:
                path.unlink()
        except OSError:
            continue
        gone += 1
        freed += stat.st_size
    return gone, freed


def usage(root: Path) -> tuple[int, int]:
    """How many takes are kept and what they weigh, for a command that reports before it deletes."""
    if not root.is_dir():
        return 0, 0
    kept = [path for path in root.rglob("*") if path.is_file() and not path.name.endswith(".part")]
    return len(kept), sum(path.stat().st_size for path in kept)


def _path(root: Path, digest: str, extension: str) -> Path:
    # Two levels of fan-out. A year of daily loops is tens of thousands of files, and one directory
    # holding all of them makes every listing — including this module's own prune — quadratic.
    return root / digest[:2] / digest[2:4] / f"{digest}.{extension}"
