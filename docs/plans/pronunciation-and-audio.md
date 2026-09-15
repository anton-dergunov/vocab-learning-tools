# Pronunciation and audio

**Status:** Built, for everything a person presses. What is left is the unattended half.

A word can be heard: the headword, a sense's definition, an example, an attestation and any stretch
of text you select. The research that settled the shape is
[`pronunciation-research.md`](pronunciation-research.md), and two of its findings decided the design —
cost is not a constraint at this volume, and a clip is small enough to replicate, which an image is
not.

## What a clip is

**A record, not a call.** `pronunciations` is the ninth replicated collection: it names the file in
`ACERVO_MEDIA_PATH`, the words that were spoken, the language, the emotion the voice was actually
given, and the provider, model and voice that spoke it.

Its id is derived — `pronunciation_id(targetKind, targetId)`, implemented in
`src/acervo/pronunciation/ids.py` and `web/src/ids.ts` and pinned against shared vectors — so a
spoken field holds at most one clip and recording it again rewrites that row. The file name carries
a digest of the bytes, so a new recording has a new reference and a device holding the old one misses
rather than serving what was just replaced.

**Stale is a comparison, not a flag.** A clip is current while its `text` equals what the record now
says. Edit the sentence and the next press records the new words; nothing marks anything.

## The two orders

`audioPlain` reads a headword, a definition and a selection. `audioExpressive` reads an example, with
its `emotion` as a delivery direction where the answering model declares `style: instruction`, and
plainly where it does not. Both draw their pairs from the catalogue's one `audio` kind: any voice can
read either, and which one *should* is the owner's answer rather than a fact about the voice.

The catalogue's `defaultChains` recommends Cloud TTS WaveNet for words and a Gemini voice for
sentences; Settings ▸ Providers changes either. A pair whose model does not speak the language is
left out of the walk for that language, and a chain where none does answers
`no_voice_for_language`, which names what to fix.

## Providers

`google-tts` is the Cloud Text-to-Speech API, with its own adapter (`models/google_tts.py`) because
LiteLLM does not cover it — one route, `text:synthesize`, serving two families of voice that the row
describes separately:

- **Standard and WaveNet** — per language, named `es-ES-Wavenet-F`, no direction, and a permanent free
  allowance far above what a vocabulary needs.
- **Gemini voices** — named once, speaking any language, selected by `voice.modelName`, taking the
  emotion in `input.prompt`, which is a field of its own and so never read aloud.

Audio capabilities are therefore declared **per model** (`capabilities.audio.models`): style,
languages, locales and voices. The other audio rows — Gemini, Vertex, Cloudflare Aura, OpenAI — are
kept and declare the same things, so choosing one is a settings change rather than a code change.

Credentials are the `vertex` row's: application default credentials plus `ACERVO_VERTEX_PROJECT`,
which also travels as the quota-project header Cloud TTS requires of a user login. Enabling the API is
in [`../acervo-vertex-setup.md`](../acervo-vertex-setup.md).

## On the device

Reads stay offline-first. A clip the replica names and the device holds plays with no request; the
bytes live in `mediaStore.ts`'s own `pronunciations` store, so forgetting them never touches a
picture. `fill()` brings down what the replica names after each sync, which is what makes a word
recorded on another device — or in advance — play on a plane. Keeping is a per-device switch in
Settings ▸ Pronunciation, on by default.

Recording is a write: online, loud when it fails, never queued.

**A bad recording is replaced from the toast.** After a stored clip plays, the message offers Record
again — the moment you know a recording is bad is the moment you have just heard it, and a control
under every sentence would be a page of buttons.

## What is left

1. **A sweep.** `acervo-worker pronounce sweep`, shaped like `draw-pictures`: ask the graph which
   words have no clips and record them while nobody is watching. Everything it needs exists —
   `pronunciation.targets.wanted` is the query, and the ids are derived, so it and the interface
   need no coordination. This is the last piece of the "record it in advance" story; today that
   happens on the device that saves the word.
2. **Aura-2.** Cloudflare's Spanish voice is a second model id and a voice list in the row, no code.
3. **An Azure row**, whose styles are an SSML enum rather than free text — a third value for
   `capabilities.audio.style`, and the first real test of that declaration.
4. **Human recordings** (Lingua Libre, Forvo) as a source tier above TTS, per the research note.

## Non-goals

- **No speech-to-text, and no Whisper.**
- **No pronunciation assessment.** Recording the owner's voice and scoring it is a product feature.
- **No second media store**, and no second pipeline: a clip is written by the route that recorded it
  through `merge_graph`, exactly as a picture is.
- **No device voices and no local models.** `speechSynthesis` cannot be captured, so it can never fill
  a cache, and a voice for a language the device lacks reads the wrong thing in the wrong accent.
