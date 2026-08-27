#!/usr/bin/env python3
"""Build the macOS asset catalogue from Acervo's approved optical-size exports."""

from __future__ import annotations

import shutil
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "assets" / "brand" / "acervo" / "dist"
OUTPUT = ROOT / "macos" / "Resources" / "Assets.xcassets"
SOURCES = {
    "icon_16x16.png": "favicon-16.png",
    "icon_16x16@2x.png": "favicon-32.png",
    "icon_32x32.png": "favicon-32.png",
    "icon_32x32@2x.png": "favicon-64.png",
    "icon_128x128.png": "icon-128.png",
    "icon_128x128@2x.png": "icon-256.png",
    "icon_256x256.png": "icon-256.png",
    "icon_256x256@2x.png": "icon-512.png",
    "icon_512x512.png": "icon-512.png",
    "icon_512x512@2x.png": "icon-1024.png",
}


def main() -> None:
    iconset = OUTPUT / "AppIcon.appiconset"
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    iconset.mkdir(parents=True)
    for destination, source in SOURCES.items():
        shutil.copyfile(ICONS / source, iconset / destination)
    (OUTPUT / "Contents.json").write_text(json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2) + "\n")
    images = []
    for size in (16, 32, 128, 256, 512):
        images.append({"filename": f"icon_{size}x{size}.png", "idiom": "mac", "scale": "1x", "size": f"{size}x{size}"})
        images.append({"filename": f"icon_{size}x{size}@2x.png", "idiom": "mac", "scale": "2x", "size": f"{size}x{size}"})
    (iconset / "Contents.json").write_text(json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n")
    print(f"Generated {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
