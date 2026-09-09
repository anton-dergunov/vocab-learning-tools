# Plan 06: Audio through the catalogue

**Status:** Planned.
**Depends on:** [04](04-one-python-provider-package.md).

## Outcome

A word can be heard. Two different kinds of hearing, deliberately kept apart: **expressive** audio
that carries the intonation of a real sentence, worth paying a good model for, and **plain**
pronunciation of a headword, which any competent voice can do and should cost nothing. Each is a
chain of catalogue rows, and the graph has somewhere to record which voice said what.

## Current state

**Acervo has no audio at all.** The vocabulary graph is
`topic → lexeme → sense → example / attestation / imagePrompt / studyState` and there is no audio
record in it. `pb_migrations/1787868000_acervo_core.js` creates nine collections and none of them
holds a recording. Nothing in `web/src/` plays anything.

The only text-to-speech code in the repository is the superseded layer: `tts/base.py:4`'s
`TTSProvider.synthesize(text, output_path) -> None`, one backend in `tts/kokoro.py:6` wrapping
`KPipeline` with a voice and speed from config, and `tts/helpers.py` with a hardcoded
`SAMPLE_RATE = 24000` and `SILENCE_DURATION = 0.3` padding. It is reachable only from tests. Its
consumer was the old Anki deck generator, which read `audio_path` out of a manifest
(`anki_sync/manifest.py:24-25`) rather than generating anything.

`provider/factory.py:4-10` carries a five-year-old TODO listing Google Cloud TTS, ElevenLabs, OpenAI,
openai-edge-tts and AWS Polly as options never pursued.

The real prior art is outside this repository, in the sibling `earworms_generator` prototype — a
working multi-provider TTS system in its `lexibeat/voice.py` (1,253 lines), intended to fold into
this project later:

- a `Backend` protocol whose `synth()` takes text, language, prosody, emotion, an optional target
  duration and a seed, and returns a `SynthesisResult` carrying audio, generation time, the controls
  actually applied, warnings, peak memory and pass count
- a `CAPABILITIES` table declaring, per backend, *how* each control is supported — `native`,
  `instruction`, `post-process`, `clone`, `preset`, `unsupported` — plus its licence and its known
  limitations, e.g. that Cloudflare's melotts deployment rejects Spanish with `AiError 8002`
- a `GEMINI_FREE_TIER_INTERVALS` table pacing against a 3-requests-per-minute free tier, with
  `_daily_quota_exhausted()` sniffing `requestsperday` markers out of the error
- `_CloudflareBackend._request` normalizing **five** different response encodings — a raw `audio/*`
  body, JSON `result.audio`, JSON `result.data`, list-wrapped, and data-URI-prefixed base64
- a `Speaker` orchestrator that warns once on an experimental backend naming its licence, memoizes by
  request, injects a deterministic per-call seed, resamples to a common rate and peak-normalizes

## Decisions

### Two jobs, and they are not interchangeable

This is the decision the whole plan turns on. Conflating them would mean either paying a premium
model to say a single word thousands of times, or getting a flat robotic reading of a sentence whose
whole value is its intonation.

- **Expressive.** A sentence — an attestation or an example — read the way a speaker would say it,
  with the stress and contour that make it memorable. Gemini's TTS models are worth paying for here
  and were chosen for exactly this. It is generated once, for material worth hearing, and cached.
- **Plain.** A headword or a lemma, said clearly. Any competent voice will do. This is the one the
  application plays constantly, so it should be free and it is the natural place for a local model —
  Cloudflare Aura-2 on the server, or Kokoro on a Mac.

They get separate chains, because the owner's answer to "what should read a sentence" and "what
should read a word" are different answers.

### The record shape comes before the generation

There is no consumer, so building a provider surface first would be building for nobody. The order is:
decide what an audio record is and where it hangs off the graph, then generate into it, then play it.

An audio clip belongs to whatever it is a reading *of*: a lexeme, for the plain pronunciation of its
headword, or an example or attestation, for the expressive reading of a sentence. That is the same
relationship `image_prompts` has to a sense, and it should be modelled the same way rather than as a
free-floating media table.

### Where the bytes live is the question this plan must answer, and images already answered it

`study_states` and the rest of the graph are small records. Audio is not, and neither are the sense
images — and plan 05 does not solve this either, because the sense-image pipeline writes to the
filesystem in phase A precisely so it cannot disturb live ingestion
(`docs/acervo-sense-images.md:383-420`).

So this plan does not invent a media store. It adopts whatever plan 05's images settle on, and if
that is still "the filesystem, and the graph holds a reference", audio does the same. Do not let audio
be the reason a media store gets designed in a hurry.

### Generation runs in `acervo-worker`, as a subcommand

Audio is batched, not synchronous: nobody waits for a clip while capturing a word. So it runs the way
`anki …` and `dictionary …` already do — `docker compose --profile tools run --rm acervo-worker
audio …` — as a new subcommand of `scripts/acervo_worker.py`. **Never a new compose service.**
`acervo-worker` is a one-shot container by design and that is not negotiated here.

Note that `deploy/acervo/Dockerfile:11-16` installs none of the model libraries today, so this is the
plan that first makes the server image need `litellm` — unless plan 05 got there first.

### Lift `earworms_generator`'s pacing and response handling; do not lift its class hierarchy

Its `GEMINI_FREE_TIER_INTERVALS` table and its five-way Cloudflare response normalization are hard-won
facts about how these providers actually behave. Those belong in the catalogue and in plan 04's
Cloudflare adapter.

Its `Backend` protocol and per-provider classes do not come across: plan 04 already decided that a
provider declares its controls rather than implementing them, and LiteLLM covers Gemini, Vertex,
OpenAI, Azure, Polly and ElevenLabs for audio already. The one gap is Cloudflare, which plan 04's
adapter fills.

### A local voice survives only if it is wanted

`tts/kokoro.py` is the only local voice in the repository and plan 04 deferred its fate to this plan.
Decide here: if plain pronunciation should work with no network at all, Kokoro becomes a `models/`
local backend and `tts/helpers.py`'s silence padding comes with it. If Cloudflare Aura-2 is enough,
delete both — an unused local backend with a `torch` dependency is a cost with no reader.

Recommendation: keep it, but only after checking that it runs on the NAS. The research in
`docs/image-generation-research.md` measured local *image* models needing 2.5–10 GiB; Kokoro is far
smaller, but "far smaller" is not a measurement. Measure it in step 1 and let the number decide.

## Implementation work

1. **Measure Kokoro on the server** before anything else, because it decides step 6. Resident memory,
   seconds per word, and whether it runs at all on a GPU-less NAS. One number, then move on.

2. **Design the audio record** and add it to the bootstrap migration. Owner-scoped, `deleted`,
   `createdAt`, `editedAt`, `editedBy`, `revision`, like every other domain record. It names what it
   is a reading of and which of the two kinds it is. Same schema-bump cost as plan 03 —
   `./deploy.sh --reset-database`, export first — so **do this in the same reset as plan 03 if
   both are pending.**

3. **Add audio rows** to `models/catalogue.json`: `gemini-free` and `vertex` gain TTS models for the
   expressive chain; `cloudflare` gains Aura-2 for the plain chain; `openai` and `elevenlabs` are
   listed as rows for anyone who wants them. Each row's `capabilities.audio` declares how it supports
   style or emotion — `native`, `instruction`, or `unsupported` — and carries its voice list and its
   free-tier pacing, from `earworms_generator`'s tables.

4. **Two chains, not one.** Plan 03's route and collection gain `audioExpressive` and `audioPlain`
   rather than a single `audio` key. Settings ▸ Models shows them as two rows of the same page, with a
   sentence each saying what they are for, because the distinction is the whole point and an unlabelled
   pair of chains would be guessed wrong.

5. **`audio` subcommand** in `scripts/acervo_worker.py`, calling `models.speech()` from plan 04, with
   a sweep shaped like `images/run.py`'s: plan what is missing, generate, write, and be idempotent on
   re-run. Reuse `images/run.py`'s `Store` pattern rather than inventing a second one.

6. **Resolve Kokoro's fate** per step 1. Either it becomes `models/local_speech.py` with
   `tts/helpers.py`'s padding, or `tts/` is deleted entirely as plan 04 anticipated.

7. **Play it.** One control on the article, in `web/src/LexemeArticle.tsx`: the headword plays its
   plain pronunciation, an example plays its expressive reading if it has one. Reads come from the
   replica and must work offline, like every other read — which is another reason the bytes question
   in step 2 matters.

## Public interfaces and data

Catalogue rows gain an audio section:

```jsonc
{
  "id": "gemini-free",
  "kinds": ["text", "image", "audio"],
  "defaultModel": { "audio": "gemini-3.1-flash-tts" },
  "litellm": { "audio": "gemini/gemini-3.1-flash-tts" },
  "capabilities": {
    "audio": {
      "style": "instruction",       // the style is written into the prompt, not a parameter
      "voices": ["Kore", "Puck", "Charon"],
      "languages": "many"
    }
  },
  "pacing": { "audio": { "min_seconds_between_requests": 20.5,
                         "note": "3 requests a minute on the free tier" } }
},
{
  "id": "cloudflare",
  "defaultModel": { "audio": "@cf/deepgram/aura-2" },
  "capabilities": {
    "audio": {
      "style": "unsupported",
      "transport": "multipart",
      "warnings": ["melotts rejects Spanish with AiError 8002"]
    }
  }
}
```

The `pacing` and `warnings` values are the facts `earworms_generator` learned the hard way. Writing
them into the catalogue is what stops them being learned twice.

The audio record — shape to be settled in step 2, sketched so the plan is executable:

```jsonc
{
  "id": "…15 lowercase alphanumerics…",
  "ownerId": "…",
  "kind": "plain",                 // "plain" | "expressive"
  "lexemeId": "…",                 // what it reads: a lexeme for plain,
  "exampleId": null,               //   or an example / attestation for expressive
  "attestationId": null,
  "modelId": "@cf/deepgram/aura-2",   // the row that ANSWERED, per the locked contract
  "voice": "angus",
  "seconds": 0.84,
  "media": "…reference, in whatever form plan 05 settled on…",
  "revision": 41
}
```

Chains, extending plan 03's route:

```jsonc
{ "chains": {
    "text": ["gemini-free", "cloudflare"],
    "image": ["cloudflare", "vertex"],
    "audioExpressive": ["gemini-free", "vertex"],
    "audioPlain": ["cloudflare", "local-kokoro"]
} }
```

## Acceptance tests and verification

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/unit/server
npm --prefix web run test
```

Unit cases:

- an expressive request reaches a row whose `style` is `instruction` with the style in the prompt,
  and a row whose `style` is `unsupported` without it and with a warning on the result
- a `multipart` audio row goes through the hand-written adapter, and each of the five Cloudflare
  response encodings is decoded — lift `earworms_generator`'s cases, they are already written
- the free-tier pacing is honoured: two consecutive Gemini requests are at least the row's interval
  apart
- an expressive chain rate limited on its first row answers from the second, and `modelId` names the
  second
- the sweep is idempotent: a second run generates nothing and says why
- an audio record whose owner differs from its lexeme's owner is refused by `validateRecord`

Live:

```bash
# the distinction this plan exists for — listen to both and confirm they are different jobs
docker compose -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker \
  audio generate --kind expressive --limit 3
docker compose -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker \
  audio generate --kind plain --limit 20

#  · the expressive clips carry the sentence's intonation
#  · the plain clips are clear, and cost nothing
#  · each record names the voice and the model that produced it
#  · the plain sweep of 20 words costs $0 and does not touch the Gemini quota

# in the app
#  · tap the headword: the plain pronunciation plays
#  · tap an example: its expressive reading plays, or nothing offers to play if it has none
#  · stop PocketBase: playback of stored audio still works, because reads are offline-first
```

## Non-goals

- **No speech-to-text, and no Whisper.** Explicitly out of scope for this whole roadmap. It is a
  different direction of travel with its own record shape and no consumer.
- **No pronunciation assessment.** Recording the owner's voice and scoring it is a product feature,
  not a provider one.
- **No new media store.** Audio adopts whatever plan 05's images use. If that turns out to be
  inadequate, that is a plan of its own, not a decision made in a hurry here.
- **No compose service.** `acervo-worker` is one-shot; a new job is a new subcommand.
- **No `earworms_generator` class hierarchy.** Its tables and its Cloudflare response handling come
  across; its `Backend` protocol does not, because plan 04 already chose declaration over
  implementation.
- **No music, beds or timing.** `earworms_generator` does those; folding that project in is its own
  piece of work and this plan only borrows its provider knowledge.
