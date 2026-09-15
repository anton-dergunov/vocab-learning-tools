# Photo capture · tap a word in what you're reading

**Status:** an idea, unbuilt. A spike comes first, and this document says what the spike has to
measure before anything is built. The fixtures it measures against are already in
[`tests/fixtures/photo-capture/`](../../tests/fixtures/photo-capture/README.md).

Today a word reaches Acervo by being typed or pasted into Add. That works for text already on a
screen. It is awkward for a word met in a printed book, and it throws away the thing a personal
dictionary most wants: the sentence the word was met in, and a memory of where.

## Outcome

Add opens the camera straight away. The frame is roughly square and centred, leaving room below it,
and a second button chooses an existing image or screenshot instead. Taking the picture freezes the
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

The frame is cropped to the centre region and re-encoded through the canvas, which also strips
EXIF.

How large and how compressed the upload is are **spike outputs, not constants**. The calorie
logger's 1280 px long edge at JPEG quality 0.72 is enough for a nutrition label and is probably too
small for a paperback's body text. Three ways to take the picture should be compared on the owner's
phone:

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
- **Sentence segmentation by rules.** No model is needed for this, but Spanish abbreviations are
  (`Sr.`, `pp.`, `aprox.`). Compare PySBD with ICU's BreakIterator on the fixtures.
- **Truncation flagged.** A sentence cut off by the frame edge is marked, so the sheet can say "this
  sentence is cut off" rather than storing a fragment as if it were whole.
- **Low-confidence words kept.** A blurred word at the edge stays tappable but is visibly marked.
  Hiding it would hide exactly the word the owner meant to tap.

### 3 · Tap → meaning, speculatively

Hit-testing is a pure module, `photoText.ts`, pure in the way `selectors.ts` is: it finds the
nearest word within a tolerance, then that word's sentence. Dragging across words, or tapping a
neighbour, extends the selection into a phrase.

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

The quick call is where latency lives, so it should run on a fast model. That is a choice for the
owner's chain, not for code. Whether it needs its own model kind is an open question for the spike.

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

The spike decides this. The design document already places OCR on the always-on server.
Candidates, each fitted to the rule that a provider is a row: a new `ocr` kind in
`models/catalogue.json`, so a 429 falls through the chain like any other call.

- **Local: RapidOCR** (PaddleOCR models on ONNX Runtime, CPU, Python). It is free, private and
  needs no credential. The risk is speed: on a NAS-class CPU a 12 MP frame may take many seconds,
  which the latency budget cannot absorb.
- **Cloud: Google Cloud Vision, `DOCUMENT_TEXT_DETECTION`.** It returns word polygons, block and
  paragraph structure, and a detected language, and it handles phone photos well. It can use the
  Google project Vertex is already set up under. LiteLLM does not cover it, so it is reached by
  hand, the way `cloudflare.py` reaches Cloudflare.
- **Rejected as the source of geometry:** Tesseract, which does poorly on camera photos, and a
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

## Spike

Every question below needs a number, measured against `tests/fixtures/photo-capture/`. Spike code
lives in `research/photo_capture/`, outside the distribution. Results are written back into this
document, the way `../clip-selection-rounds.md` records its rounds.

1. **Ground truth.** Fill in each manifest's `truth` block by hand: the central lines, and three to
   five tap points, each with the word, sentence and unit expected. The screenshots are checked
   against `sources/`. Never generate truth with the engine under test.
2. **OCR accuracy per engine.** Character error rate for the centre region and for the edges
   separately, on camera photos versus screenshots. `camera-01` and `camera-02` are one page taken
   twice, so they also show how much two captures of the same page differ.
3. **Resolution.** Accuracy at a long edge of 1280 px, 2048 px and the original, alongside the bytes
   uploaded at each size. This sets the device's encode settings for spotty mobile data.
4. **Latency, stage by stage.** Encode → upload (throttled to "Fast 4G" in DevTools) → OCR → layout,
   then tap → quick call. Median and p90 for each stage, checked against the kill criterion.
5. **Segmentation.** Sentences split correctly, hyphenation joined, truncation flagged. The tango
   book pages carry footnotes and superscript note markers.
6. **Unit resolution.** From one tap on each fixture tap point, does resolve propose the multi-word
   unit when there is one?
7. **The camera path** on the owner's Android phone: video frame versus `takePhoto()` versus the
   native picker, judged on sharpness at the edges of the frame.

## Build order after the spike

1. The OCR package and `/photo/read`, with unit tests driven by the fixtures.
2. The capture split and the quick call.
3. `photoRef` and `photoRegion` on attestations, pending-photo promotion in `merge_graph`, and the
   sweep. This step needs one `--reset-database`.
4. `PhotoCapture.tsx`, `photoText.ts` and their styles, with `design/ui-prototype/` changed at the
   same time.
5. The image share target.
