# Photo capture · what is still to do

**Status:** open. Photo capture is built for languages that put spaces between words
([`../features/photo-capture.md`](../features/photo-capture.md)).

- **An image share target** — the Web Share Target API, sending a screenshot from any app into this
  screen. Android only for a PWA, since iOS offers PWAs no share target; the macOS host could accept a
  dropped image instead. It shares its manifest work with the text share target in
  [`../plans/capture-transports.md`](../plans/capture-transports.md).
- **Keeping the photo when a sentence is folded into a held word.** Folding goes through the article
  conversation, which carries text.
- **A second OCR row.** If access to Vision changes: measure Azure AI Vision Read first (5,000 free
  transactions a month, word polygons), with the spike's harness; then RapidOCR as a degraded mode
  that says up front it takes several seconds and may miss text on a book photo. Running it on the
  Mac would not help — the Mac is not always on, which is the point of a fallback.
- **Photos taken offline and kept for later: no.** A photo capture is a write, and writes are
  online-only.

## Chinese and Japanese: a separate spike

- **OCR is the easy part.** Vision reads both.
- **A tap lands on a character, not a word.** With no spaces, "the word under the finger" needs a
  segmenter (jieba, SudachiPy) or, more simply, the quick call choosing the unit around the tapped
  character, which it already does for *New York*.
- **SaT covers both languages**, but measure it rather than assume it.
- **Vertical Japanese text** changes reading order and the line geometry.
- **It needs its own fixtures**: photos with hand-checked text, and taps whose unit is several
  characters.

The layout format is character offsets and polygons, so nothing in it assumes spaces.

This is the photo half of [`chinese-subsystem.md`](chinese-subsystem.md).
