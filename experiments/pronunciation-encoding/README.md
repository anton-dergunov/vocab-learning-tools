# Experiment · pronunciation encoding: what should a stored clip be?

Spike for [`docs/plans/pronunciation-and-audio.md`](../../docs/plans/pronunciation-and-audio.md).
The plan keeps the decision; this document holds the question, the method and every number.

**Run:** 15 September 2026 · Spanish · four pieces of speech · blind listening.

## The question

The first clips Acervo recorded sound metallic. The catalogue asks Cloud TTS for
`audioEncoding: "MP3"`, and the reference defines that as *"MP3 audio at 32kbps"*. So: **is the
metallic sound the bitrate we ask for, or the model that produced it** — and if it is the bitrate,
which of the encodings the API offers should a stored clip be in, given that clips are replicated to
every device and therefore cost space twice over?

Cloud TTS bills **per character, never per byte**, so a better encoding costs nothing at the API. The
only trade is size.

## What the API actually returns

Measured before any listening, and three of these were surprises:

| request | WaveNet voice | Gemini voice |
| --- | --- | --- |
| `MP3` | **64 kbps**, 24 kHz mono | **32 kbps**, 24 kHz mono |
| `OGG_OPUS` | 35 kbps | 28–32 kbps |
| `LINEAR16` | 384 kbps (uncompressed 24 kHz PCM) | 384 kbps |
| `M4A` | **byte-identical to the `MP3` answer**, `codec_name=mp3` | `400 Unsupported audio encoding` |
| `MP3` with `sampleRateHertz: 48000` | 64 kbps, resampled | 32 kbps, resampled |

1. **The documented "32kbps" is the floor, not the rule.** A WaveNet voice answers at 64; the Gemini
   voices — the ones that read example sentences, where prosody is the whole point — answer at 32.
   The worst encoding lands on the most valuable material.
2. **`M4A` is not an AAC option.** It returns MP3 bytes under another name where it works at all, and
   the Gemini voices refuse it outright. It is out.
3. **A Gemini voice re-performs the line on every call.** The same request came back 16,992 bytes one
   minute and 22,176 the next. That is a fact about the product as well as the test — "Record again"
   genuinely gives a different reading, not the same audio re-encoded — and it invalidated the first
   version of this experiment, which compared one encoding per call.

## Method

Because of (3), each piece is synthesised **once** as `LINEAR16`, and every candidate is that one
master encoded locally with ffmpeg. The bitrates are chosen to match what the API returns, so the
comparison stands in for a choice between its own encodings.

| piece | text | voice | direction |
| --- | --- | --- | --- |
| word 1 | picar | es-ES-Wavenet-F | — |
| word 2 | la sobremesa | es-ES-Wavenet-F | — |
| sentence 1 | ¡Me pica todo el cuerpo desde que volví del campo! | Gemini 3.1 flash TTS · Kore | exasperated, scratching and complaining |
| sentence 2 | Espero que se mejoren pronto. Un abrazo a toda la familia. | Gemini 3.1 flash TTS · Kore | warm and tender, a goodbye full of care |

Five candidates per piece: `LINEAR16` (the master, and the hidden anchor), `MP3_32`, `MP3_64`,
`OPUS_32`, `MP3_128` (the control — if this is clean and 32 kbps is not, the bitrate is the culprit;
if the master itself sounds metallic, the model is).

**Blind by construction.** Every candidate is decoded back to a plain 24 kHz WAV under a shuffled id,
so the file extension cannot name the codec, while the artifacts — the thing being judged — survive
decoding untouched, which is what a player does anyway. The mapping lives in `out/key.json` and is
read only after the whole sheet is scored.

```bash
export ACERVO_VERTEX_PROJECT=…
.venv/bin/python experiments/pronunciation-encoding/run.py make      # writes out/listen.md
# … score every row of out/listen.md …
.venv/bin/python experiments/pronunciation-encoding/run.py reveal    # mapping, scores, sizes
```

`out/` is ignored: twenty WAVs of the same four lines are not worth a repository. The numbers below
are.

## Results

One listener, one sitting, headphones, 20 files. Scores out of five for how clean each sounds.

| candidate | scores | mean | word file | sentence | bytes/s |
| --- | --- | --- | --- | --- | --- |
| `LINEAR16` (master) | 5 · 5 · 5 · 5 | **5.0** | 41.7 KB | 237 KB | 48,000 |
| `MP3_128` | 5 · 5 · 5 · 5 | **5.0** | 15.2 KB | 80 KB | ~16,900 |
| `OPUS_32` | 5 · 5 · 5 · 4 | **4.75** | 3.4 KB | 17.6 KB | ~3,700 |
| `MP3_64` | 5 · 5 · 5 · 4 | **4.75** | 7.6 KB | 40.2 KB | ~8,500 |
| `MP3_32` | 5 · 2 · 2 · 1 | **2.5** | 3.9 KB | 20.2 KB | ~4,300 |

**Every file the listener flagged was `MP3_32`, and no other candidate was ever flagged.** In the
listener's own words: *"clearly much worse! less airy, very compressed"* (`la sobremesa`),
*"obviously compressed, much smaller range"* (both sentences). The two hesitant fours were
`MP3_64` — *"slightly compressed Spanish S, but not sure"* — and `OPUS_32` — *"might be very
slightly compressed, but not sure"*. Nothing else was distinguishable from the uncompressed master.

Three things this establishes:

1. **The metallic sound is the bitrate, not the model.** The same performance at 128 kbps and
   uncompressed scored five every time; at 32 kbps it was audible immediately. No prompt, voice or
   model change would have fixed it.
2. **The damage shows on sustained fricatives and on sentence-length material.** `MP3_32` scored a
   clean five on `picar` — one short word with no long /s/ — and 1–2 on everything else. The
   listener's remarks name the Spanish *s* three times unprompted, which is exactly where a 32 kbps
   MP3's low-pass and pre-echo live. It is also why the fault was *audible in the app before this
   test*: the sentences are read by the Gemini voices, which is precisely where the API returns 32.
3. **Opus at ~30 kbps is the whole win.** It scored with `MP3_64` and within one hesitant point of
   uncompressed, while being **smaller than the 32 kbps MP3 that was obviously bad** — 3.4 KB for a
   word against 3.9 KB, 17.6 KB for a sentence against 20.2 KB. The API's own `OGG_OPUS` lands in
   the same band it was tested at (28–35 kbps).

### What each would cost to store

Per clip, scaled to the corpus twice: as it stands today (~1,500 words, ~3 examples each) and at the
ceiling `docs/plans/pronunciation-research.md` uses (10,000 headwords, 30,000 sentences). Clips are
**replicated**, so each number is paid on the server *and* on every device that keeps them.

| candidate | today | at the ceiling | vs today's mix |
| --- | --- | --- | --- |
| `LINEAR16` | 1,157 MB | 7,716 MB | 11× |
| `MP3_128` | 393 MB | 2,623 MB | 3.7× |
| `MP3_64` | 197 MB | 1,312 MB | 1.9× |
| **today's mix** (words 64, sentences 32) | **105 MB** | **699 MB** | — |
| `OPUS_32` | **86 MB** | **574 MB** | **0.8×** |

### Why not simply store the best-sounding format

Because the best-sounding format is not better *to this listener's ear* than Opus, and it costs
between four and eleven times as much:

- `LINEAR16` and `MP3_128` both scored 5.0 — but so did `OPUS_32` on three of four pieces, and the
  fourth was a "not sure". There is no quality to buy back, only bytes to spend.
- Audio is replicated **because it is cheap**. The whole argument for putting clips in the graph,
  unlike pictures, was that they cost roughly what the text costs (`§04`, 20–50 MB). At `LINEAR16`
  the clips would be 7.7 GB — the same order as the ~9 GB of pictures that are deliberately *not*
  replicated, and on a phone. That does not qualify the rule; it repeals it.
- Every first play is also a download over whatever connection is to hand: 237 KB for a sentence
  against 17.6 KB.
- The ceiling is not decoration. At 30,000 sentences, `MP3_128` is 2.6 GB of IndexedDB per device.

So the choice that follows from the numbers is **`OGG_OPUS`: better than what is stored today, on
every piece where a difference was audible at all, and smaller than it.**

## Decision

**Ask Cloud TTS for `OGG_OPUS` instead of `MP3`**, for both the plain and the expressive voices. It
is the only candidate that is simultaneously better-sounding and smaller than what is stored now,
and the 32 kbps MP3 it replaces is the one thing in this test anybody could hear.

Recorded here; the change itself is a follow-up — one value per model in `models/catalogue.json`,
read by `src/acervo/models/google_tts.py`, with `audio_mime` already recognising an Ogg stream.

Two notes for whoever makes that change:

- The blind candidates were encoded locally with libopus at 32 kbps; the API's own `OGG_OPUS`
  answers at 28–35 kbps with the same encoder, so the listening result carries over. Worth one A/B
  of a real API clip against its master before it ships.
- The API's Opus reports a 48 kHz sample rate where its MP3 reports 24 kHz. That is Opus's internal
  rate, not upsampled content, and is nothing to fix.

### Not settled here

- **The accent.** Choosing `es-ES` against `es-US` voices is taste, not artifacts, and belongs in its
  own sheet — mixing it in would have tested two things at once.
- **`M4A` and 48 kHz** are closed rather than open: the first is MP3 under another name where it is
  accepted at all, and the second only resamples.
