"""Photo capture's page reading: an OCR engine's words in, a page a finger can tap out.

The engine is `acervo.models` — a row of the `ocr` kind, Cloud Vision today — and this package is
what happens to its answer afterwards: words joined back across a hyphenated line break, lines
rebuilt with their outlines, the running text split into sentences, and a sentence the frame cut off
marked as cut off. Everything comes out normalised to the image, so the interface only ever
hit-tests.

**It stands alone the way `images/` does**: it imports `acervo.models` and nothing else of Acervo's,
and `tests/unit/server/test_layering.py` enforces that. `services/photo.py` is the binding layer —
settings, storage, the owner's vocabularies — and this package never learns any of them exist.

The design is `docs/features/photo-capture.md`; every number it was chosen by is in
`experiments/photo-capture/`.
"""
