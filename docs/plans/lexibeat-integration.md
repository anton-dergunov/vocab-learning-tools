# LexiBeat · integrating the loop generator

**Status:** Designed, nothing built. Step 1 of §4 is this document and one word deleted from
`models/redact.py`; step 2 is an experiment that gates the prompt change; step 3 happens in the other
repository, because Acervo consumes a tag.

A word's article can already say what a word means, show a picture of it, play a native speaker using
it, and read every field aloud. What none of that does is get a word *stuck in your head*.
[`lexibeat`](https://github.com/anton-dergunov/lexibeat) exists to do that: the word and one
translation, each spoken three times on a bar grid over a procedurally synthesised bed, with a
silence in the middle to recall the answer in. This document is how the two projects meet.

It is the **second** companion repository, after [`spoken-usage-retrieval`](spoken-clips.md), and a
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

And the facts that rule things out:

- **Its HTTP surface and its Gradio explorer were built to demonstrate the engine**, not to be
  integrated against: the lesson flow is reachable in-process or through Gradio and nowhere else, and
  its input is a two-column table capped at six rows with no emotion column. It is **open to
  redesign**, and this integration redesigns it.
- **Its default voice is Chatterbox Multilingual**, local through MLX or CUDA, at 5.5–6.1 seconds an
  utterance. The NAS has neither MLX nor a GPU, and the public Space that ran it is stopped. Local
  voices are a later experiment; nothing here waits on them.
- **It is not installable.** No `[build-system]`, no console scripts, no tags, no releases, and CI
  that runs the tests only on the way to deploying the Space.

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

**Two:** the quantisation has dead zones, and `emphatic` falls in one. Widening that vocabulary is
worth doing in the other repository; until it is, §2.5's key is what keeps the takes distinct.

**Three:** `gain_db` has never done anything, in any backend. It is applied and then erased by the
peak-normalise eleven lines later. The −0.8/+0.6 dB column of `Prosody.TABLE` is decoration. That is a
bug in that repository, not a constraint here, and it is listed in §4.

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
fields. Article quality itself is untouched by this run and is its own experiment — both arms wrote
`/ˈaska/` for `el asco`, which is simply wrong.

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
[`processing-flow.md`](processing-flow.md) §4.14's *"anything heavy is out of scope for the runner"*
true rather than merely restated. The runner holds a lane and a poll timer.

A rate limit surfaces as one of the three transient codes and rests as usual; the take cache is why
the restart is cheap.

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

In the other repository it retires the six-row lesson cap, the assumption that a lesson synthesises its
own speech with a voice it chose, and the Spanish-and-English-shaped pattern table. Two things are
adjacent rather than required, and the owner's call: the stopped public Space, and with it the CUDA
backend, the vendored runtime and the build script that between them are why that checkout is 9 GB and
its CI takes an hour.

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
see a defect both arms share.

### Step 3 · `lexibeat` becomes a dependency

In that repository, and its own checks pass locally before the tag is pushed.

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

### Step 4 · The data model and the prompt

`primaryGloss` and `emotion` on the lexeme; `loops` and `loopItems` as collections ten and eleven.
Server: `db/tables.py`'s `REPLICATED`, `domain/projection.py`, the bootstrap migration,
`SCHEMA_VERSION` in `domain/__init__.py`. Client: `domain.ts`, `localDatabase.ts`, `repository.ts`
(`saveLoop`, the cascade, `baseOf`), `api.ts`, `yaml.ts`, `selectors.ts` (view models, derived title,
the sampler), and `transfer.ts` — loops are not exported. Then `./deploy.sh --reset-database`.

### Step 5 · The orders, the seam route and the take cache

Rename the two orders in `ModelPanel.tsx`; add the per-use Delivery choice to `pronunciation_settings`,
`services/pronunciations.py` and `PronunciationPanel.tsx`; delete `expressive`. Add
`POST /pronunciations/take` reusing `_speak`, the render-scoped token it accepts, and the
content-addressed FLAC take store.

### Step 6 · The deployment

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

### Step 7 · The pipeline

`src/acervo/loops/` — the `httpx` client that is the only place the service's wire shape is read, with
its own refusal vocabulary, as `clips/corpus.py` is for the corpus. `services/loops.py` binds it to
`Settings`, the graph and `ApiError`. `work/loop.py` registers the kind, joins `work/kinds.py:_load()`
and follows the operation. `api/routes/loops.py` holds `POST /loops`, the settings pair and an
allow-listed `schema` passthrough — written out, never concatenated. `api/routes/jobs.py` gains the
`loop` entry in `ENQUEUEABLE`. `test_layering.py` gains a stands-alone case and a vacuity assertion for
`loops/`.

If the row is written and queuing the job then fails, the loop shows as never rendered and Try again
queues it. That is §2.9's derived state doing its job.

### Step 8 · The interface

`App.tsx` for the bar and the view switch; `styles.css` with `design/ui-prototype/` changed in the same
commit; `LoopView.tsx`, `LoopPlayer.tsx`, `LoopDialog.tsx` and `loops.ts`; `mediaStore.ts`'s third
kind; `ActivitySettings.tsx`'s labels and retry set; `ProgressStrip.tsx`'s phases; and a Settings ▸
Loops page with keep-on-device, the kept byte count and a service status block modelled on
`ClipPanel`'s corpus block.

No component imports its own stylesheet: `scripts/verify_pwa.py` holds the build to one, and the
dynamic-CSS failure it exists to catch killed the macOS application once already.

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
comments and documents.

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
