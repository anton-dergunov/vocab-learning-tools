# Photo capture · tap a word in what you're reading

**Status:** unbuilt. The Spanish spike has run: **the idea survives with Cloud Vision reading the
photo, and not with RapidOCR on the NAS**. See [Spike results](#spike-results). The code is in
[`research/photo_capture/`](../../research/photo_capture/README.md), and the fixtures it measures
against are in [`tests/fixtures/photo-capture/`](../../tests/fixtures/photo-capture/README.md).
Several sections below have been corrected by what it measured. Chinese and Japanese are a separate
spike, not yet run.

Today a word reaches Acervo by being typed or pasted into Add. That works for text already on a
screen. It is awkward for a word met in a printed book, and it throws away the thing a personal
dictionary most wants: the sentence the word was met in, and a memory of where.

## Outcome

Add opens the camera straight away. The viewfinder fills the top of the screen, leaving room for a
sheet below it, and a second button chooses an existing image or screenshot instead. The whole
frame is what gets read: the spike showed a square crop cuts the very sentences worth keeping. Taking the picture freezes the
frame, and every recognised word on it becomes tappable.

Tapping a word highlights it, and its sentence in a second colour. A sheet under the frame shows
that sentence as editable text with the word marked, and within about a second shows what the word
means **in this sentence**. From there it is one tap to one of two actions:

- **Add**, for a word the owner does not have. It builds an entry with the sentence as its
  attestation and the photo kept beside it.
- **Open / fold in**, for a word the owner already has. It opens the stored article and offers to
  add this sentence to it.

On a desktop, or on a tablet on its stand, it is the same screen with a file picker, paste and drop
in place of the camera.

The tapped word is a hint, not the answer. Tapping *new* in "New York" should propose *New York*,
and tapping *echo* in "te echo de menos" should propose *echar de menos*. A model makes that
judgement, the same one resolve already makes on typed text.

## Why build it when Lens, Live Text and Google Translate exist

This question has to be answered first, because each platform already does part of this for free.

- **iOS Live Text and Google Lens** recognise text on the device. Getting a sentence into Acervo is
  photo → open it → select → copy → switch to Acervo → paste → Add: about eight taps. The sentence
  is kept only if the owner selects all of it, and choosing *which* word is left for the capture
  flow to guess.
- **Google Translate's camera** needs no taps at all and translates as you point. It keeps nothing,
  though: no attestation, no duplicate check, no entry, no picture.

What this feature has that neither of those has:

- About **three taps**: shutter, word, Add.
- The **sentence captured by default**, as an attestation, which is the point of a personal
  dictionary.
- The **duplicate check before any typing**. A word already held becomes "add this sentence to it"
  instead of a second entry.
- The meaning **as used in this sentence**, rather than a list of dictionary senses.
- The **photo kept as provenance**: where on the page, or which street sign.

**Kill criterion, stated up front.** If the spike shows either of these:

- tap-to-meaning slower than about **3 s at the median** on mobile data, or
- OCR in the centre of the frame worse than what Live Text copies from the same photo,

then do not build the camera. Build the cheaper half instead: an image and text **share target** in
front of the existing capture flow, which lets the platform's own OCR do the reading.

## How it fits what already exists

- **Nothing new writes the graph.** "Add" is the existing `POST /capture` followed by
  `saveArticle(parseArticle(text))`. The sentence goes in as `text`, so it becomes an attestation
  exactly as a pasted sentence does. The chosen unit goes in as `headword`, a hint resolve may still
  correct. The capture rule in AGENTS.md is that adding a transport must not add a second pipeline,
  and a camera is a transport.
- **The duplicate path is reused unchanged.** `/capture` already returns `duplicates` and
  `foldable`, and `AddView.tsx`'s `onFoldIn` already opens the stored article and asks the AskDock
  to fold the sentence in. A photo of a word the owner holds needs no new merge logic.
- **Geometry comes from an OCR engine, never from a language model.** A multimodal model can read
  a page, but its boxes are approximate and its transcription can be invented, and constrained
  decoding is not used anywhere in Acervo, so there is no way to hold it to a shape. The model is
  used only where judgement is needed: which unit was meant, what it means here, and whether an
  OCR'd sentence needs a light repair.
- **Online-only, like every write.** Photo capture needs the server. It fails visibly when the
  server cannot be reached and queues nothing.

## The pipeline

### 1 · Capture on the device

`PhotoCapture.tsx`, adapted from the camera in the owner's calorie logger, which already works well
as a PWA:

- `getUserMedia` with `facingMode: { ideal: "environment" }`.
- A canvas the frame freezes into, so what was sent is what is on screen.
- The camera stopped on `visibilitychange`.
- Plain error messages for `NotAllowedError`, `NotFoundError` and `NotReadableError`.

The frame is re-encoded through the canvas, which also strips EXIF. **It is not cropped to a
square.** The spike measured what the square costs: sentences run past it, and a landscape page
loses the start and end of every line. On Vision the square crop lowered correct sentences from 98%
to about 70%, and removed 4 of 54 tapped words from the image entirely. Send the frame the
viewfinder shows; the sheet below the frame is a layout decision, not a crop.

The upload is **2048 px on the long edge at JPEG quality 0.85**, about 400 KB. At 1280 px (about
190 KB) Vision still hits the tapped word 98% of the time, but character error on camera sentences
rises from 0.4% to 2.3%. So 1280 is the setting for a poor uplink, not the default. Three ways to
take the picture are still to be compared on the owner's phone:

| Path | Resolution | Cost |
| --- | --- | --- |
| Grab a video frame | Usually at most 1080p | Instant, no extra tap |
| `ImageCapture.takePhoto()` | Full sensor, Android Chrome only | A short delay |
| `<input type=file accept=image/* capture=environment>` | Full sensor, the native camera's autofocus | One more tap and a context switch |

Focus matters as much as resolution: the fixtures are soft at the edges, and a video stream may
never focus as hard as the native camera does.

### 2 · `POST /api/acervo/v1/photo/read`

An image goes in and a page layout comes out. Coordinates are normalised to the stored image:

```text
language                 detected, checked against the owner's vocabularies
words[]                  id, text, polygon, confidence, lineId
lines[]                  id, polygon, wordIds
sentences[]              id, text, wordIds, start, end, truncatedStart, truncatedEnd
photoRef                 the pending photo (see "The photo is kept with the attestation")
```

The server does the cleanup a page needs, so the interface only ever hit-tests:

- **Reading order**, including a two-page spread and a page that curves toward the spine.
- **Hyphenation across a line break** (`pala-` / `bra`) joined into one word that keeps both
  polygons, so tapping either half selects it.
- **Sentence segmentation by SaT** (Segment any Text, `sat-3l-sm` through `wtpsplit-lite`). The
  plan assumed rules would do, and on clean text they do: rules, pySBD and SaT all found 59 of 59
  boundaries in the truth text. OCR output is not clean text, though. A photo's text stream
  carries a status bar, a URL, a heading, show-through from the facing page and a fragment cut off
  by the frame, none of which ends in punctuation. So rules and pySBD glue that noise onto the next
  sentence, and got the boundaries right for only 69% and 74% of taps; SaT got 98%. It costs a
  408 MB model and about 150 ms per page on the Mac. Worth trying before paying that: hard-split on
  Vision's own paragraph and block boundaries, then run rules inside each block.
- **Fragments rebuilt into lines** (RapidOCR only). On a curled or tilted page the detector breaks
  one printed line into pieces and orders them by their top edge, so pieces of neighbouring lines
  interleave. `research/photo_capture/layout.py` chains them back along each line's slope. Vision
  returns lines in reading order already.
- **Truncation flagged.** A sentence cut off by the frame edge is marked, so the sheet can say "this
  sentence is cut off" rather than storing a fragment as if it were whole.
- **Low-confidence words kept.** A blurred word at the edge stays tappable but is visibly marked.
  Hiding it would hide exactly the word the owner meant to tap.

### 3 · Tap → meaning, speculatively

Hit-testing is a pure module, `photoText.ts`, pure in the way `selectors.ts` is: it finds the
nearest word within a tolerance, then that word's sentence. Dragging across words, or tapping a
neighbour, extends the selection into a phrase.

The tolerance must be relative to the **line height**, not the image. The spike used a fixed 3% of
the image width, and on RapidOCR's output several "misses" were a tap on a word the OCR had lost
selecting the word on the line above instead. A tap on nothing should select nothing, so the owner
sees that the word was not read, rather than getting the meaning of a different word.

Every tap fires a **quick call** straight away. It is cancelled with `AbortController` when the
selection moves, and cached per (sentence, selection), so tapping back is free. The quick call
returns:

- the resolved lexical unit;
- a short in-context gloss in `glossLangs[0]`;
- `duplicates` and `foldable`, exactly as `/capture` returns them.

### 4 · Add

Add runs the existing capture flow with the resolution already in hand, so compose does not pay
for resolve a second time.

## Splitting capture so the quick call is not a second pipeline

`run_capture` in `src/acervo/api/routes/capture.py` already runs its steps in the right order:
resolve, then the vocabulary checks, then duplicates, then compose. Split it at the duplicate check
into two functions, and have both routes call them:

- **The quick call** runs the first half and returns `resolution`, `duplicates` and `foldable`. It
  costs one model call.
- **`/capture`** accepts an optional `resolution` from an earlier quick call. It validates that
  resolution against the same vocabularies, never trusts it as given, and then composes.

The in-context gloss is a new field in `prompts/acervo_resolve.md`, and its language is stated
(`glossLangs[0]`), because a prose field with no stated language drifts from request to request.

The quick call is where latency lives, so it runs on a fast model, and the spike says which kind of
model. Gemini 3.5 flash-lite answered in **1.02 s at the median** (1.64 s p90), with the right unit
85% of the time exactly and 98% counting near misses. Vertex Gemini 3.5 Flash was more accurate
(95% exact) but took 4.4 s, which the tap cannot afford.

That is a real reason for the quick call to have **its own model kind** rather than share `text`
with compose: the owner's `text` chain is ordered for writing good entries, and this call is ordered
for answering while a finger is still on the glass. The draft prompt is
`research/photo_capture/quick_prompt.md`. Its one systematic miss is an idiom cut short, so its
multi-word rule needs another pass: `doquier` for *por doquier*, `azar` for *al azar*, `caliza`
for *piedra caliza*.

## The photo is kept with the attestation

The picture is part of the provenance. For a book, it shows where on the page the word was, so the
owner can go back to it. For a sign or a landmark, the picture *is* the memory. The dictionary is
private, so keeping photos of pages raises no question of sharing.

**Model.** An attestation gains two nullable fields:

- `photoRef`: a path relative to `ACERVO_MEDIA_PATH`, as `imageRef` is for a sense picture.
- `photoRegion`: the normalised polygons of the selected words and their sentence, so the article
  can draw the same highlight again.

This is a schema change, so it costs a `--reset-database`. `SOURCE_KINDS` probably gains a kind for
something seen out in the world rather than read; name it during the build.

**Who writes the file, and who writes the row.** AGENTS.md requires that a media file and the row
naming it be written by the same party, or one of them is a lie. Here the server writes the file,
but the row goes through the ordinary `saveArticle`. This design keeps the rule true without adding
a second writer:

1. `/photo/read` stores the uploaded image, cropped and EXIF-free, content-addressed as
   `photos/{owner}/pending/{sha256}.jpg`, and returns its ref.
2. The Add document's attestation names that ref. `merge_graph` **refuses** a `photoRef` with no
   file under that owner's pending directory, and in the same write moves the file out of
   `pending/`. The row can never name a missing file, and there is still one writer of the graph.
3. A sweep deletes pending photos older than a day. A photo nobody added costs nothing.

**Reading.** A photo is fetched as a blob behind bearer auth and cached in `mediaStore.ts`, exactly
as sense pictures are, so it works offline once seen. The attestation shows a thumbnail, and tapping
it opens the full frame with the highlight drawn.

**Keeping the photo is a switch** on the sheet, on by default. Adding a word without its picture
must stay one tap away.

**Export is an open question.** Bundles carry no media today, so the first version leaves photos
out of them and says so in the export panel.

## Where OCR runs

Measured, not assumed: **Google Cloud Vision (`DOCUMENT_TEXT_DETECTION`) reads the photo**, as the
first row of a new `ocr` kind in `models/catalogue.json`. That way a 429 falls through the chain
like any other call. It returns word polygons, block and paragraph structure and a detected
language, and it can use the Google project Vertex is already set up under. LiteLLM does not cover
it, so it is reached by hand, the way `cloudflare.py` reaches Cloudflare. Price: the first 1,000
images a month are free, then $1.50 per 1,000, which a personal dictionary is unlikely to reach.

**RapidOCR on the NAS is not a usable interactive fallback**, and two separate measurements say
so:

- **Too slow.** On the NAS's Ryzen R1600, one 2048 px photo took 6.7 s at the median with 4 threads
  (9.9 s with 1), and a 1280 px one took 4.8 s, all at about 1 GB of memory. The budget from shutter
  to tappable is 3 s.
- **Not accurate enough on book photos.** On camera photos RapidOCR hit the tapped word 68% of the
  time against Vision's 100%. It misses whole blocks where a page tilts or softens, and no detector
  setting recovered them.

On screenshots it was as good as Vision: 100% of words and 90% of sentences.

So the second row is a **degraded mode, not an equal**. When Vision is unavailable, RapidOCR can
still read a screenshot, with the sheet saying up front that this takes several seconds; for a book
photo it should say the reading may be incomplete. Whether that degraded mode is worth building at
all, or whether "Vision is unavailable, try again later" is the honest answer, is the owner's
decision. Running RapidOCR on the Mac worker would not help, because the Mac is not always on,
which is the point of a fallback.

**Rejected as the source of geometry:** Tesseract, which does poorly on camera photos, and a
multimodal model, for the reasons above.

The code layout follows `images/`. `src/acervo/ocr/` is a standalone package holding the engines,
layout and segmentation, and it imports nothing of Acervo's beyond `acervo.models`. The binding
layer is `services/photo.py`, and `test_layering.py` enforces both.

## Interface decisions worth making early

- **The highlight is an SVG laid over the frozen image, using the image's own `viewBox`.** This is
  *not* the overlay AGENTS.md prohibits for the YAML editor. That one failed because two
  independent text layouts had to agree pixel for pixel. Here there is one coordinate system, the
  image's pixels, and nothing to drift.
- **Frame above, sheet below, never side by side**, for the reason the AskDock is a sheet: it must
  work on a tablet in portrait, which is the device that matters most.
- **The sentence box is editable** before Add, so an OCR error is fixed in the text that gets
  stored rather than preserved in it.
- **A street sign has no sentence.** Resolve decides whether the recognised line is a sentence. If
  it is not, no attestation text is created, and the photo is kept by itself.

## Not in the first build

- **An image share target** (the Web Share Target API: a multipart POST handled by the service
  worker) sends a screenshot from any app into the same screen. It is Android only for a PWA, since
  iOS offers PWAs no share target; the macOS host could accept a dropped image instead. The text
  share target is a separate, smaller piece of work.
- **Photos taken offline and kept for later: no.** Writes are online-only, and a photo capture is a
  write. The camera says the server is unreachable.

## Spike results

Run on 15 September 2026, Spanish only, against the 13 fixtures. The full tables regenerate offline
from the cache with `research/photo_capture/report.py`, and the README there says how to rerun
everything.

### How it was measured

- **Ground truth.** Every sentence was transcribed by reading the full-resolution photos: 59 taps,
  54 **primary** (the word in the sharp centre, where the owner aims) and 5 **edge** (a soft or
  cut-off line), all in the manifest. The transcription agreed with Cloud Vision character for
  character on nearly every sentence. Two independent readers matching is the check that the
  truth is sound, but **the owner should still spot-check it**.
- **Scoring.** A sentence's character error rate (CER) is measured by aligning the truth inside
  the engine's text, so OCR quality and sentence splitting are scored separately. A tap is placed at
  its word's centre on Vision's full-resolution reading, then asked of every engine and every
  upload size.

### Thresholds, set before measuring

| Measure (primary taps) | Threshold | Vision, 2048 px, SaT | RapidOCR best, 2048 px |
| --- | --- | --- | --- |
| CER of the tapped word | ≤ 1% | **0.3%** ✓ | 15% ✗ |
| CER of its sentence | ≤ 5% | **1.3%** ✓ | 12% ✗ (screenshots 4.2%, camera 17%) |
| Right word hit | ≥ 95% | **98%** ✓ (camera 100%) | 80% ✗ (screenshots 100%, camera 68%) |
| Right whole sentence | ≥ 90% | **98%** ✓ | 69–80% ✗ |
| Right unit from the quick call | ≥ 85% | **85% exact, 98% near** ✓ (Gemini 3.5 flash-lite) | — |
| Shutter → tappable, p50, 5 Mbps | ≤ 3 s | **≈ 1.6–1.9 s** ✓ | ≈ 7.5 s ✗ |
| Tap → meaning, p50 | ≤ 1.5 s | **1.02 s** ✓ | — |

The one Vision word miss was `índole` read as `indole` on screen-03; the one sentence miss was the
sentence that screenshot's floating browser control covers.

### OCR by upload

| Engine | Upload | Bytes | CER camera | CER screenshot | Word hit | Sentence right |
| --- | --- | --- | --- | --- | --- | --- |
| Vision | full, 1280 px | 193 KB | 2.3% | 0.1% | 98% | 98% |
| Vision | **full, 2048 px** | 404 KB | **0.4%** | **0.0%** | **98%** | **98%** |
| Vision | full, original | 1243 KB | 0.2% | 0.1% | 100% | 98% |
| Vision | square centre, 2048 px | 500 KB | 12% | 31% | 91% | 70% |
| RapidOCR v5 mobile, Latin | full, 2048 px | 404 KB | 31% | 0.2% | 80% | 72% |
| RapidOCR v5 mobile, Latin, box .3 | full, 2048 px | 404 KB | 16% | 0.2% | 80% | 69% |
| RapidOCR v6 detector, v5 Latin, box .3 | full, 2048 px | 404 KB | 18% | 0.2% | 76% | 80% |

On camera photos RapidOCR's CER comes from whole passages **missed**, not letters misread. The
detector drops lines where the page tilts, curls or softens: the bottom quarter of camera-01, a
whole paragraph of camera-05 inside the centre square. Vision reads both perfectly. A lower
detector threshold, a looser box, contrast enhancement and tiling each recovered a little and none
recovered the passage. camera-01 and camera-02 are the same page a moment apart, and RapidOCR lost
the same lines in both, so the loss is systematic rather than noise.

### Latency

| Stage | Measured | Where |
| --- | --- | --- |
| Encode on the phone | not measured; a canvas JPEG is ~0.1–0.3 s | — |
| Upload 404 KB | 0.65 s at 5 Mbps · 2.2 s at 1.5 Mbps · 0.16 s at 20 Mbps (computed) | — |
| Vision round trip | 0.57 s median (0.5–1.2 s) | from the Mac |
| RapidOCR v5 Latin, 2048 px | 6.7 s median, 4 threads · 9.0 s with 2 · 9.9 s with 1 | NAS, R1600 |
| RapidOCR v5 Latin, 1280 px | 4.8 s median, 4 threads | NAS |
| RapidOCR v6 detector, 2048 / 1280 px | 6.1 / 4.6 s, 4 threads | NAS |
| Line rebuild + SaT split | 0.5 ms + 151 ms median (1.3 s worst) | Mac |
| Quick call, Gemini 3.5 flash-lite | 1.02 s p50 · 1.64 s p90 | from the Mac |
| Quick call, Gemini 3.1 flash-lite | 2.09 s p50 · 3.36 s p90 | from the Mac |
| Quick call, Cloudflare Llama 3.3 70B | 2.52 s p50 · 4.63 s p90 | from the Mac |
| Quick call, Vertex Gemini 3.5 Flash | 4.36 s p50 · 7.21 s p90 (and 10 of 56 rate limited) | from the Mac |

RapidOCR was timed while DSM's own packages were busy (load average 5–12 on 4 threads), which is
also the condition a capture arrives under. SaT on the NAS is not measured; assume two to three
times the Mac. On a 1.5 Mbps uplink a 2048 px photo misses the 3 s budget on upload alone, and a
1280 px one fits (≈ 2.1 s): the device should step down when the connection is slow.

### The quick call, unit by unit

| Model | Exact | Exact or near |
| --- | --- | --- |
| Gemini 3.5 flash-lite | 85% | 98% |
| Gemini 3.1 flash-lite | 87% | 96% |
| Cloudflare Llama 3.3 70B | 80% | 89% |
| Vertex Gemini 3.5 Flash | 95% (44 answered) | 100% |

"Near" accepts one form containing the other: `cada vez más` for truth `cada vez`, which is
arguably the better answer. Several "exact" misses are the truth's strictness rather than a wrong
answer: `trasuntar` against `trasuntarse`, `destacar` against `destacarse`. The misses that matter
are idioms cut to a word (`doquier`, `azar`, `caliza`, `guardia` for *Guardia Suiza*) and
Llama's invented `confier`.

### What else it found

- **Hyphenation across lines works** once joined in layout: all three hyphenated taps (`consejero`,
  `personalidad`, `compositor`) hit on Vision.
- **Truncation flags were not scored.** The flagger exists, but the spike never compared it with
  the truth. That is the first thing to add when this becomes the OCR package.
- **For info-triage**, which picked RapidOCR for video:
  - Its Cyrillic recognition model covers Spanish characters but reads them badly (`maana`,
    `operacion`, `habia`); the Latin model reads them correctly.
  - RapidOCR silently shrinks every image to 2000 px (`Global.max_side_len`) before detection,
    which is probably why raising the detector size "changed nothing" there.
  - The v5 server detector took 29 s and the v6 medium models about 18 s per photo on the Mac, and
    neither was more accurate.
- **Not done:** the camera-path comparison on the phone (video frame, `takePhoto()`, native
  picker). It waited on the result above, which says the idea survives, so it is next.

## Chinese and Japanese: a separate spike

Not run, and deliberately not folded into this one:

- **OCR is the easy part.** Vision reads both. RapidOCR ships `ch` and `japan` models, but it was
  already too slow for Spanish.
- **A tap lands on a character, not a word.** With no spaces, "the word under the finger" needs a
  word segmenter (jieba, SudachiPy) or, more simply, the quick call choosing the unit around the
  tapped character, which it already does for *New York*.
- **Splitting on 。！？ is easy,** but SaT is what this spike already chose, and it covers both
  languages. Measure it rather than assume it.
- **Vertical Japanese text** changes reading order and the line-rebuilding geometry.
- **It needs its own fixtures:** photos with hand-checked text, and taps whose unit is several
  characters.

The layout format above is character offsets and polygons, so nothing in it assumes spaces.

## Build order after the spike

0. The camera-path comparison on the owner's phone, and the owner's decision on the degraded
   RapidOCR mode (see "Where OCR runs").
1. The OCR package and `/photo/read`, with Vision as the `ocr` row and unit tests driven by the
   fixtures.
2. The capture split and the quick call, with its own fast model kind.
3. `photoRef` and `photoRegion` on attestations, pending-photo promotion in `merge_graph`, and the
   sweep. This step needs one `--reset-database`.
4. `PhotoCapture.tsx`, `photoText.ts` and their styles, with `design/ui-prototype/` changed at the
   same time.
5. The image share target.
