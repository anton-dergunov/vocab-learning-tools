"""The second call: one image per sense, saved as a 1024 WebP master.

Square, because both consumers want square — the article fold and an Anki card — and because 1K is
the model's native output, so nothing is upscaled and nothing generated is discarded.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from google import genai
from google.genai import types
from PIL import Image

WEBP_QUALITY = 88


class RenderRefused(RuntimeError):
    """The provider declined to draw. A refusal, not a transport failure — do not retry it."""


@dataclass(frozen=True)
class Rendered:
    path: Path
    bytes_written: int
    usage: dict[str, Any]


class Renderer:
    def __init__(self, client: genai.Client, models: Sequence[str], aspect_ratio: str = "1:1",
                 image_size: str = "1K") -> None:
        self.client = client
        self.models = tuple(models)
        self.aspect_ratio = aspect_ratio
        self.image_size = image_size

    def draw(self, prompt: str, seed: int, output: Path, model: str) -> Rendered:
        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                seed=seed,
                image_config=types.ImageConfig(
                    aspect_ratio=self.aspect_ratio,
                    image_size=self.image_size,
                    output_mime_type="image/png",
                ),
            ),
        )
        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    written = _save_webp(inline.data, output)
                    usage = response.usage_metadata
                    return Rendered(output, written, {
                        "model": model,
                        "promptTokens": getattr(usage, "prompt_token_count", None),
                        "outputTokens": getattr(usage, "candidates_token_count", None),
                        "totalTokens": getattr(usage, "total_token_count", None),
                    })
        raise RenderRefused(_why_empty(response))


def _why_empty(response: Any) -> str:
    for candidate in response.candidates or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason:
            return f"the provider returned no image ({reason})"
    feedback = getattr(response, "prompt_feedback", None)
    blocked = getattr(feedback, "block_reason", None) if feedback else None
    if blocked:
        return f"the provider blocked the prompt ({blocked})"
    return "the provider returned no image and gave no reason"


def _save_webp(data: bytes, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(data)) as image:
        image.convert("RGB").save(output, format="WEBP", quality=WEBP_QUALITY, method=6)
    return output.stat().st_size
