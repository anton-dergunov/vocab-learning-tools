"""The second call: one image per sense, encoded as a square WebP master.

Encoded rather than saved: what comes back is bytes, and where they go is the caller's business.
That is not tidiness — a picture's file name carries a digest of these bytes (`images/ids.py`), so
the name cannot exist until the encode has finished.

Square, because both consumers want square — the article fold and an Anki card. The master is 1024
by default, which is the Gemini image models' native output, so nothing is upscaled; a row that
draws smaller is saved at what it drew rather than blown up, and `--size 512` is the cheap sweep,
Cloudflare's free allocation being metered in neurons proportional to pixels.

One pair, one call. Walking the chain is `run.py`'s job, because it also owns the pacing that
decides which pair is free soonest — see the note on `Runner.pace`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from acervo.models import Answer, ImageResult, call, chain

WEBP_QUALITY = 88
# 1024², the models' native output. Not a per-call argument on `draw` because the whole run must
# agree: a contact sheet of mixed sizes is unreadable and a re-drawn sense would not match its
# neighbours.
MASTER = (1024, 1024)


@dataclass(frozen=True)
class Rendered:
    """The master as it will be stored, and the row that drew it.

    The bytes rather than a path: the file's name is derived from them, so nothing can be written
    until they exist.
    """

    data: bytes
    answer: Answer


class Renderer:
    def __init__(self, size: tuple[int, int] = MASTER) -> None:
        self.size = size

    def draw(self, prompt: str, seed: int, candidate: chain.Candidate) -> Rendered:
        """Draw one picture with one pair.

        A provider that looks at the prompt and declines raises `ProviderRefused("refused")` from
        `call.image` — terminal, and `run.py` records it rather than retrying. A provider that is
        rate limited or down raises `ProviderUnavailable`, which is the caller's cue to try another
        pair.
        """
        result: ImageResult = call.image(
            prompt, row=candidate.row, model=candidate.model, seed=seed, size=self.size
        )
        return Rendered(encode_master(result.data, self.size), result.answer)


def encode_master(data: bytes, master: tuple[int, int] = MASTER) -> bytes:
    """Encode at the master size, downsampling if the provider drew larger and never upscaling.

    Upscaling would invent detail and cost bytes for nothing; a provider that draws smaller than
    asked has already been reported as such in the answer's warnings, and the file says what it is.
    """
    with Image.open(io.BytesIO(data)) as image:
        picture = image.convert("RGB")
        if picture.size[0] > master[0] or picture.size[1] > master[1]:
            picture = picture.resize(master, Image.LANCZOS)
        buffer = io.BytesIO()
        picture.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buffer.getvalue()


def as_master(data: bytes, master: tuple[int, int] = MASTER) -> bytes:
    """A file that already *is* a master, kept byte for byte; anything else, encoded into one.

    For a picture put back from a bundle, which is a master Acervo wrote: re-encoding it cost half a
    second of the server's CPU per picture — about twenty-five minutes for one vocabulary's import —
    and bought only a second generation of WebP artifacts. The rule `pronunciation/encode.py` follows
    for audio that arrives already compressed. A file that does not decode is still refused, because
    it is decoded here in full before it is believed.
    """
    with Image.open(io.BytesIO(data)) as image:
        fits = image.format == "WEBP" and image.size[0] <= master[0] and image.size[1] <= master[1]
        if fits:
            image.load()
    return data if fits else encode_master(data, master)
