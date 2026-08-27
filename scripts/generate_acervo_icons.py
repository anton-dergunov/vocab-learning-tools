#!/usr/bin/env python3
"""Generate only Acervo's micro icon family; larger approved artwork is preserved."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "brand" / "acervo" / "source"
DIST = ROOT / "assets" / "brand" / "acervo" / "dist"


def render(source: Path, size: int) -> Image.Image:
    png = cairosvg.svg2png(url=str(source), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def save(image: Image.Image, path: Path) -> None:
    image.save(path, format="PNG", optimize=True)


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    micro = SOURCE / "favicon-micro.svg"

    small_images: dict[int, Image.Image] = {}
    for size in (16, 24, 32):
        small_images[size] = render(micro, size)
        save(small_images[size], DIST / f"favicon-{size}.png")

    existing_48 = Image.open(DIST / "favicon-48.png").convert("RGBA")
    existing_48.save(
        DIST / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[small_images[16], small_images[32]],
    )
    shutil.copyfile(micro, DIST / "favicon.svg")

    print(f"Generated Acervo micro icons in {DIST.relative_to(ROOT)}; larger artwork unchanged")


if __name__ == "__main__":
    main()
