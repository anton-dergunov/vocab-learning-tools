# Experiment · photo capture: OCR, sentences and tap → meaning

Spike for [`docs/photo-capture.md`](../../docs/photo-capture.md): photograph a page,
tap a word, see its sentence and its meaning in context. The plan keeps the decisions; this document
holds the question, the method and every number. The photos and the hand-written truth are in
[`tests/fixtures/photo-capture/`](../../tests/fixtures/photo-capture/README.md).

**Run:** 15 September 2026 · Spanish only · 13 fixtures (9 phone photos of two printed books, 4
screenshots of web pages).

## Outcome

**The idea survives with Google Cloud Vision reading the photo, and not with RapidOCR on the NAS.**
Vision passed every threshold set before measuring. RapidOCR was as accurate as Vision on
screenshots, but on book photos it lost the tapped word a third of the time. On the NAS it took
4.6–6.7 s per photo, against a 3 s budget.

Four design corrections came out of it:
- Read the **whole frame**, not a square crop.
- Upload at **2048 px**, stepping down to 1280 px on a slow connection.
- Split sentences with **SaT**, not rules.
- Run the tap → meaning call on a **fast model kind of its own**.

## The questions

1. How accurately does each engine read the tapped word and its sentence, on photos versus
   screenshots?
2. What does the upload size cost in accuracy and in bytes, and what does cropping to a square cost?
3. Which sentence splitter gets the tapped word's sentence right, on real OCR output?
4. Does a fast model pick the right word or phrase from a single tap, quickly enough?
5. How long does each stage take, on the hardware that would run it?

## Method

- **Ground truth.** Every sentence touching the centre of each frame was transcribed by reading the
  full-resolution photos. There are 59 taps: 54 **primary**, a word in the sharp centre where the
  owner aims (every threshold is judged on these), and 5 **edge**, a soft or cut-off line, reported
  but not optimised for. The transcription agreed with Cloud Vision character for character on
  nearly every sentence, which is the check that it is sound; **the owner should still spot-check
  it**.
- **Engines.** Cloud Vision `DOCUMENT_TEXT_DETECTION` with a Spanish hint, and RapidOCR 3.9.2 on
  ONNX Runtime 1.28 in three configurations. Both are reduced to one layout: words, polygons, lines
  and line breaks.
- **Uploads.** Each fixture was re-encoded as the phone would send it: full frame or square centre,
  at 1280 px, 2048 px or original size, JPEG quality 0.85.
- **Scoring.**
  - A sentence's character error rate (CER) is measured by *aligning* the truth inside the engine's
    text, so reading and splitting are scored separately.
  - A tap sits at its word's centre on Vision's full-resolution reading, mapped into each upload's
    coordinates. It counts as hit when the token under it matches the word.
  - A sentence counts as right when its CER against the truth is at most 10%.
  - A boundary counts as right when the splitter's span matches where the truth sentence aligns.
- **Tap → meaning.** A draft prompt (`quick_prompt.md`) through Acervo's own `llm_json`, pinned to
  one model at a time, fed the sentence *as Vision read it*, so OCR damage is part of the test.
- **Latency.**
  - Vision was timed from the Mac.
  - RapidOCR was timed on the NAS (AMD Ryzen Embedded R1600, 4 threads, 20 GB) in a throwaway
    Python 3.12 environment, since DSM's own Python is 3.8. No Docker and no sudo; deleted
    afterwards.
  - Upload time is computed from bytes at three uplink speeds.

## Results

### Against the thresholds

| Measure (primary taps) | Threshold | Vision, 2048 px, SaT | RapidOCR best, 2048 px |
| --- | --- | --- | --- |
| CER of the tapped word | ≤ 1% | **0.3%** ✓ | 15% ✗ |
| CER of its sentence | ≤ 5% | **1.3%** ✓ | 12% ✗ (screenshots 4.2%, camera 17%) |
| Right word hit | ≥ 95% | **98%** ✓ (camera 100%, screenshots 95%) | 80% ✗ (screenshots 100%, camera 68%) |
| Right whole sentence | ≥ 90% | **98%** ✓ | 69–80% ✗ |
| Right unit from the quick call | ≥ 85% | **85% exact, 98% near** ✓ (Gemini 3.5 flash-lite) | — |
| Shutter → tappable, p50, 5 Mbps | ≤ 3 s | **≈ 1.6–1.9 s** ✓ | ≈ 7.5 s ✗ |
| Tap → meaning, p50 | ≤ 1.5 s | **1.02 s** ✓ | — |

Vision's single word miss was `índole` read as `indole`, a small accent in a thin, light-grey font
on screen-03. Its single sentence miss is on the same screenshot, where a floating browser control
covers part of the sentence. That one miss is why screenshots read 95% and camera photos 100%. With
20 and 34 taps the two figures are not meaningfully different; over all text, screenshots read
cleaner (0.0% sentence CER against 0.4%).

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

- **The square crop** removed 4 of 54 tapped words from the image and cut sentences that ran past
  it. A landscape page lost the start and end of every line.
- **RapidOCR's camera CER comes from whole passages missed, not letters misread.** Its detector
  drops lines where the page tilts, curls or softens: the bottom quarter of camera-01, and a
  paragraph of camera-05 inside the centre square. Vision reads both perfectly.
  - A lower box threshold, a looser threshold, contrast enhancement and tiling each recovered a
    little, and none recovered the passage.
  - camera-01 and camera-02 are the same page a moment apart, and RapidOCR lost the same lines in
    both: a systematic failure, not noise.
- **RapidOCR on a curled page** also breaks one printed line into fragments and orders them by top
  edge, so neighbouring lines interleave. `layout.py` rebuilds lines along each line's slope, which
  took camera-07's sentence CER from 23% to 4% on one sentence and 33% to 15% on another.

### Sentence splitting

| Splitter | Truth text | Vision OCR: boundary right | RapidOCR OCR: boundary right |
| --- | --- | --- | --- |
| Rules | 59 / 59 | 69% | 57% |
| pySBD (Spanish) | 59 / 59 | 74% | 63% |
| **SaT** `sat-3l-sm` | 59 / 59 | **98%** | 70% |

On clean text any splitter will do. OCR output carries a status bar, a URL, a heading, text showing
through from the facing page and fragments cut by the frame, none of which ends in punctuation. So
rules and pySBD glue it onto the next sentence, and SaT does not. SaT costs a **408 MB model** and
**151 ms per page** at the median on the Mac (1.3 s worst).

**Splitting on Vision's own paragraphs first does not rescue rules** (step 7, `blocks.py`, run
24 September 2026 on the cached 2048 px readings, so no new call). The idea was that Vision already
knows a status bar or a heading is a paragraph of its own, so cutting there would leave rules only
clean prose to split. It helps, and not enough:

| Splitter | Boundary right, primary taps | Camera | Screenshot | Median time |
| --- | --- | --- | --- | --- |
| Rules | 69% | 71% | 65% | 0.0 ms |
| SaT | **98%** | 100% | 95% | 57 ms |
| Paragraphs, then rules | 81% | 79% | 85% | 0.1 ms |
| Paragraphs, then SaT | 87% | 88% | 85% | 85 ms |

Cutting on paragraphs also makes SaT *worse*, because Vision ends a paragraph where a sentence does
not end. In all six taps SaT had right and the paragraph cut broke, Vision had started a new
paragraph at an ordinary line break mid-sentence (`…operan simultáneamente` / `confiriendo…`), on
book photos and on a screenshot alike. SaT on the page's whole running text is therefore what ships.
A paragraph cut is a cut in the wrong place often enough to cost more than it saves, and rules are
written for Spanish punctuation where SaT is multilingual. Both of those matter more for Chinese and
Japanese, where there are no spaces to split on and the punctuation differs. The Chinese and
Japanese spike still has to measure SaT itself.

### Tap → meaning

| Model | Exact | Exact or near | p50 | p90 |
| --- | --- | --- | --- | --- |
| **Gemini 3.5 flash-lite** (free tier) | 85% | 98% | **1.02 s** | 1.64 s |
| Gemini 3.1 flash-lite (free tier) | 87% | 96% | 2.09 s | 3.36 s |
| Cloudflare Llama 3.3 70B | 80% | 89% | 2.52 s | 4.63 s |
| Vertex Gemini 3.5 Flash | 95% (44 of 54 answered) | 100% | 4.36 s | 7.21 s |

- **"Exact"** compares the lemma to the truth after folding case, accents and articles. **"Near"**
  accepts one containing the other: `cada vez más` for truth `cada vez`, arguably the better answer.
- **Several exact misses are the truth being strict:** `trasuntar` against `trasuntarse`,
  `destacar` against `destacarse`.
- **The misses that matter** are idioms cut down to a word (`doquier` for *por doquier*, `azar` for
  *al azar*, `caliza` for *piedra caliza*, `guardia` for *Guardia Suiza*) and Llama's invented
  `confier`. The prompt's multi-word rule needs another pass.
- **Limits:** the free Gemini tier allows 15 requests a minute per model, and the Vertex project
  rate-limited 10 of 56 calls.

### Latency

| Stage | Result | Where |
| --- | --- | --- |
| Encode on the phone | not measured; a canvas JPEG is ~0.1–0.3 s | — |
| Upload 404 KB | 0.65 s at 5 Mbps · 2.2 s at 1.5 Mbps · 0.16 s at 20 Mbps (computed) | — |
| Vision round trip | 0.57 s median (0.5–1.2 s) | from the Mac |
| RapidOCR v5 Latin, 2048 px | 6.7 s median at 4 threads · 9.0 s at 2 · 9.9 s at 1 | NAS |
| RapidOCR v5 Latin, 1280 px | 4.8 s median at 4 threads | NAS |
| RapidOCR v6 detector, 2048 / 1280 px | 6.1 / 4.6 s at 4 threads | NAS |
| RapidOCR memory | 840 MB–1 GB peak | NAS |
| Line rebuild + SaT | 0.5 ms + 151 ms median | Mac |

- **RapidOCR timings are for a busy NAS.** DSM's own packages were running (load average 5–12 on 4
  threads), which is also the condition a capture arrives under.
- **SaT on the NAS is not measured;** assume two to three times the Mac.
- **On a 1.5 Mbps uplink** a 2048 px photo misses the 3 s budget on upload alone, while a 1280 px
  one fits (≈ 2.1 s), so the phone should step down on a slow connection.

### Also found

- **Hyphenation across lines works** once joined in layout: all three hyphenated taps
  (`consejero`, `personalidad`, `compositor`) hit on Vision.
- **The hit-test should select nothing** when the tapped word was not read. With a fixed tolerance,
  several RapidOCR "misses" selected the word on the neighbouring line instead.
- **For info-triage**, which uses RapidOCR for video:
  - Its Cyrillic recognition model covers Spanish characters but reads them badly (`maana`,
    `operacion`, `habia`), where the Latin model reads them correctly.
  - RapidOCR silently shrinks every image to 2000 px (`Global.max_side_len`) before detection,
    which is probably why raising the detector size "changed nothing" there.
- **Not scored:** the truncation flags, and the camera-path comparison on the phone (video frame,
  `takePhoto()`, native picker).

## Why not a better model on the NAS

The spike tried the larger local models too, and on this hardware bigger was **slower and not more
accurate**:

- The PP-OCRv5 server detector took **29 s** per photo on the Mac (the M1 is roughly twice the
  NAS), and read *worse*.
- The PP-OCRv6 medium models took about **18 s** on the Mac, and were no more accurate.
- info-triage measured Surya at **8.3 s per frame** on the Mac, with PyTorch and a ~3 GB image.

The failures were a detector missing tilted or soft regions, not a recogniser misreading letters,
and more parameters did not find those regions. A local model that matches Vision within a 3 s
budget on a Ryzen R1600 is not realistic. RapidOCR stays what it is: a slower, weaker fallback,
accurate on screenshots.

The one local reader of Vision's quality is **Apple's Vision framework**, which info-triage timed at
136 ms a frame on the Mac. It runs on the device, not the server, so a PWA cannot reach it. The
macOS host, or a native iPad or iOS app, could. Google's ML Kit is the Android equivalent, with the
same constraint.

## Other OCR APIs (desk research, not measured)

Checked in September 2026. Tap-a-word needs **word-level boxes**; a service that returns paragraphs
cannot place a tap.

| Service | Word boxes | Free allowance | Paid | Notes |
| --- | --- | --- | --- | --- |
| **Google Cloud Vision** (measured) | yes | 1,000 images/month, ongoing | $1.50 / 1,000 | The chosen reader. |
| **Azure AI Vision, Read** | yes | 5,000 transactions/month, 20/minute (F0) | not shown on the pricing page | The strongest candidate for a *second cloud row*: the most generous ongoing free tier, and word polygons with confidence. |
| Azure AI Document Intelligence, Read | yes | 500 pages/month (F0) | not shown on the pricing page | The same Read model, packaged for documents; smaller allowance. |
| Amazon Textract, DetectDocumentText | yes | 1,000 pages/month for the first **three months**, new accounts | $1.50 / 1,000 | Not a lasting free option. |
| OCR.space | yes (`isOverlayRequired`) | 25,000 requests/month, 500/day per IP | paid plans | Files up to **1 MB**, which a 2048 px JPEG fits. Spanish, Chinese and Japanese. Says it stores nothing. A small provider; quality unmeasured. |
| Mistral OCR 4 | **no** (paragraph boxes) | — | $4 / 1,000 ($2 batched) | Good at documents, but cannot place a tap on a word. |
| Multimodal LLMs (Gemini, GPT) | approximate only | — | per token | Ruled out as the geometry source: boxes drift and transcription can be invented. |

**Recommendation:** keep Vision as the only row for now. If a fallback is ever wanted, measure
**Azure AI Vision Read** first, before building the RapidOCR degraded mode. It is a new engine in
`engines.py` and a rerun of `report.py`, costs nothing inside its free tier, and would likely be a
real equal rather than a weaker second. OCR.space is the free runner-up worth one run.

Sources: [Cloud Vision pricing](https://cloud.google.com/vision/pricing) ·
[Azure AI Vision pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/computer-vision/) ·
[Azure Document Intelligence pricing](https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/) ·
[Amazon Textract pricing](https://aws.amazon.com/textract/pricing/) ·
[OCR.space API](https://ocr.space/ocrapi) ·
[Mistral OCR 4](https://www.marktechpost.com/2026/06/23/mistral-ocr-4/)

---

## Apparatus

Nothing here ships. `pytest.ini` collects only `tests/`, so this directory's tests run only in its
own environment.

### Environment

Its own, so RapidOCR, OpenCV and SaT never enter the application's requirements:

```sh
cd experiments/photo-capture
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt --override overrides.txt
.venv/bin/python -m pytest -q -c /dev/null test_spike.py
```

`overrides.txt` stops RapidOCR pulling in the GUI build of OpenCV next to the headless one.

Cloud Vision needs an untracked `.env` here naming which credentials it may spend:

```sh
PHOTO_SPIKE_ADC=/path/to/application_default_credentials.json
PHOTO_SPIKE_GCP_PROJECT=your-project-id
PHOTO_SPIKE_GCP_ACCOUNT=learner@account.example.com
```

A Vision call first asks Google whose token it holds, and refuses if the answer is not that
account, or if Google cannot say.

### Files

| File | Job |
| --- | --- |
| `engines.py` | Cloud Vision and RapidOCR, both reduced to one layout. Every response is cached in `runs/cache/`, keyed by settings and image bytes. |
| `layout.py` | Rebuilds RapidOCR's fragments into lines, then joins words into one text with a character span per tappable token, joining hyphenation across lines. |
| `segment.py` | Three sentence splitters: rules, pySBD, SaT. |
| `hit.py` | A tap point to a token and its sentence. |
| `evaluate.py`, `score.py` | Alignment against the truth, tap placement, and every metric. |
| `quick_prompt.md`, `quick.py` | The tap → meaning call, through Acervo's own `llm_json`, one pinned model at a time. Runs in the application's `.venv`. |
| `bench_nas.py` | A self-contained RapidOCR timing script, copied to the server. |
| `spike.py` | `ocr`: fills the engine cache for every fixture and upload size. |
| `report.py` | Every table, from the cache only, plus the quick call's input file. |
| `blocks.py` | Step 7: paragraphs-then-rules against SaT, from the cache only. |
| `record_vision.py` | Records Vision's raw answer for each fixture at 2048 px into `tests/fixtures/photo-capture/vision/`, trimmed to what `acervo.models.google_vision.parse` reads. Thirteen units. |

### Rerunning

```sh
# OCR, cached. Vision costs one unit per image and upload variant.
.venv/bin/python spike.py ocr --engine vision
.venv/bin/python spike.py ocr --engine rapidocr --presets v5m-latin --box-thresh 0.5 0.3
.venv/bin/python spike.py ocr --engine rapidocr --presets v6s-det-v5-latin --box-thresh 0.3

# Tables and runs/taps-vision-full-2048-sat.json, with no network
.venv/bin/python report.py > runs/report.md
HF_HUB_OFFLINE=1 .venv/bin/python blocks.py

# Raw Vision answers for the shipped code's tests. Thirteen units, and the credential check above.
.venv/bin/python record_vision.py

# The quick call, from the repository root, in the application environment
set -a; . ./.env; set +a
.venv/bin/python experiments/photo-capture/quick.py \
  --taps experiments/photo-capture/runs/taps-vision-full-2048-sat.json \
  --pair gemini-free:gemini/gemini-3.5-flash-lite --pace 4.5
```
