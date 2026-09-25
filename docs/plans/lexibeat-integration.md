# LexiBeat · integrating the loop generator

**Status:** Steps 1–9 done, and 0.3.0 closed the two things step 7 left open — `speech.delivery` is
sent, so the plain order costs what it is supposed to; and the director note the generator composes
reaches the voice intact rather than being re-framed as an adjective by the example prompt.

Step 1 was this document and one word deleted from `models/redact.py`. Step 2 was the experiment
that gated the prompt change, run 18 September 2026.
Step 3 was the whole of the work in the other repository, which now ships a wheel, a versioned
`/api/v1` and an injected speech backend — it landed on **18 September 2026** and everything from §4
step 4 onward is in this repository. Step 4 landed the same day: the two lexeme fields, the two
collections, and the compose prompt the experiment measured. Schema version 11; the database is
rebuilt rather than migrated, as every schema change here is. Step 5 followed: the orders renamed for
their capability, `expressive` replaced by a per-use Delivery choice, and `POST /pronunciations/take`
over a content-addressed store of FLAC masters. Step 6 put the generator on the deployment and gave
it a voice, and a rehearsal against a real Acervo rendered a loop over real samples with a Gemini
voice that took its direction — the quality this was for.

A word's article can already say what a word means, show a picture of it, play a native speaker using
it, and read every field aloud. What none of that does is get a word *stuck in your head*.
[`lexibeat`](https://github.com/anton-dergunov/lexibeat) exists to do that: the word and one
translation, each spoken three times on a bar grid over a procedurally synthesised bed, with a
silence in the middle to recall the answer in. This document is how the two projects meet.

It is the **second** companion repository, after [`spoken-usage-retrieval`](../spoken-clips.md), and a
third is expected. So the shape matters more than the feature: this is the template's second use, and
where it departs from the first it says why.

## Outcome

You select nothing and press one button: twelve words from whatever you are looking at become a
four-minute track you can put on in the kitchen. It is listed in its own surface, plays with the
screen locked, shows each word as it arrives, and can be reordered or deleted. Making one is a server
job you can walk away from.

The other repository keeps everything that makes a loop sound like anything — the pattern, the number
of takes, how each take differs, the bed, the ducking. Acervo lends it words, one emotion per word,
and a voice.

---

## §1 · What the other repository already gives

Read its `README.md`, `docs/design.md` and `docs/music-generation.md` before starting.

- **A procedural music engine, not a model.** `lexibeat/music.py` synthesises four stems — `pad`,
  `bass`, `drums`, `lead` — with numpy and `scipy.signal` from CC0 samples, against a known beat
  grid. No GPU, no network, no model call, and byte-identical from a seed; its own tests assert the
  no-network property. **This is why a loop can be built on the NAS at all.**
- **A deterministic bed description.** `bedspec.py` holds `ENGINE_VERSION` and the 16 families that
  become `STYLES`; `profiles.py` gates which a request may use (14 under `production-v1`);
  `generator.py:resolve_request` builds candidates, scores them with `quality.py`, and writes every
  choice — down to each `SampleRef(collection, asset_id, sha256)` — into the spec. A family plus a
  seed replays exactly.
- **An arrangement engine.** `arrange.py` is the whole of it: `PATTERNS` maps a name to one-bar
  slots, where a slot is a language, a `"gap"` to recall in, or a `"rest"`. `retrieval` is the preset
  — word, gap, answer, then two more pairs, then a rest — and every utterance starts on a downbeat,
  budgeted to `grid.bar * 0.92` and stretched to fit with the ratio capped at 1.35. Measured onset
  error against the downbeat is a median of 15 ms.
- **Three takes per line, each delivered differently.** `Prosody.TABLE` carries four rows of
  speed / semitones / gain / exaggeration and `for_repeat(index)` cycles them, so the repetition does
  not sound mechanical. **How** a take differs depends on what the voice can do, and §2.6 is about
  that, because it is the one thing in this integration that is easy to get subtly wrong.
- **A mix that ducks.** `mix.py` sidechains each stem from the speech envelope (attack 100 ms,
  release 400 ms) at a depth the spec carries, then limits at 0.97; speech −16 LUFS, music −26.
- **Two timing exposures.** `lesson.py:_subtitles` holds each caption until the next utterance so the
  answer is never revealed early, and `demo.py:build_timeline` gives the richer per-item structure —
  `start`, `source_reveal`, `target_reveal`, `end`, and every utterance's span — and validates that
  the arranged events match the words it was given. **That second one is the interface's cue data**,
  and it currently lives in a demo script rather than in the library.
- **A 1.8 GB sample bundle**, Git-LFS tracked: a `catalog.sqlite3`, 1,112 content-addressed assets,
  95 named-pack files, and a `manifest.json` carrying a SHA-256 per asset. Without it the engine
  still works and offers only the sample-free `electronic` palette, reporting
  `production_bundle: false`.
- **One injection seam that matters.** `Speaker(backend_instance=…)` takes any object satisfying the
  `Backend` Protocol structurally, and `cuda_voice.py:CudaChatterboxBackend` is a working precedent
  that is registered nowhere. `render_lesson_speech(…, backend=…)` passes one **per render**, and
  `create_api(lesson_generate=…)` lets a host replace the whole speech phase. Those three are the
  whole of what this integration needs.

And the facts that ruled things out — all three of which **step 3 has now changed**, and they are
kept because they are why the seams are where they are:

- **Its HTTP surface and its Gradio explorer were built to demonstrate the engine**, not to be
  integrated against: the lesson flow was reachable in-process or through Gradio and nowhere else,
  and its input was a two-column table capped at six rows with no emotion column. It was **open to
  redesign**, and step 3 redesigned it into `/api/v1`.
- **Its default voice is Chatterbox Multilingual**, local through MLX, at 5.5–6.1 seconds an
  utterance. The NAS has no MLX and no GPU. Local voices are a later experiment; nothing here waits
  on them, and the CUDA backend and the stopped public Space were removed in step 3.
- **It was not installable.** It now has `[build-system]`, four console scripts, a wheel, a lock
  file, a release workflow that writes `SHA256SUMS` on a tag, and a CI job that runs the tests on a
  pull request rather than on the way to a deployment.

---

## §2 · The decisions

### 1 · Two repositories, one version pin

Unchanged from `spoken-clips.md` §2.1: `deploy/acervo/lexibeat/pin.json` names one version, one tag
and a digest per artifact, and `scripts/fetch_lexibeat.sh` turns that into gitignored
`vendor/lexibeat/`. Digests come from the release's own `SHA256SUMS`. A locally built wheel that
matches is left alone, which is what makes "try it before tagging" work; anything the pin does not
name is pruned, because the image installs `vendor/lexibeat/*.whl` and two wheels of one package fail
the build.

There is no npm half. LexiBeat ships no player component; the loop player is Acervo's.

### 2 · A service beside Acervo, holding no provider key

A compose service with no published port, reached at `http://lexibeat:8000/api/v1`, in an image that
is **Acervo's** — the package does not self-daemonize, so process, volumes and URL are the host's.

Unlike the retrieval image it carries no `acervo.models` and **no provider credential at all**,
because of §2.3. It is therefore the one companion service absent from `test_deployment.py`'s "every
service that calls a model is given the same credentials" tuple, and a test asserts that absence
deliberately so a later reader cannot mistake it for an oversight.

Its healthcheck asserts **liveness**, and not that the sample bundle is present: a fresh deployment
has no bundle and still serves. Readiness gating would fail the install of a working service, which
is the lesson `spoken-clips.md` §2.2 paid for.

**It serves without the bundle; it cannot render without it** — and this paragraph said otherwise
until step 9. The claim was that a pack-less render falls back to the synthesised `electronic`
palette, so the interface should warn rather than refuse. It does not: fifteen of the sixteen bed
families name instruments loaded from the catalogue, so the render dies partway through on a missing
sample and how far it gets depends on which voices the seed happens to draw. `POST /loops` therefore
refuses with `loops_no_samples` before writing a row. The healthcheck is unchanged and still
deliberately does not gate on it — *installing* a server without its samples is fine, and the
refusal belongs on the one route that needs them.

### 3 · LexiBeat synthesises; Acervo lends it a voice

**The service receives words, not audio.** `{items: [{source, target, emotion}], pattern, family,
seed}`. It decides how many takes, how each differs, where the downbeats fall, how the bed resolves
and how the mix ducks.

An earlier draft had Acervo record the lines and post the audio. It was wrong three ways, and the
reasons are worth keeping:

- **It split the pattern across two repositories.** Changing three repetitions to four would have
  meant changing both, which is the opposite of letting that project be iterated on alone.
- **It contradicted that project's own interface**, which takes a word and decides delivery itself. A
  second, audio-shaped entry point would have been a second way in, permanently.
- **It missed that the three takes are three recordings.** Acervo holds at most one clip per spoken
  field by construction, so "the word's audio" is exactly the thing it cannot supply.

**So the seam is a provider, injected.** And this is where it differs from the translation seam, which
is handed `acervo.models` in-process: everything a speech call needs here is database state a
companion container cannot read. `services/pronunciations.py:_speak()` already resolves the owner's
chain through `chain_for`, the owner's per-model voice through `preferences.voice`, the hedge, and the
`no_voice_for_language` refusal that names what to fix. Copying the provider package across would
mean passing the chain *and* the voice map in the request and reimplementing the voice lookup and
that refusal on the far side — duplication, and a third copy of every credential on the NAS.

So the injected `Backend` is implemented in `deploy/acervo/lexibeat/serve.py` as a call **home**, to
the route in §2.4. One rate limiter, one cooldown, one call log, one place the owner chooses. LexiBeat
sees only a Protocol, so if the balance ever changes, moving to in-process LiteLLM edits `serve.py`
and nothing else.

**The protocol step 3 landed**, and what `serve.py` must satisfy:

```python
class Backend(Protocol):
    name: str
    sample_rate: int
    capabilities: BackendCapabilities   # emotion, rate, voice, languages
    load_seconds: float
    model_id: str

    def synth(self, request: SpeechRequest) -> SynthesisResult: ...
```

`SpeechRequest` carries `text`, a `Language(code, name)`, a `Delivery(take, direction, prosody)`,
`target_seconds` and `seed`. Three things about it are load-bearing here.

**Dispatch reads `capabilities`, never a name.** That is what step 3 was mostly about: `Speaker` used
to look its post-processing flags up by the backend's name string, so an injected backend raised
`KeyError` before it spoke a word. Acervo's backend declares
`BackendCapabilities("instruction", "instruction", "preset", languages=())`, and the empty tuple
means "any language" — the owner's chain decides what it can speak, not a table in the other
repository.

**`take` is on the request**, which is what makes §2.5's cache key implementable at all: the index
would otherwise have to be re-derived from the prosody, and two takes can carry identical prosody at
low strength.

**`backend_factory` is the seam**, not a module-level object: `create_service(backend_factory=…)`
takes a callable given a `RenderContext(operation_id, request, credentials)` and returns a `Backend`.
`credentials` is the render-scoped token of §2.3, handed to that callable and to nothing else — it
appears in no operation body, no result and no log line, and `lexibeat.voice.register_secret` adds it
to that package's own provider-text redactor.

**No credential sits in that container.** `POST /loops` carries a short-lived token signed with
`ACERVO_JWT_SECRET`, scoped to one render and audienced to the take route; `serve.py` builds the
backend for that request around it, which works because `render_lesson_speech` takes its backend per
render. Nothing is stored, nothing outlives the render, and there is no login flow — narrower than
`acervo-worker`'s owner password, which is a one-shot container rather than a service.

There is no startup dependency in either direction: render requests arrive *from* the server, so the
server is up whenever a call comes home.

### 4 · `POST /pronunciations/take`, and why it is not `utterance()`

`{text, language, direction | null, take}` → the **uncompressed master**, plus
`X-Acervo-Provider`, `X-Acervo-Model`, `X-Acervo-Voice` and `X-Acervo-Direction: sent | dropped`.

- **Not `utterance()`**, which exists for a selection and compresses to Opus because the bytes are
  downloaded before they can be heard. A take is about to be time-stretched, pitch-shifted and mixed;
  it wants the master, so that the only lossy generation in a loop is the final MP3.
- **Not a plain-or-directed choice made by the caller.** The route reads the owner's *loop* delivery
  setting (§2.7) and reports whether the direction was honoured. **A dropped direction is a useful
  answer, not a failure**: LexiBeat falls back to its own pitch and speed variation, so a deployment
  with no instruction-following voice still gets loops — with three distinguishable takes and no
  emotion — and that requirement is met by the contract rather than by a branch on either side.
- **Not uncached.** §2.5.

**The field is called `direction` on the wire**, not `emotion`. `emotion` is the *record's* field
name — what §2.8 writes onto a lexeme, and what an example already carries — and it stays that.
LexiBeat has no notion of an emotion: it receives a short English phrase saying how a line should be
said, appends the take's prosody words to it, and puts the result in the director note. Naming it
for what it is on the far side keeps the two vocabularies from being confused for one, and the
mapping is one line in `src/acervo/loops/`.

### 5 · The take cache, and why `take` is in the key

Behind the route sits a content-addressed store of **FLAC masters**, keyed by a digest of
`(text, language, direction, take, provider, model, voice)`. The digest *is* the filename, so there is
no table and no schema. FLAC because it is lossless and about half of WAV: this is the one place in
Acervo where FLAC is the right answer, and the delivery format is not it.

It pays for itself twice. A word that appears in two loops is recorded once. And a render that dies
half way — a rate limit, a restart, a deploy — resumes against the takes that already exist, which is
what makes §2.10's retry cheap rather than a second bill.

**`take` is in the key deliberately, and this is the subtle part.** `delivery_instruction` quantises a
continuous `Prosody` into a 3×3 grid of adjectives, so two takes of the same word can produce
*byte-identical* instructions — they do for an `emphatic` word today. Without the take index the cache
would hand back one recording for both, and the repetition would sound **more** mechanical, not less.
Today nothing has noticed because there is no persistent cache and the provider is nondeterministic:
Gemini does not honour seeds, so two identical prompts happen to give two different readings. A cache
turns that accident into a guarantee in the wrong direction.

**A stored pronunciation is deliberately not read through.** It is tempting: a plain headword take has
the same text, language, model and voice as the clip the article already holds. But that clip is Opus
at about 51 kbps, compressed for a phone, and stretching and mixing it would put a second lossy
generation in front of the master. It would save one call per word in the plain case and none in the
directed case. `experiments/pronunciation-encoding/` exists to have settled exactly this trade, and
this is it being settled.

### 6 · Three takes, and what actually makes them differ

This deserves its own section because the mechanism is not uniform, and the integration sits on top
of the part that is weakest.

| The voice | How the three takes differ |
|---|---|
| Instruction-following (Gemini, Vertex, OpenAI) | **Only through words.** `delivery_instruction` turns speed and pitch into adjectives inside the prompt; `exaggeration_bias` and `gain_db` are discarded. |
| Post-processing (Cloudflare, Kokoro's pitch) | **Locally**, by time-stretch and pitch-shift on the returned audio. |
| Chatterbox | **Model-side**, by `exaggeration` alone; it has no speed or pitch control. |

Acervo's loops land in the first row, and three things follow.

**One:** a directed take is a separate model call per repetition — three per line, so roughly 72 for a
twelve-word loop. A plain take is one call per line, varied locally: roughly 24. That is what the
setting in §2.7 actually buys, and the document says so rather than leaving it to be discovered.

**Two:** the quantisation had dead zones, and `emphatic` fell in one — at full strength, takes 0 and
2 of an emphatic word resolved to speed 1.030/+0.30 st and 1.051/+0.70 st and *both* said "slightly
briskly, with a slightly brighter, higher pitch". **Step 3 widened each axis from three bands to
five**, and a test asserts the three takes of a line are pairwise distinct. Note that the emotion
table that pushed both takes past one threshold is itself gone: a direction is free text now, so the
multiplier that caused the collision no longer exists either. §2.5's key remains the belt, because at
a *low* prosody strength the takes converge by design — that is what "vary less" means.

**Three:** `gain_db` had never done anything, in any backend: it was applied and then divided
straight back out by the peak-normalise eleven lines later, so the −0.8/+0.6 dB column of
`Prosody.TABLE` was decoration. **Step 3 reordered it** — normalise to the reference peak, then apply
the gain, then hold the result under the ceiling — and a test asserts two takes differing only in
`gain_db` have measurably different peaks.

### 7 · Two orders named for what they are; three uses pick one

Today the two speech chains are labelled by use — *words and definitions*, *example sentences* — and an
example is **always** read by the expressive order. The `Speak examples with their emotion` switch only
decides whether a direction is *sent*, so turning it off still spends the expensive voice on every
sentence. With loops there would be three uses and two orders, and a third chain would make it worse.

So the orders keep their ids and are renamed for their capability — *a clear, even voice* and *a voice
that takes a direction* — and Settings ▸ Pronunciation ▸ Delivery gives each of the three uses a choice
between them. **Choosing the directed order is asking for emotion**, which is why
`pronunciation_settings.expressive` is deleted rather than left beside the new control: one mechanism
where there were two, and the cheap voice finally reachable for examples as well as loops.

No third chain. Any voice is a legitimate answer to either question, which is exactly why the catalogue
has one `audio` kind and `defaultChains` has two orders over it.

### 8 · `primaryGloss` and `emotion`, written by the compose prompt

`shortGloss` is right for the list and wrong for a loop: *casa* → `house, home` cannot be spoken on a
beat. What a loop needs is one term, the most common reading, roughly as long as the source — and a
direction for how the word is said.

```yaml
headword: asco
shortGloss: disgust, revulsion       # unchanged, the list line
primaryGloss: disgust                # the one term spoken
emotion: repulsed, recoiling slightly
```

**Named for what they are, not for what consumes them.** A future flashcard, quiz or second kind of
lesson can use both without either name lying. And `emotion` is the same field an example carries, at
a different level: same meaning, same short-English-direction format, same rules in the prompt, read
by the same `acervo_pronounce_style.md` machinery.

**On the lexeme, not the sense**, because a loop drills a word and must choose exactly one meaning.
Asking per sense produces three answers where one is wanted, and moves the choice away from the writer
that has just read every sense.

**`primaryGloss` follows `glossLangs[0]`**, exactly as `shortGloss` and a sense `domain` do, and there
is deliberately no setting for it. A vocabulary's gloss languages are already ordered most preferred
first, so reordering them *is* the control. A setting over a single stored string could only end up
naming a language the stored text is not in.

**And this is measured before it is trusted.** The risk is not that the fields are wrong but that a
larger prompt thins the *rest* of the article — fewer senses, shorter notes, a `primaryGloss` that is
just `shortGloss` again. `experiments/compose-lesson-line/` runs the amended prompt against the model
set and a fixed word list and compares everything except the new fields against what the current
prompt produces. If it degrades, the answer is **not** to carve two fields into their own call — that
is too small a piece to justify a second prompt. It is to split `acervo_compose.md` into comparable
parts, considered whole, as its own task. The write-up records which way it went.

**Measured on 18 September 2026, and it does not degrade:**
[`../../experiments/compose-lesson-line/README.md`](../../experiments/compose-lesson-line/README.md).
315 calls over 20 words, four languages, three (provider, model) pairs and three repeats.
**All ten substance metrics move less than their own run-to-run variance** — senses +0.04 against a
noise floor of 0.13, note characters −15.7 against 58.4 — gloss completeness is 100% in both arms,
and the only unparseable reply in the run came from the *shorter* prompt. `primaryGloss` was a single
term in all 158 usable replies and never once copied a multi-meaning `shortGloss`.

The subjective half found nothing either, and said so precisely: shown two articles from the **same**
prompt, the reader named a winner **half the time**, and agreement with a Pro-model judge over all 155
pairs was κ = −0.097, at chance. That 50% false-positive floor is the strongest available statement
that there is nothing to see — and it also means pairwise "which is better" is the wrong instrument
for differences this small, which the next prompt experiment should not repeat.

So **the fields ship as worded and `acervo_compose.md` is not split.** Two bars were missed and
neither bears on it: note characters at 89.4% on a metric whose difference is a quarter of its noise,
and the gloss-language rule, failed only by `llama-3.3-70b` and only on a rule that predates these
fields. Article quality itself is untouched by this run and has its own register,
[`article-quality.md`](article-quality.md) — both arms wrote `/ˈaska/` for `el asco`, which is simply
wrong, and a comparison of two arms is blind to a defect they share.

### 9 · A loop is two collections, and its state is derived

`loops` — `language`, `styleId`, `seed`, `engineVersion`, `bedFingerprint`, `pattern`, `audioRef`,
`audioMime`, `durationSeconds`, `position`. `loopItems` — `loopId`, `lexemeId`, `position`,
`sourceText`, `targetText`, `emotion`, `startSeconds`, `sourceRevealSeconds`, `targetRevealSeconds`,
`endSeconds`.

- **No status column.** An empty `audioRef` is *not rendered yet*; the job says the rest. `ImagePrompt`
  already lives by this — four facts say all of it, and a fifth would be a thing to keep in step.
- **No BedSpec blob.** Style, seed and engine version replay the bed byte-identically, and
  `bedFingerprint` is what proves it did. Nothing else in the model stores opaque JSON.
- **The item text is denormalised on purpose.** A `loopItem` records what was *said*, so editing the
  word afterwards must not make the player caption a recording that no longer matches. Identical
  reasoning to `pronunciations.text`, and the reason both are safe.
- **Per-utterance spans are not stored**, only the four per-item times. So the day three repetitions
  become four, Acervo's schema does not move.
- **No title.** `selectors.ts` derives one from the source words that fit, as `effectiveShortGloss`
  derives a gloss.
- **`position` orders them**, sparse and renumbered on reorder, with no uniqueness constraint — that
  is the data rule, and ordering is respected rather than enforced.

`pronunciations` gains nothing: no new target kinds, no new derived ids. Reordering and deleting are
ordinary graph writes, so online-only and loud when they fail, like every other write.

Two new collections take `SCHEMA_VERSION` to 11 and rotate the Alembic head, so this deploys as
`./deploy.sh --reset-database` — the normal cost of a schema change here.

### 10 · A render is an operation, followed like `corpus.update`

Seventy-odd model calls plus a bed and a mix is minutes, not seconds. So `POST /loops` answers an
operation id, and the job polls it, marking the step `waiting` and raising `Requeue` exactly as
`work/corpus.py` does. That buys progress the owner can watch, cancellation between polls, and no
multi-minute blocking call inside the runner.

The CPU work happens in the companion container, which is what keeps
[`../server.md`](../server.md) "Jobs"'s *"anything heavy is out of scope for the runner"*
true rather than merely restated. The runner holds a lane and a poll timer.

A rate limit surfaces as one of the three transient codes and rests as usual; the take cache is why
the restart is cheap.

**The routes step 3 landed**, all written out because §2.12's allow-list rule applies to them as it
does to the corpus:

| Route | Answers |
|---|---|
| `GET /api/v1/health` | `{status, api_version, engine_version, production_bundle}` — liveness only |
| `GET /api/v1/schema` | patterns, profiles, families, energy, rhythm, palette, limits, audio |
| `POST /api/v1/loops` | `202` with an operation |
| `GET /api/v1/operations/{id}` | the operation, with `result` once it completes |
| `DELETE /api/v1/operations/{id}` | cancels between utterances |
| `GET /api/v1/loops/{id}/audio` | the finished track, `audio/mpeg` |

The operation is `{operation_id, status, successful, error, progress: {fraction, message},
created_at, updated_at, result}`, with `status` one of `queued | running | completed | failed |
cancelled`. That is **deliberately the corpus's vocabulary** — the one
`src/acervo/clips/corpus.py`'s `Operation` already models and `src/acervo/work/corpus.py` already
follows, down to `finished` being "not queued and not running". So step 7's client is a second
instance of a pattern rather than a second pattern, and `work/loop.py` is `work/corpus.py` with a
different noun.

The completed `result` carries `audio_url`, `audio_mime`, `bitrate_kbps`, `duration_seconds`,
`pattern`, `style_id`, `seed`, `engine_version`, `profile_version`, `bed_fingerprint`, `total_bars`,
`bpm` and `timeline` — which is exactly §2.9's two collections and nothing else. **The resolved
BedSpec is deliberately not in it**, on that service's side as well as this one, so there is nothing
for a host to be tempted into storing.

### 11 · MP3, written there and stored untouched

LexiBeat writes the finished track as **MP3 at 128 kbps** and Acervo stores those bytes exactly as
they arrive, into `ACERVO_MEDIA_PATH`, with the row through `merge_graph` — file first, row second, as
`services/pronunciations.py` does, because nobody else holds both.

No re-encoding on the NAS, and no change to `encode.py`, which already states the rule this follows:
*"a provider that already returned MP3 has its bytes stored exactly as they arrived; re-encoding a
lossy stream into another lossy codec adds a second generation of artifacts."* A loop arrives
compressed, so it is stored as it arrived.

MP3 rather than Opus because the content is speech over a generated bed where 128 kbps is inaudible
from the master, and because the phone decodes it in hardware, seeks in it trivially, and will cache
it as a plain file later. Verified rather than assumed: that project's `soundfile` 0.14.0 over
libsndfile 1.2.2 writes MP3 and Ogg Opus with no new dependency and no ffmpeg.

**And the bitrate is measured rather than declared.** libsndfile exposes quality as a 0–1
`compression_level`, not a bitrate, so "128 kbps" is a claim that has to be checked: in
`bitrate_mode="CONSTANT"` the level maps onto LAME's own bitrate ladder, and `0.65` is the rung that
is 128. Measured on a 124.5-second loop, 1,993,664 bytes — **128.1 kbps, constant**. A test in that
repository re-measures it on every run, so the pair cannot drift apart.

### 12 · Words come from what you are looking at

The interface samples N lexeme ids from the scope on screen — this language, this topic, or everything
— as a pure selector over the replica, and posts the list. The server never re-derives scope, and the
route takes ids rather than a query.

That is what makes the next step cheap: **choosing words by hand is the same route with a different
list**, so it is a separate, optional piece of work that changes nothing on the server. Difficulty,
newest-first and "words with no loop yet" are later options on the same dialog, one selector each.

**The style and pattern catalogues are LexiBeat's**, read from its `schema` route and never copied here
— the rule `spoken-clips.md` §2.10 settled for channels. The dialog offers *Surprise me* or a family
the service advertises, so a new family or a second pattern appears here with no change at all.
`GET /api/v1/schema` is that route: it reports `patterns` (each with its bars and utterances per item
and whether it has a recall gap), `families`, `energy`, `rhythm`, `palette`, the request `limits` and
the `audio` format, plus `production_bundle`. A pattern's shape is described there rather than
assumed here, which is what keeps three repetitions becoming four from being a change on this side.

### 13 · A bottom bar, and only over the list

Loops get their own surface, reached from a bar pinned to the bottom — and `.app` grows that third grid
row **only when no article, external entry or Add view is open.**

The article pane is 780 px of column already carrying the view segments, the delete control, the
progress strip and `AskDock`; a second dock there is prohibited. It cannot collide by accident either,
since `AskDock` renders only when an article is open and the bar only when one is not. The top bar is
left alone: it holds search, scope, Add, sync, settings and the language menu, which on a phone is
already everything that fits.

A loop keeps playing while you read a word — the audio element is not the surface — and the now-playing
row is on the bar when you come back. **There is no mini-player over an article**, and a finished render
announces itself as a toast with an action, which `App.tsx` already has.

### 14 · The track plays from memory

The media route is behind bearer auth, so its URL cannot go in an `<audio src>` — the same reason a
picture is fetched as a blob, and the reason `LexemeArticle.tsx` once displayed none at all.

The constraint is the better design. A whole track in memory means **nothing touches the network during
playback**, which is what a locked screen and a lift need. `mediaStore.ts` gains a third kind, `loops`,
so a device can keep or forget loops without touching a picture or a pronunciation; `loops.ts` sets
MediaSession metadata and action handlers — the first in this codebase — and drives the word display
from `loopItems`.

One rule: **`loops.ts` stops `pronunciation.ts` before it plays, and `pronunciation.ts` stops the
loop.** Two audio elements racing for one output is a bug with no good failure mode. The iOS gesture
priming in `pronunciation.ts` applies here too.

A signed media URL that would let the browser stream by range is **not** built: a new credential shape
for a file better held whole.

### 15 · The sample bundle is fetched on the server, and size is the whole reason

1.8 GB cannot ride a tarball streamed over ssh, and binary data does not enter this repository. A
compiled dictionary rides the release archive because it is small enough to; this is not.

So `pin.json` names the bundle and its digest, a one-shot `docker compose run --rm` of the same image
fetches and verifies it into its own volume against the bundle's own `manifest.json`, and
`LEXIBEAT_BUNDLE_ROOT` points the service at the mount. That variable is needed regardless: the package
resolves its default bundle relative to the repository root, which in a wheel install is
`site-packages`.

It is the dictionaries arrangement — the owner's own data, moved between the owner's own machines,
populated once and rarely again — and it is never deleted by `--reset-data`.

**Licensing is not a reason for any of this**, and an earlier draft of this document said it was. The
bundle's one attribution-bearing source is CC-BY 3.0, which permits redistribution and commercial use;
the only condition is credit, and it already travels inside the bundle's own `licenses/` directory and
the other repository's `NOTICE.md`. The rest is CC0. Publishing a *generated loop* would mean crediting
that one source; running the tool imposes nothing at all.

### 16 · One word that may not appear

The obvious English word for what a loop does to you is a **commercial product name for a product that
does the same thing**, and is prohibited in both repositories — in code, comments, identifiers,
documents and directory names. One occurrence exists in Acervo today, in a `models/redact.py`
docstring crediting where that module's redaction logic came from; step 1 replaces it with `lexibeat`.
`§5` greps for it, so the rule is checked rather than remembered.

This is also why the artifact is a **loop** rather than a lesson: "lesson" will be overloaded the day a
second kind of lesson exists, and a loop is a thing that repeats, which is both accurate and free.

### 17 · What is deliberately not built

- **No Chatterbox, no local model, no GPU** in this integration. A local voice is its own experiment;
  the NAS cannot run one, and the injected-provider seam means trying one later changes nothing here.
- **No second provider layer, credential set, rate limiter or cooldown store** — the whole point of
  §2.3.
- **No compatibility path and no backfill.** A word without a `primaryGloss` is not eligible for a
  loop; nothing adapts it, nothing fills it in later, and the database is rebuilt.
- **No loop in an export bundle.** A loop is a rendering of words the bundle already carries, from a
  seed the record names — reproducible, and megabytes of it is not what a text archive is for. Study
  state is left out for the same kind of reason.

---

## §3 · What this retires

- **`pronunciation_settings.expressive`** and the `Speak examples with their emotion` switch, replaced
  by the per-use order choice (§2.7).
- Nothing else here. There is no earlier loop implementation to withdraw.

In the other repository step 3 retired the six-row lesson cap, the assumption that a lesson
synthesises its own speech with a voice it chose, the Spanish-and-English-shaped pattern table, the
two-phase `lesson.py` whose split existed only to fit a GPU reservation, and `emotion.py` — the
twelve-name table, the emoji map and the Spanish-punctuation heuristic — replaced outright by the
caller's free text.

Two things were adjacent rather than required, and the owner took them: the stopped public Space, and
with it the CUDA backend, the vendored runtime and the build script. Its CI is now a test job on pull
requests, reused by the release workflow rather than copied into it. librosa went with them from the runtime — the music path used it for resampling alone, and
through it numba and llvmlite — so a service install is 131 MB rather than most of 534.

---

## §4 · The steps

### Step 1 · The name, and this document

`models/redact.py`, and this file. Nothing else starts first.

### Step 2 · The prompt experiment, which gates step 4 — **done**

`experiments/compose-lesson-line/`, run 18 September 2026 for $4.04. The verdict is in §2.8 and the
numbers are in that directory's README: no measurable cost to the rest of the article, so step 4
proceeds as written and the candidate prompt in `arms/after.md` is what lands in `prompts/`.

Two follow-ups it opened, neither blocking: the `emotion: null` boundary wants a tuning pass (`picar`
returns null where a direction would serve a loop better), and **article quality deserves its own
experiment against ground truth** rather than against another article — a pairwise comparison cannot
see a defect both arms share. Both are recorded in [`article-quality.md`](article-quality.md).

### Step 3 · `lexibeat` becomes a dependency — **done**

Landed 18 September 2026 in that repository as **v0.2.0**, 142 tests green with the sample
bundle materialized, wheel built. The
contract it produced is recorded in §2.3, §2.4, §2.10, §2.11 and §2.12 above, and written out
in full in that repository's `docs/service.md` with `docs/openapi-v1.json` as the machine copy.
Three things were the owner's call and were taken: the Space and the CUDA half **removed**,
`emotion.py` **deleted outright**, and a release workflow written as well as the packaging.
What follows is what step 3 was, kept because §2's decisions refer to it.

**Dispatch becomes capability-based, which is what makes an injected voice work at all:**

- `Speaker.__init__` reads `CAPABILITIES[name]` and derives its `post_process_*` flags from the name,
  so an injected backend under a new name raises `KeyError`. Read `backend_instance.capabilities`.
- `lesson.py` hard-codes `backend="chatterbox"`, so an injected backend inherits chatterbox's profile
  and the lesson path can therefore **never** apply local pitch or speed. That is precisely the
  fallback §2.4 depends on.
- `arrange.py` branches on `speaker.backend.name == "chatterbox"` for both the prosody table and the
  long-outlier retry.

**The pattern stops being bilingual.** Its slots are literally `("es", 0)` and `("en", 0)`, and
`gemini_prompt` reads `"native Spanish" if lang == "es" else "native English"`. Slots become
`source`/`target`, and the language name comes from the request.

**Emotion becomes free text.** `delivery_instruction` slots a twelve-name enum into *"Speak in a {name}
but clear tone"*; Acervo sends a phrase. Accept a direction string, keep the prosody words appended, and
drop the emoji path from the lesson input entirely — an emoji column and a Spanish-punctuation
heuristic have no place when the host supplies a direction.

**The API**, redesigned rather than extended: `/api/v1` with a checked-in OpenAPI snapshot, a liveness
route, a `schema` route reporting patterns, families and `production_bundle`, and the operation-shaped
render of §2.10 taking words and answering with the track and the timeline. `build_timeline` moves out
of `demo.py` into the library. Lift the six-item cap, and generalise `_long_duration_outlier`, which
requires exactly three lengths — that is what stands between three repetitions and four.

**Two bugs found while surveying**, both worth fixing there: `gain_db` never audible in any backend
(§2.6), and `delivery_instruction`'s dead zones making two takes of an `emphatic` word identical.

**Packaging and weight:** `[build-system]`, console scripts, a wheel, `uv lock`, a tag with
`SHA256SUMS`, and a CI job that runs the tests on a pull request rather than only on the way to a
deploy. The bundle root read from the environment. MP3 output. `finalize_lesson`'s refusal of any path
outside its managed directory relaxed. A slim runtime is `numpy`, `scipy`, `soundfile`, `pyloudnorm`
and `librosa` — needed in the music path only for `resample`, so replacing those four calls with `soxr`
would drop numba and llvmlite and most of a 534 MB environment; `pedalboard` is already optional behind
`try/except`, and nothing in the music path imports torch. Publish the sample bundle as a release
artifact with digests, plus `bundle fetch --into DIR` and `bundle verify`.

**Privacy:** remove the hardcoded personal vocabulary path in `cli.py` and the external-volume default
in `library.py`. That repository may be public too, and a home path is a home path.

**What is still open, and it is the tag.** The work is committed there and its checks pass locally,
but a version pin needs a *release*: the tag, the workflow run that builds the wheel and writes
`SHA256SUMS`, and one `lexibeat-bundle publish` plus `gh release upload` from the laptop for the
1.8 GB sample bundle, which is Git-LFS tracked and which a runner would have to pull in full to
repack. §2.1's digests come from that release's `SHA256SUMS`, so **step 6's
`deploy/acervo/lexibeat/pin.json` waits on it** — which is why nothing under `deploy/` moved here.
Steps 4, 5, 7, 8 and 9 do not: none of them touches the pin.

### Step 4 · The data model and the prompt — **done**

`primaryGloss` and `emotion` on the lexeme; `loops` and `loopItems` as collections ten and eleven.
Server: `db/tables.py`'s `REPLICATED`, `domain/projection.py`, `domain/validation.py`,
`services/articles.py`'s `LEXEME_FIELDS`, `services/capture/draft.py`, `seed_data.py` and
`SCHEMA_VERSION` in `domain/__init__.py`. Client: `domain.ts`, `localDatabase.ts`, `repository.ts`
(`saveLoop` and the cascade), `api.ts`, `yaml.ts`, `articleEdit.ts`, `selectors.ts` (view models,
derived title, the sampler), and `transfer.ts` — loops are not exported. The prompt is
`experiments/compose-lesson-line/arms/after.md` verbatim, and `prompts/acervo_chat.md`'s
addressable-field table gains both names. Then `./deploy.sh --reset-database`.

Three things this step found, all recorded rather than silently done:

- **The bootstrap migration needed no edit.** Its revision id is a digest of the schema shape, so
  adding two tables and two columns moved the head from `bootstrap_72fd55014c6e` to
  `bootstrap_1c4fd20cc877` by itself — which is exactly the guard working. The list above named it
  as work; it is not.
- **`baseOf` was not touched either.** It is "every record of one entry" for `POST /articles`, and a
  loop is not part of a word's article.
- **`position` is `loop_order` at the storage boundary**, beside `vocab_order`, `topic_order` and
  `sense_order`.

### Step 5 · The orders, the seam route and the take cache — **done**

Rename the two orders in `ModelPanel.tsx`; add the per-use Delivery choice to `pronunciation_settings`,
`services/pronunciations.py` and `PronunciationPanel.tsx`; delete `expressive`. Add
`POST /pronunciations/take` reusing `_speak`, the render-scoped token it accepts, and the
content-addressed FLAC take store.

What it decided along the way:

- **The take store lives beside the database**, not on the media volume: a take is a cache, nothing
  references it and the media route must not serve it. That is also why it needs no new mount and no
  new environment variable, and why the prune is `python -m acervo.admin takes prune` in the server
  container rather than a worker subcommand — the worker has no reason to hold that volume.
  Unbounded on purpose, emptied by hand, as dictionaries and media already are.
- **Delivery defaults**: words read by the clear order, examples and loops by the directed one. That
  preserves how examples sound today and makes the cheap voice the default for the field read most.
- **`pronunciation/targets.py` decides the *use*, never the order.** That package stands alone beside
  the provider package and the article view, so it may not read settings; the service maps use to
  order. `Target.reading` became `Target.use`.
- **One rule computes the cache key, and it has three callers.** `speak.asked_of` says what a pair
  would actually be *sent* — the voice after its own limits, the direction only if the row declares
  `style: instruction` — and is used by the call itself and by both halves of the cache. Keying on
  what was *asked for* rather than what came back is what lets the key exist before the call as well
  as after it; keying on `result.voice` made every second request miss.
- **`pronunciation_settings` changed shape, so the Alembic head moved again.** It is not a replicated
  table, so `SCHEMA_VERSION` stays 11 — but the database still has to be rebuilt.

### Step 6 · The deployment — **done**

`deploy/acervo/lexibeat/{pin.json,Dockerfile,entrypoint.sh,serve.py}`; `scripts/fetch_lexibeat.sh`
with `--check` and `--force`; the portless service, the samples volume and `ACERVO_LEXIBEAT_URL` in
`deploy/acervo/compose.yaml`; the wheel copy in `scripts/package_acervo_server.sh`; dirs, paths and a
health-wait loop in `deploy/acervo/install.sh`; the fetch step in all three jobs of
`.github/workflows/tests.yml` and the Dockerfile in its `multi-arch-build` matrix; the Dockerfile in
`test_server_bundle_contents.py`'s `DOCKERFILES`; and in `test_deployment.py` the never-deleted volume
and the assertion that this service holds no provider credential.

Then fetch the bundle on the NAS, render one loop by hand, and **set the poll and timeout from that
measurement** rather than from feel — `python -m acervo.admin calls` exists so a bound is read rather
than invented.

**Measured, in a rehearsal against a real Acervo and the real bundle**, three words over the directed
order (`google-tts` / `gemini-3.1-flash-tts-preview`, `X-Acervo-Direction: sent`):

| | |
|---|---|
| Render | 65.5 s for 79.1 s of audio |
| Per utterance | **3.6 s** — 18 takes, all recorded |
| Per word | 21.8 s |
| Bed | `gentle-game`, a sampled family, 86 BPM |
| Track | 1.3 MB, 128 kbps, stereo |

So a twelve-word loop is ~72 takes ≈ **4½ minutes**, and step 7's poll should be seconds rather than
the corpus job's twenty — a render reports progress far more often than a channel scan does. The
take cache is what makes a second loop sharing words cheaper, and `admin takes show` is how to see it.

Four things this step decided or found:

- **The client landed early, in `src/acervo/loops/client.py`.** The verification needs to post a loop
  and follow it, and writing that wire shape twice — once for a script, once for step 7 — would have
  been two places to keep in step. It is step 7's named home, tested here against responses recorded
  from the real service, and `test_layering.py` has its stands-alone case.
- **The render command is `acervo_worker.py loop render`, not a script.** A new job is a new worker
  subcommand and never a new service; and the generator publishes no port, so only something on the
  compose network can reach it. It signs in with the owner's password and hands its *session* token
  to the generator, which `POST /pronunciations/take` accepts by design.
- **`pedalboard` needs `libatomic1`, which slim-bookworm does not ship.** Without it the import
  fails, LexiBeat falls back to librosa, and the slim runtime deliberately has none — so the render
  died nine utterances in with `ModuleNotFoundError: No module named 'librosa'`, naming the wrong
  dependency entirely. The image installs it; the misleading message is a defect to fix in LexiBeat's
  next release, recorded below.
- **`speech.delivery` is not sent yet.** `serve.py` reads it and defaults to `directed`, which is
  correct for this deployment. Step 7 adds the field to LexiBeat's request body — a version bump and
  a re-pin — which is what buys the plain order its one-call-a-line economy (§2.6).

**Two more for LexiBeat's next release**, found by step 9. Its default seed is
`secrets.randbits(64)` (`generator.py`), which cannot round-trip through JSON into any reader whose
numbers are doubles — a browser, most JSON libraries — so a host that does not send its own seed
gets a value it cannot store. 2^53 would do everything 2^64 does here, the seed being a replay token
rather than a key. And `dsp.time_stretch` / `dsp.pitch_shift` still name the wrong dependency, below.

~~**One defect for LexiBeat's next release**~~ — **fixed in 0.3.0.** `dsp.time_stretch` and
`dsp.pitch_shift` wrapped the pedalboard *call* as well as its import, so any pedalboard problem fell
through to `import librosa` and surfaced as `ModuleNotFoundError: No module named 'librosa'`, naming
a dependency that was removed on purpose. The `try` now covers the import alone and the refusal names
what happened to *both*. The seed above is still open, and does not matter while Acervo mints its own.

### Step 7 · The pipeline — **done**

`src/acervo/loops/` — the `httpx` client that is the only place the service's wire shape is read, with
its own refusal vocabulary, as `clips/corpus.py` is for the corpus (it landed in step 6, which needed
it to verify). `services/loops.py` binds it to `Settings`, the graph and `ApiError`. `work/loop.py`
registers the kind, joins `work/kinds.py:_load()` and follows the operation. `api/routes/loops.py`
holds `POST /loops` and an allow-listed `schema` passthrough — written out, never concatenated.
`api/routes/jobs.py` gains the `loop` entry in `ENQUEUEABLE`, which is Try again.
`test_layering.py` has the stands-alone case and the vacuity assertion for `loops/`.

If the row is written and queuing the job then fails, the loop shows as never rendered and Try again
queues it. That is §2.9's derived state doing its job.

Four things this step decided:

- **`src/acervo/tokens.py` is a new leaf, and it exists because of the layering rule.** A render needs
  a render-scoped token, minting lived in `api/auth.py`, and `work/` may not import `api/`. Rather
  than route a job back through the request path, the signing rule moved to a module that knows JWT
  and a secret and nothing else; `api/auth.py` re-exports from it, so every existing caller reads
  unchanged and the rule is written down once instead of twice.
- **Nothing is held in memory between the two steps.** `loop.render` writes the operation id down and
  `loop.store` reads it back and asks the generator again for the finished operation. An in-memory
  hand-off works until the first retry — a step that fails re-enters the handler from the top with
  only what was written down — and the earlier draft had a `loops_interrupted` refusal in it whose
  only purpose was to say so.
- **The render holds the `audio` lane, not a lane of its own.** That is the allowance it actually
  spends: the generator holds no credential and speaks every line by calling home to
  `POST /pronunciations/take`, so a quota refused for a loop is the quota a word's pronunciation
  would have been refused from.
- **`loops_busy` and `loops_unreachable` join `retry.TRANSIENT`.** They are the same two conditions
  two of the three model-call codes already name — busy, and not there this second — and both pass on
  their own. `loops_failed` deliberately does not: a render the generator ran and could not finish is
  a fact about that request, and asking again changes nothing.

~~**Still not sent: `speech.delivery`.**~~ **Sent, in 0.3.0.** `SpeechBody` takes it, `RenderContext`
carries it, and `services/loops.delivery` now travels with the render rather than only into the
step's detail. So the plain order finally costs what §2.6 says it costs — one recording a line,
varied locally — instead of three identical calls, and the fallback §2.4 promises is reachable for
the first time. The same release narrowed `dsp.py`'s `try` to the import, so a pedalboard failure no
longer reports itself as a missing `librosa`; that mattered more once the plain path actually ran
that code.

### Step 9 · What the deployment taught — **done**

Step 8 shipped and the feature did not work on the server. Three faults, one causing another, and
the reversal of a decision that had been made on a false premise.

- **The sample pack was in a store the service never mounts.** The documented fetch —
  `docker compose -f compose.yaml run --rm lexibeat lexibeat-bundle fetch …` — omits the
  deployment's env file, so `ACERVO_LEXIBEAT_BUNDLE` is unset, compose falls back to a *named
  volume*, and 1.9 GB unpacks, verifies its manifest and reports success into a directory nothing
  serves from. It is a silent failure that looks exactly like a success. `./deploy.sh
  --install-samples` is now the only documented way: it reads the URL and digest from the pin and
  passes the project name and every env file, and the entrypoint's own hint — the thing an operator
  reads at the moment they hit this — prints it instead of the command that caused it.
- **§2.2 is reversed: no pack, no loop.** That section said a pack-less server warns rather than
  refuses, on the understanding that the render falls back to the synthesised palette. It does not:
  fifteen of the generator's sixteen bed families name instruments loaded from its catalogue, so a
  render dies partway through on a missing sample and how far it gets depends on which voices the
  seed draws. `POST /loops` refuses with `loops_no_samples` before writing a row and the dialog
  disables its button. Refusing in a second beats failing in four minutes.
- **A failure's sentence was thrown away three times** — by `services/loops.refusal`, which kept only
  its own constant; by the runner's rollup, which copied the failed step's `error` but not its
  `message`; and by `ProgressStrip`, whose `loop.render` case returned a fixed string where the
  `default` branch would have used the message. Each is one line, and between them they turned "No
  samples cached for 'salamander'" into "the loop could not be made".
- **`work/journal.py`**, the second log, and `admin jobs list` showing recent jobs with their error
  and message rather than open ones with neither. The wider question is
  [`observability.md`](observability.md).
- **The Loops surface could not be left.** Two accidental exits existed — Add, and changing language
  — and every obvious one was a dead end: the search box updated a list that was not drawn, and
  Escape was a no-op. There is now one back arrow whose meaning follows the level, and search, ⌘K
  and Escape all leave. The topic rail, which the surface was hiding at every width by borrowing
  `article-open`, now stays wherever there is room and goes only on a phone.
- **The dialog's Music selector was a no-op**: `family` was read by nobody and `POST /loops` enqueued
  with an empty `input`. It is validated against the generator's own catalogue, carried on the job,
  and passed to the render — so Try again asks for the same music too.
- **Acervo mints the seed.** The first render that got as far as storing was thrown away by the
  graph's range check: given no seed, the generator uses `secrets.randbits(64)`, and a 64-bit
  integer does not survive the journey — a JSON number is a double in the browser, so anything above
  2^53 arrives as a *different* number, and SQLite's INTEGER is signed. Four minutes of work lost
  over an integer. Acervo now mints the seed when the loop is created and sends it; the generator
  echoes back what it is given, so the stored value is provably the one that made the bed, and Try
  again reproduces it rather than rolling a new one. The stored range is now the JavaScript
  safe-integer bound, which is the real constraint; 2^31 was arbitrary.
- **The entrypoint lectured the command installing the samples.** `lexibeat-bundle fetch` runs in a
  container of its own, so the entrypoint's bundle verdict printed *before* the fetch it was about
  to perform — telling the owner to install the samples in the middle of doing exactly that. It now
  stays quiet when the command it wraps is the bundle tool.
- **A render says what it is doing.** It reports both a fraction and a phrase — "Synthesizing
  speech", "Rendering the music bed", "Mixing" — and the loops list was showing a fixed "Being
  made…" over the top of them. Its own words, because it is the only thing that knows and a sentence
  invented on this side would drift from it at the next release.

### Step 8 · The interface — **done**

Drawn in `design/ui-prototype/` first, in three shapes, and built from the one that was chosen. That
order was worth it: the layout question could not be settled by argument, and two of the three were
rejected in a minute of looking at them.

`App.tsx` for the way in and the view switch; `styles.css` with `design/ui-prototype/` changed in the
same commit and the loops section byte-identical between them; `LoopView.tsx`, `LoopPlayer.tsx`,
`MadeBar.tsx` (was `LoopBar.tsx`, renamed when Stories joined it), `LoopDialog.tsx` and `loops.ts`; `mediaStore.ts`'s third kind; `ActivitySettings.tsx`'s
label and retry set; `ProgressStrip.tsx`'s two phases; and Settings ▸ Loops with keep-on-device, the
kept byte count and the generator's own state.

No component imports its own stylesheet: `scripts/verify_pwa.py` holds the build to one, and the
dynamic-CSS failure it exists to catch killed the macOS application once already.

Five things this step decided:

- **The player takes the screen, with its controls at the foot.** Of the three drawn — controls above
  the words, controls inside each loop's card, controls under the words — the third is the one every
  music player already uses, and the only one where the thing you reach for never moves. They are the
  footer of a column that owns its height, not a sticky element inside a scroller, which is a
  different thing: sticky still drifts at the ends of a scroll.
- **The way in is the chip on a desktop and the bar on a phone.** One component in two skins, so what
  they say cannot disagree. A bar across the foot of a wide window is a lot of furniture for one line
  of text; the top bar is already where everything reachable from anywhere lives.
- **`loopItems` gained `repeats` and `repeatSeconds`**, which took `SCHEMA_VERSION` to 12 and needs a
  `--reset-database`. Without them the player could mark only the first pass of each word, because
  four times cannot say where the other four utterances fall. Two numbers rather than six spans keeps
  §2.9's promise that a pattern change does not move the schema, and `loops/client.py` is where the
  spans become the numbers.
- **The mark is colour and nothing else.** No weight, no size, no offset, no motion. This is the one
  surface meant to be left running and glanced at, and the same rule the article's change marks live
  by matters more here: a screen that reflows under the eye is not one you can glance at.
- **The topic rail is hidden on this surface at every width.** A topic files a *word*, and nothing
  here is filed. The top bar stays, unlike on an open article: a loop is a thing you put on and then
  go looking for the next word, so search and the language menu are still what you want in reach.

### Step 9 · Optional, and separately

**Choosing words by hand** — a Select control in the list header, a tick per row, a count where the
header was, and *Make a loop* carrying the picks into the same dialog. Same route, different list, no
server change.

**Transport controls** — play and pause, next and previous, and continuous play across several loops.
This is the feature the name was chosen for, and it is a player change with no schema behind it.

---

## §5 · Verification

```bash
.venv/bin/python -m pytest          # incl. the layering cases and a loops/ fixture test
npm --prefix web run test
npm --prefix web run build && npm run test:pwa      # the one-stylesheet rule
RUN_DOCKER_INTEGRATION_TESTS=true .venv/bin/python -m pytest tests/integration/test_acervo_server_docker.py
```

The wire shape is checked offline against a recorded response, as `tests/unit/clips/test_corpus.py` is,
plus one gated live contract test against a running container. A copy of that service's OpenAPI
document is **not** committed here, for the reason `spoken-clips.md` §5 gives: it would be re-committed
on every bump and read by nobody.

**The prohibited word returns nothing**, in either repository, case-insensitively, across code,
comments and documents. On the other side this is now a CI step rather than a habit — and it builds
the pattern from two halves at runtime, so the check is not itself the one occurrence.

**On the NAS, end to end** — reset, create the account, compose two words, fetch the sample bundle, make
a twelve-word loop from the list, watch the steps in the progress strip, then make a second loop sharing
several words and confirm from the call log that the shared takes cost nothing.

**A plain-voice loop** — set loop delivery to the clear voice, confirm the render still succeeds, that
`X-Acervo-Direction: dropped` comes back, and that the three takes still differ audibly. That is the
fallback working rather than silently flattening.

**On the phone, which is the only test that matters** — a loop plays; the words track the audio; the
screen locks and it keeps playing with lock-screen controls; a kept loop plays with no connection;
pressing a word's play button stops the loop instead of overlapping it.

**And the rules still hold** — reordering or deleting a loop with the server unreachable fails visibly
and changes nothing locally; an export bundle contains no loop; a word with no `primaryGloss` is refused
by name rather than silently dropped from the track; and nothing, anywhere, backfills it.
