"""The second call: one image per sense, saved as a square WebP master.

Square, because both consumers want square — the article fold and an Anki card. The master is 1024
by default, which is the Gemini image models' native output, so nothing is upscaled; a row that
draws smaller is saved at what it drew rather than blown up, and `--size 512` is the cheap sweep,
Cloudflare's free allocation being metered in neurons proportional to pixels.

One pair, one call. Walking the chain is `run.py`'s job, because it also owns the pacing that
decides which pair is free soonest — see the note on `Runner.pace`.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from acervo.models import Answer, ImageResult, call, chain

WEBP_QUALITY = 88
# 1024², the models' native output. Not a per-call argument on `draw` because the whole run must
# agree: a contact sheet of mixed sizes is unreadable and a re-drawn sense would not match its
# neighbours.
MASTER = (1024, 1024)


@dataclass(frozen=True)
class Rendered:
    path: Path
    bytes_written: int
    answer: Answer


class Renderer:
    def __init__(self, size: tuple[int, int] = MASTER) -> None:
        self.size = size

    def draw(self, prompt: str, seed: int, output: Path, candidate: chain.Candidate) -> Rendered:
        """Draw one picture with one pair.

        A provider that looks at the prompt and declines raises `ProviderRefused("refused")` from
        `call.image` — terminal, and `run.py` records it rather than retrying. A provider that is
        rate limited or down raises `ProviderUnavailable`, which is the caller's cue to try another
        pair.
        """
        result: ImageResult = call.image(
            prompt, row=candidate.row, model=candidate.model, seed=seed, size=self.size
        )
        return Rendered(output, save_master(result.data, output, self.size), result.answer)


def save_master(data: bytes, output: Path, master: tuple[int, int] = MASTER) -> int:
    """Save at the master size, downsampling if the provider drew larger and never upscaling.

    Upscaling would invent detail and cost bytes for nothing; a provider that draws smaller than
    asked has already been reported as such in the answer's warnings, and the file says what it is.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the target and moved into place, so a reader never sees a half-written file
    # and two writers racing on the same derived path cannot tear one. The path is derived from the
    # sense, so two devices asking for the same picture *will* collide — this is the ordinary case,
    # not the unlucky one.
    staging = output.with_suffix(output.suffix + ".part")
    with Image.open(io.BytesIO(data)) as image:
        picture = image.convert("RGB")
        if picture.size[0] > master[0] or picture.size[1] > master[1]:
            picture = picture.resize(master, Image.LANCZOS)
        picture.save(staging, format="WEBP", quality=WEBP_QUALITY, method=6)
    os.replace(staging, output)
    return output.stat().st_size
