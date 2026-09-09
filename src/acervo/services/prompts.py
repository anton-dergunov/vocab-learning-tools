"""The capture prompts, read from disk by name at request time.

They are content, not code: tracked once at the repository root, copied into the image, and changed
without changing the code that builds a request out of them.
"""

from __future__ import annotations

from pathlib import Path

from acervo.errors import ApiError

_cache: dict[str, str] = {}


def prompt_text(directory: Path, name: str) -> str:
    cached = _cache.get(name)
    if cached:
        return cached
    try:
        text = (Path(directory) / f"{name}.txt").read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if not text:
        raise ApiError(
            500,
            "prompt_missing",
            f"The Acervo server is missing its '{name}' prompt, so it cannot build entries.",
        )
    _cache[name] = text
    return text


def forget_prompts() -> None:
    """Drop the cache. For tests that write a prompt directory per case."""
    _cache.clear()
