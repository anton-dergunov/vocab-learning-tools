# Photo capture · tap a word in what you're reading

**Status:** built, steps 1–4 of the [build order](#build-order-after-the-spike), with Cloud Vision
as the only reader. The Spanish spike ran first: **the idea survives with Cloud Vision reading the
photo, and not with RapidOCR on the NAS**. See [Spike results](#spike-results), and the
experiment write-up in [`experiments/photo-capture/`](../../experiments/photo-capture/README.md). The
fixtures it measures against are in
[`tests/fixtures/photo-capture/`](../../tests/fixtures/photo-capture/README.md).
Several sections below have been corrected by what it measured, and by what the build decided —
[What the build decided](#what-the-build-decided) lists those. Chinese and Japanese are a separate
spike, not yet run.

Today a word reaches Acervo by being typed or pasted into Add. That works for text already on a
screen. It is awkward for a word met in a printed book, and it throws away the thing a personal
dictionary most wants: the sentence the word was met in, and a memory of where.

## Outcome

Add has a **Photo** tab beside Text, Article and YAML. It is never where Add opens, and the camera
turns on only when "Take a photo" is pressed: photo capture is an occasional way in, and a camera
that switches itself on is one nobody asked for. The viewfinder fills the top of the screen, leaving
room for a sheet below it, and a second button chooses an existing image or screenshot instead. The whole
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

The frame is re-encoded through the canvas, which also strips EXIF. **Every photo is shown in one
square, and a camera photo *is* that square**: the viewfinder is square, and the shutter keeps
exactly the square it showed, so the photo framed, the photo read and the photo kept are one photo.
A square also leaves the phone the height it needs for the sheet below, and matches every other
picture in Acervo.

That is not the crop the spike warned against. The spike cut a centre square out of photos the owner
had framed as portraits, and so cut off sentences they had taken care to include — correct sentences
fell from 98% to about 70%. A square viewfinder is framed as a square; nothing is cut that was seen.

An image that is not square — a screenshot, a photo chosen from the gallery — fills the square's
width, so a phone screenshot reads at about its real size, and scrolls up and down inside it, with a
fade at the edge that has more. It never scrolls sideways, so a sideways drag along a line is always
free to select a phrase. Vision reads the whole image, so every sentence stays tappable wherever it
is scrolled to; what is **kept** is the square on screen when Add is pressed, cropped on the device
and stored through `POST /photo/store` without a second reading.

The upload is **2048 px on the long edge at JPEG quality 0.85**, about 400 KB. At 1280 px (about
190 KB) Vision still hits the tapped word 98% of the time, but character error on camera sentences
rises from 0.4% to 2.3%. So 1280 is the setting for a poor uplink, not the default. Of the three ways
to take the picture, **the video frame is the one used**: on the owner's phone `takePhoto()` returned
a narrower field of view than the preview, so every line lost its start and end between framing and
reading. What is on screen is what is read, at the cost of resolution — a video frame is about
1080–1440 px square, where the spike measured the tapped word still found 98% of the time at 1280:

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
  interleave. `experiments/photo-capture/layout.py` chains them back along each line's slope. Vision
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
`experiments/photo-capture/quick_prompt.md`. Its one systematic miss is an idiom cut short, so its
multi-word rule needs another pass: `doquier` for *por doquier*, `azar` for *al azar*, `caliza`
for *piedra caliza*.

## The photo is kept with the attestation

The picture is part of the provenance. For a book, it shows where on the page the word was, so the
owner can go back to it. For a sign or a landmark, the picture *is* the memory. The dictionary is
private, so keeping photos of pages raises no question of sharing.

**Model.** An attestation gains two fields, empty for one that was typed or pasted:

- `photoRef`: a path relative to `ACERVO_MEDIA_PATH`, as `imageRef` is for a sense picture.
- `photoRegion`: the normalised polygons of the selected words and their sentence, so the article
  can draw the same highlight again.

This is a schema change, carried across by a throwaway converter (`./deploy.sh --transition`) rather
than a `--reset-database`, since it only adds two columns. `SOURCE_KINDS` gains `sign`, for text
seen out in the world rather than read: a street sign, a menu, a label.

**Who writes the file, and who writes the row.** AGENTS.md requires that a media file and the row
naming it be written by the same party, or one of them is a lie. Here the server writes the file,
but the row goes through the ordinary `saveArticle`. This design keeps the rule true without adding
a second writer:

1. `/photo/read` stores the uploaded image, EXIF-free, content-addressed as
   `photos/{owner}/pending/{digest}.jpg`, and returns the ref it will have **once kept**,
   `photos/{owner}/{digest}.jpg`. Nothing ever rewrites a ref, and a second word saved from the same
   photo finds it already kept.
2. The Add document's attestation names that ref. `merge_graph` **refuses** a new `photoRef` whose
   file is neither kept nor pending under that owner, and in the same write moves it out of
   `pending/` — back again if the transaction does not commit. The row can never name a missing
   file, and there is still one writer of the graph.
3. A runner tick deletes pending photos older than a day. A photo nobody added costs nothing.
4. The media route serves `photos/{owner}/…` to that owner only, and never a pending one.
5. A kept photo is not deleted with its attestation: undo restores the tombstone, and one photo may
   back several words.

**Reading.** A photo is fetched as a blob behind bearer auth and cached in `mediaStore.ts`, exactly
as sense pictures are, so it works offline once seen. The attestation shows a thumbnail — and so
does the example drawn from it, because capture shows a sentence you supplied as that example and
not under "Where you met it" — and tapping it opens the full frame with the highlight drawn. The
device puts the bytes it uploaded into that cache under the kept ref before review, so the article
being reviewed shows the photo the server does not serve yet.

**Keeping the photo is a switch** on the sheet, on by default. Adding a word without its picture
must stay one tap away.

**Export leaves photos out**, and the export panel says so: a word file drops `photoRef` and
`photoRegion`, and an attestation that was only a photo has nothing left to say without it.

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

**Decided: Vision is the reader, and the first build has no second row.** When Vision is
unavailable, the camera says so and the owner tries again later. A bigger local model is not the
way out: on this hardware the larger models the spike tried were slower and no more accurate (see
the experiment's "Why not a better model on the NAS").

If access to Vision changes, there are two fallbacks, in this order:
1. **Azure AI Vision Read.** 5,000 free transactions a month and word polygons, but not yet
   measured. Measure it first, with the spike's harness.
2. **RapidOCR as a degraded mode.** It can read a screenshot, with the sheet saying up front that
   this takes several seconds. For a book photo the sheet should also say the reading may be
   incomplete.

Running RapidOCR on the Mac worker would not help, because the Mac is not always on, which is the
point of a fallback.

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

## What the build decided

- **The quick call is `POST /capture/resolve`.** It is `pipeline.understand` — resolve, the
  vocabulary checks and the duplicate check — on the `quick` chain, with `prompts/acervo_resolve.md`'s
  `quick` and `photo` sections switched on. The tap is marked in the text with asterisks, which is
  how the resolve prompt already reads a pointer. `/capture` takes the `resolution` back, checks
  every field again and refuses a sentence its own text does not contain.
- **Two model kinds, not one.** `quick` is the text models in a second order; `ocr` is a catalogue
  kind of its own with `google-vision` its only row. Both appear in Settings ▸ Models.
  `models/google_vision.py` answers provider-neutral `OcrWord`s with their block and paragraph, so
  Azure AI Vision Read is one more row and one more adapter.
- **SaT on the page's whole text.** Splitting on Vision's paragraphs first was measured and loses
  (step 7 of the experiment): rules rise from 69% to 81%, and SaT falls from 98% to 87%, because
  Vision starts paragraphs mid-sentence. SaT is pinned in `models/segmenter.json`, baked into the
  image, and loaded when the Photo tab opens rather than at startup.
- **The camera path** is the video frame, cut to the square the viewfinder shows. `takePhoto()` was
  tried first and dropped: its field of view differed from the preview's. "Choose an image" is the
  native camera's route, and a gallery photo scrolls in the square like a screenshot.
- **Folding a sentence in does not keep the photo.** It goes through the article conversation, which
  carries text; keeping the photo there is future work.
- **A sign is a photo with no sentence**: an attestation with empty text is allowed when it carries a
  photo, and no example is drawn from one.

## Spike results

The Spanish spike ran on 15 September 2026. Its method and every number are in
[`experiments/photo-capture/`](../../experiments/photo-capture/README.md); this section keeps only
what it decided.

- **Cloud Vision passed every threshold set before measuring:**
  - the right word hit 98% of the time (100% on book photos);
  - 98% of sentences came out right, with character error 0.4% on book photos;
  - shutter to tappable took about 1.6–1.9 s on a 5 Mbps uplink.
- **RapidOCR is a weaker, slower fallback.** It matched Vision on screenshots, but hit only 68% of
  words on book photos, and took 4.6–6.7 s per photo on the NAS.
- **A bigger local model is not the way out.** Larger models were slower and no more accurate, so
  Vision is the reader. See "Where OCR runs".
- **Read the whole frame at 2048 px**, and step down to 1280 px on a slow uplink.
- **Split sentences with SaT.** Rules fail on the page's non-sentence text.
- **Run the quick call on a fast model** (Gemini 3.5 flash-lite answered in 1.02 s at the median),
  and give its prompt's multi-word rule another pass.
- **Other OCR APIs** are compared there too. If a fallback is ever wanted, measure Azure AI Vision
  Read before building the RapidOCR degraded mode.

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

0. The camera path: settled on the video frame after using it (see above). The owner decided
   against the degraded RapidOCR mode for the first build.
1. **Built.** The OCR package and `/photo/read`, with Vision as the `ocr` row.
2. **Built.** The capture split and the quick call, with its own fast model kind.
3. **Built.** `photoRef` and `photoRegion` on attestations, pending-photo promotion in `merge_graph`,
   and the sweep — carried across by a throwaway converter rather than a reset.
4. **Built.** `PhotoCapture.tsx`, `photoText.ts` and their styles, with `design/ui-prototype/`
   changed at the same time.
5. The image share target.
