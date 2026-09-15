# Photo capture fixtures

Real pictures for the photo-capture spike in
[`docs/plans/photo-capture.md`](../../../docs/plans/photo-capture.md): what OCR is scored against,
what resolution and cropping are measured on, and where tap points are placed.

**The camera photos are imperfect on purpose.** They come from an ordinary Android phone, whose
pictures of text go soft toward the edges. That softness is the case to design for, not a flaw to
fix, so these files are kept at full resolution. Whether downscaling costs accuracy is one of the
things the spike measures.

All metadata was removed and the pixels were left unchanged. The files are named by what they are,
not by when they were taken.

## Sources

| Files | What | Source |
| --- | --- | --- |
| `camera-01`–`04.jpg` | Pages of a printed Spanish history book | The owner's own copy |
| `camera-05`–`09.jpg` | Pages of a printed Spanish book on tango music | The owner's own copy |
| `screen-01.png` | Phone screenshot | [tangoba.org — Clasificatorias Tango de Pista](https://tangoba.org/actividad/clasificatorias-tango-de-pista-23-08/) |
| `screen-02.png` | Phone screenshot | [perfil.com — Mundial de Baile de Tango en el Obelisco](https://www.perfil.com/noticias/amp/cultura/mundial-de-baile-de-tango-en-el-obelisco-raul-lavie-amelita-baltar-y-jose-colangelo-cerraron-el-espectaculo.phtml) |
| `screen-03`, `04.png` | Phone screenshots | [turismo.buenosaires.gob.ar — Museo de Arte Latinoamericano, Malba](https://turismo.buenosaires.gob.ar/es/otros-establecimientos/museo-de-arte-latinoamericano-malba) |

These are short excerpts, kept only to test text recognition.

`sources/` holds the body text of the three web pages, copied by hand on 2026-09-15. It serves as
the reference text for the screenshots, and as a copy in case a page changes or goes away. The book
pages have no reference text yet; their transcription is spike step 1.

## `manifest.json`

One row per image: its `kind` (`camera` or `screenshot`), its `source`, a note on what makes it
hard, and a `truth` block. The shape of `truth` is given at the top of the file. Every `truth` is
`null` until it is written by hand. **Do not generate ground truth with the OCR under test**:
scoring an engine against its own output measures nothing.
