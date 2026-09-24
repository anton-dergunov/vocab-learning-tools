#!/usr/bin/env python3
"""Record Cloud Vision's raw answer for every fixture, once, as the shipped code's test data.

The spike cached its own *reduced* layout, which threw away the block and paragraph structure — the
one thing the "split on Vision's blocks, then rules" arm needs, and the thing `acervo.ocr` is written
against. This asks Vision again, the way the server will: the whole frame at 2048 px, JPEG quality 85,
`DOCUMENT_TEXT_DETECTION`. Thirteen images, thirteen units of the free thousand.

What is kept is trimmed to the fields `acervo.models.google_vision.parse` reads — a symbol's text and
its break, a word's outline and confidence, the block and paragraph nesting, the page's size and
language — so a dense page is a few hundred kilobytes rather than several megabytes of per-symbol
boxes. It is still an `images:annotate` response in Vision's own shape.

    .venv/bin/python record_vision.py            # writes tests/fixtures/photo-capture/vision/
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from engines import Variant, prepare, vision_credentials

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "photo-capture"
OUT = FIXTURES / "vision"
FRAME = Variant("full", 2048)


def trimmed(answer: dict[str, Any]) -> dict[str, Any]:
    pages = []
    for page in (answer.get("fullTextAnnotation") or {}).get("pages") or []:
        blocks = []
        for block in page.get("blocks") or []:
            paragraphs = []
            for paragraph in block.get("paragraphs") or []:
                words = []
                for word in paragraph.get("words") or []:
                    symbols = []
                    for symbol in word.get("symbols") or []:
                        kept: dict[str, Any] = {"text": symbol.get("text", "")}
                        broken = (symbol.get("property") or {}).get("detectedBreak")
                        if broken:
                            kept["property"] = {"detectedBreak": broken}
                        symbols.append(kept)
                    words.append({
                        "boundingBox": word.get("boundingBox", {}),
                        "confidence": word.get("confidence", 0.0),
                        "symbols": symbols,
                    })
                paragraphs.append({"words": words})
            blocks.append({"paragraphs": paragraphs})
        pages.append({
            "property": {"detectedLanguages": (page.get("property") or {}).get("detectedLanguages", [])},
            "width": page.get("width"),
            "height": page.get("height"),
            "blocks": blocks,
        })
    return {"fullTextAnnotation": {"pages": pages}}


def main() -> None:
    import requests

    token, project = vision_credentials()
    OUT.mkdir(exist_ok=True)
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for image in manifest["images"]:
        data, _box, _scale = prepare(FIXTURES / image["file"], FRAME)
        body = {"requests": [{
            "image": {"content": base64.b64encode(data).decode()},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["es"]},
        }]}
        started = time.perf_counter()
        response = requests.post(
            "https://vision.googleapis.com/v1/images:annotate",
            headers={"Authorization": f"Bearer {token}", "x-goog-user-project": project},
            json=body, timeout=60,
        )
        response.raise_for_status()
        answer = response.json()["responses"][0]
        if "error" in answer:
            raise RuntimeError(answer["error"])
        target = OUT / (Path(image["file"]).stem + ".json")
        target.write_text(json.dumps(trimmed(answer), ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{image['file']}: {time.perf_counter() - started:.2f}s, {target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
