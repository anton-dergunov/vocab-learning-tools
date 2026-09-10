# Pronunciation and audio

**Status:** Planned. Nothing blocks it.

Rewritten from the provider roadmap's audio plan after that roadmap closed and its documents
were deleted. The catalogue half is
built — audio rows, `models.speech()`, the Cloudflare adapter, and a Settings ▸ Providers section
that already stores an order — so what is left here is the record, the job, and playback.

## Outcome

A word can be heard. Two different kinds of hearing, deliberately kept apart, each with its own
chain of catalogue rows, and a place in the graph to record which voice said what.

## The decision this turns on

**Expressive and plain are two jobs, not one.** Conflating them means either paying a premium model
to say a single word thousands of times, or getting a flat robotic reading of a sentence whose whole
value is its intonation.

- **Expressive.** A sentence — an attestation or an example — read the way a speaker would say it,
  with the stress and contour that make it memorable. Gemini's TTS models are worth paying for here.
  Generated once, for material worth hearing, and cached.
- **Plain.** A headword or a lemma, said clearly. Any competent voice will do. This is the one the
  application plays constantly, so it should be free.

They get **separate chains**, because the owner's answer to "what should read a sentence" and "what
should read a word" are different answers. Settings ▸ Providers shows them as two sections with a
sentence each saying what they are for; an unlabelled pair of chains would be guessed wrong.

## What is already built

Do not rebuild any of this.

- **`models.speech()`** (`src/acervo/models/call.py`) — one speech call against one row, returning
  an `Answer` naming the row that answered.
- **The style rule.** A style is carried only to a row whose `capabilities.audio.style` is
  `instruction`; anywhere else it is dropped and the answer carries a warning, rather than being
  read aloud as an instruction.
- **The Cloudflare audio adapter** (`src/acervo/models/cloudflare.py`) — the one thing LiteLLM does
  not cover.
- **Content-sniffed MIME** (`call.audio_mime`), because Gemini answers WAV and Aura answers MP3, and
  a clip labelled by what was hoped for rather than by what arrived does not play.
- **Audio rows** on `gemini-free`, `vertex`, `cloudflare` and `openai`, with the facts learned the
  hard way written into their `notes`: the free tier's ten speech requests a day; why
  `gemini-2.5-flash-preview-tts` is deliberately excluded (it answers a short word with generated
  *text* often enough to matter, Gemini refuses that with a 400, and LiteLLM surfaces it as an
  `IndexError`, which the chain would read as terminal); melotts refusing Spanish with
  `AiError 8002`, which is why Cloudflare's row names Deepgram Aura instead; and that Aura takes
  `text` where melotts took `prompt`.
- **A single `audio` kind** in Settings, which stores an order nothing reads yet.
- **Live coverage**: `tests/integration/test_models_live.py` already makes one real speech call per
  credentialed row, behind `RUN_LIVE_MODEL_TESTS`.

## What is settled that the earlier plan left open

**Where the bytes live.** The earlier plan deferred this to the image work, and the image work
answered it:
`ACERVO_MEDIA_PATH`, served from `GET /api/acervo/media/{path}` behind bearer auth and Range-capable,
read-write in the worker and read-only in the server. Audio uses it and the record holds a relative
path, exactly as `imageRef` does. **Do not design a second media store.**

**Kokoro's fate.** `src/acervo/tts/` was deleted with the PocketBase server, so the "measure it,
then decide" branch resolved itself by the code going away. A local plain voice is now a *rebuild*,
not a resurrection, and needs its own argument — starting with whether it runs at all on a GPU-less
NAS. Cloudflare Aura at zero cost is the incumbent it has to beat.

## What is actually left

1. **The audio record.** A lexeme has no audio field at all; `examples.audio_ref` exists but is an
   ingestion string for a reference someone pasted, not a generated clip. Decide whether audio hangs
   off the record it reads — a lexeme for plain, an example or attestation for expressive, the way
   `image_prompts` hangs off a sense — or becomes its own owner-scoped table. Either way it carries
   `ownerId`, `deleted`, `createdAt`, `editedAt`, `editedBy`, `revision`, names the model that
   **answered** and the voice it used, and **this is the piece that costs a `--reset-database`.**

2. **Two chains, not one.** `services/models.py`'s `KINDS` gains `audioExpressive` and `audioPlain`
   in place of `audio`, plus the UI copy. The chain is a JSON document keyed by kind
   (`model_selection.chains`), so this needs no migration of its own.

3. **An `audio` subcommand** in `scripts/acervo_worker.py`, shaped like `jobs/images/run.py`'s
   sweep: plan what is missing, generate, write, and be idempotent on re-run. Reuse the `Store`
   pattern rather than inventing a second one. **Never a new compose service** —
   `acervo-worker` is one-shot by design and a new job is a new subcommand.

4. **LiteLLM in the worker image.** `deploy/acervo/Dockerfile` installs none today, with a comment
   saying no worker job calls a model yet. This is the job that changes that.

5. **Playback.** `web/src/LexemeArticle.tsx` already has the buttons, wired to
   "Audio is not wired up yet". Reads come from the replica and must work offline like every other
   read — which is another reason step 1 matters.

6. **Row facts worth adding while you are there**: a `pacing` block is *not* wanted (a rate limit is
   a fact about an account, not a provider), but voice lists per language and structured warnings
   would earn their place — they currently live only in prose `notes`.

## The credentials are meant to be reusable

The same provider keys will be used by other projects that generate audio. Nothing in the record
shape, the media store or the catalogue may assume Acervo is the only reader of a clip or the only
caller behind a key.

## Non-goals

- **No speech-to-text, and no Whisper.** A different direction of travel, with its own record shape
  and no consumer.
- **No pronunciation assessment.** Recording the owner's voice and scoring it is a product feature,
  not a provider one.
- **No new media store.** Audio adopts the images'.
- **No compose service.** A new job is a new subcommand.
- **No music, beds or timing.** A sibling prototype does those; folding that in is its own piece of
  work, and this one only borrows its provider knowledge.
