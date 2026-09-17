# LexiBeat · integrating the lesson generator

**Status:** Designed, nothing built. Step 1 of §4 is this document; step 2 is an experiment that
gates the prompt change, and step 3 happens in the other repository, because Acervo consumes a tag.

A word's article can already say what a word means, show a picture of it, play a native speaker
using it, and read every field aloud. What none of that does is get a word *stuck in your head*.
[`lexibeat`](https://github.com/anton-dergunov/lexibeat) exists to do that: the word and one
translation, spoken on a bar grid over a procedurally synthesised bed, with a silence in the middle
to recall the answer in. This document is how the two projects meet.

It is the **second** companion repository, after
[`spoken-usage-retrieval`](spoken-clips.md), and a third is expected. So the shape matters more than
the feature: what is written here is the template's second use, and where it departs from the first
it says why.

## Outcome

You select nothing and press one button: twelve words from whatever you are looking at become a
four-minute track you can put on in the kitchen. It is listed in its own surface, plays with the
screen locked, shows each word as it arrives, and can be reordered or deleted. Making one is a
server job you can walk away from, and a lesson is built out of clips the words already have.

Both repositories keep their own release cadence. Acervo names one version and upgrades when it
chooses.

---

## §1 · What the other repository already gives

Read its `README.md`, `docs/design.md` and `docs/music-generation.md` before starting. In short:

- **A procedural music engine, not a model.** `lexibeat/music.py` synthesises four stems — `pad`,
  `bass`, `drums`, `lead` — with numpy and `scipy.signal`, from CC0 samples, against a known beat
  grid. No GPU, no network, no model call, and byte-identical from a seed. Its own tests assert the
  no-network property (`test_resolution_does_not_use_network`). **This is why the lesson can be built
  on the NAS at all.**
- **A deterministic bed description.** `bedspec.py` holds `ENGINE_VERSION`, `BED_SPEC_SCHEMA_VERSION`
  and the 16 `_WIDE_FAMILIES` that become `STYLES`; `profiles.py` gates which families a request may
  use (14 under `production-v1`); `generator.py:resolve_request` builds candidates, scores them with
  `quality.py`, and writes every choice — down to each `SampleRef(collection, asset_id, sha256)` and
  per-zone gain — into the spec. A family plus a seed replays exactly.
- **An arrangement engine.** `arrange.py` is the whole of it: `PATTERNS` maps a name to a list of
  one-bar slots, where a slot is a language, a `"gap"` to recall in, or a `"rest"`. `retrieval` is
  the preset — word, gap, answer, then two more pairs, then a rest, eight bars an item — and every
  utterance starts on a downbeat, budgeted to `grid.bar * 0.92` and time-stretched to fit with a
  ratio capped at 1.35. Measured onset error against the downbeat is a median of 15 ms.
- **A mix that ducks.** `mix.py` sidechains each stem from the speech envelope (attack 100 ms,
  release 400 ms) at a per-layer depth the spec carries, then limits at 0.97; speech −16 LUFS against
  music −26.
- **Two timing exposures.** `lesson.py:_subtitles` holds each caption until the next utterance so the
  answer is never revealed early, and `demo.py:build_timeline` gives the richer per-item structure —
  `start`, `source_reveal`, `target_reveal`, `end` and every utterance's span. **That second one is
  the interface's cue data**, and it currently lives in the demo script rather than the library.
- **A 1.8 GB sample bundle** under `assets/production-core/v1/`, Git-LFS tracked: a
  `catalog.sqlite3`, 1,112 content-addressed assets under `samples/<collection>/<asset_id>.<ext>`,
  95 named-pack files, and a `manifest.json` carrying a SHA-256 per asset. Seven CC0 collections plus
  Salamander, which is CC-BY 3.0 and the one attribution-bearing source. Without the bundle the
  engine still works and offers only the sample-free `electronic` palette, reporting
  `production_bundle: false`.
- **A FastAPI surface**, `explorer_web.py:create_api`, with strict `extra="forbid"` request models, a
  2 MiB request cap, a work queue of one concurrent render answering 429 `render_queue_full`, and a
  render→`artifact_id`→`GET /api/audio/{artifact_id}` shape. It never daemonizes: `run_local` blocks
  in `uvicorn.run` and expects a host to supervise it. Acervo is that host.

And three facts that decide the design by ruling things out:

- **There is no lesson route.** The FastAPI surface is bed-only. The lesson flow —
  `lesson.py:render_lesson_speech` then `finalize_lesson` — is reachable in-process or through
  Gradio, and nowhere else. Its input, `normalize_lesson_rows`, is a two-column table capped at
  **six** rows with no emotion column at all.
- **Its voice is Chatterbox Multilingual**, local through MLX or CUDA on the public Space, at 5.5–6.1
  seconds an utterance. `lesson.py` hardcodes it and raises on any other model. The NAS has neither
  MLX nor a GPU. The Gemini and Vertex backends in `voice.py` are experimental, and the emotion they
  take is a natural-language direction — the same idea Acervo already sends.
- **It is not installable.** No `[build-system]`, no console scripts, no tags, no releases, and CI
  that runs the tests only on the way to deploying the Space.

---

## §2 · The decisions

### 1 · Two repositories, one version pin

Unchanged from `spoken-clips.md` §2.1, and for the same reasons: `deploy/acervo/lexibeat/pin.json`
names one version, one tag and the digest of each artifact, and `scripts/fetch_lexibeat.sh` turns
that into files under gitignored `vendor/lexibeat/`. Digests come from the release's own `SHA256SUMS`.
A locally built wheel that matches is left alone, which is what makes "try it before tagging" work;
anything the pin does not name is pruned, because the image installs `vendor/lexibeat/*.whl` and two
wheels of one package fail the build.

There is **no npm half** to this pin. LexiBeat ships no player component, and Acervo's lesson player
is Acervo's — see §2.8.

### 2 · A service beside Acervo, not a package inside it

`lexibeat` becomes a compose service with no published port, reached at
`http://lexibeat:8000/api/v1` over the project network, exactly as the retrieval service is. The
image is **Acervo's** — `deploy/acervo/lexibeat/Dockerfile` around the foreign wheel — because the
package does not self-daemonize and process, volumes and URL are the host's.

**It has no `serve.py`, and that absence is the design.** The retrieval image carries
`src/acervo/models`, `src/acervo/speech` and `models/catalogue.json` so that `create_app` can be
handed the owner's chain. This one carries nothing of Acervo's, holds no credential, and makes no
model call, because of §2.3. It is therefore the one companion service absent from
`test_deployment.py`'s "every service that calls a model is given the same credentials" tuple, and a
test asserts that absence deliberately so a later reader does not mistake it for an oversight.

Its healthcheck asserts **liveness**, and not that the sample bundle is present. A fresh deployment
has no bundle and still serves; readiness gating would fail the install of a working service, which
is the lesson `spoken-clips.md` §2.2 paid for.

### 3 · Acervo speaks; LexiBeat arranges

**The seam is audio, not text.** Acervo records the two spoken lines and posts them; the service
returns the bed, the arrangement, the mix and the timeline. It synthesises nothing for Acervo.

This is the opposite direction from the translation seam, and the difference is worth stating
plainly, because the two look alike and are not:

> A translation is a pure function whose provider is a *cache key*. That is why
> `spoken-usage-retrieval` can be handed `acervo.models` through
> `create_app(…, translation_provider=…)` and why `ChainGenerator` reports the chain rather than the
> row that answered. **A spoken line is a record the owner keeps.** It needs the graph, the media
> directory and an allocated revision, none of which may enter a companion container. Injecting a
> chain there would mean duplicating the clip cache, the per-model voice choices and the staleness
> rule inside that repository — or throwing all three away and paying Gemini for every lesson.

So the rule the two integrations share is the one that matters: **one way to call a model, one rate
limiter, one cooldown.** Where the call happens follows from where the record lives.

On LexiBeat's side this is one new `Backend` behind the Protocol it already has — resample to
44.1 kHz mono float32, peak-normalise, return — so `arrange.py`, `mix.py` and `lesson.py` are
untouched, and the existing two-phase split it built for the Space (a speech phase, then a CPU
phase, with a JSON job between) is exactly the seam. Its per-repetition variation goes through the
`"post-process"` capability path `kokoro` and `cloudflare` already use.

Its own backends stay. That repository is where the owner iterates on voices, and a lesson made by
its CLI is its business.

### 4 · A lesson line is the fifth and sixth spoken field

`pronunciation_id(target_kind, target_id)` takes two arbitrary strings, so two new kinds cost no
signature change and no new id function:

- `lessonTerm` — the headword, read with the word's own emotion, in the vocabulary's language.
- `lessonGloss` — the single translation, read in `glossLangs[0]`.

Both keyed on the **lexeme** id. Everything then follows from machinery that exists: one clip per
field, re-recording rewrites the row rather than adding a second, the clip is stale exactly when its
`text` no longer matches what the record says, the bytes are a few kilobytes and therefore
replicated, `fill()` brings them to every device, and Settings ▸ Pronunciation's voice choice
applies. A lesson made from twelve words the owner has drilled before costs **zero** model calls.

Two consequences to handle rather than discover:

- `targets.py`'s `COLLECTION` can no longer be inverted, because two kinds now read fields of one
  collection. `services/pronunciations.py:ROUTE_KINDS` goes and the route addresses a target kind
  directly — `POST /pronunciations/{kind}/{id}`. No compatibility shim; every caller changes.
- Nothing pre-records these on save. `wanted()` is what a save asks for, and recording two Gemini
  clips for every word in case a lesson ever uses it is the wrong default. The lesson job records
  what it needs, when it needs it.

### 5 · The single translation and the emotion are fields on the lexeme, written by the compose prompt

`shortGloss` is right for the list and wrong for a lesson: *casa* → `house, home` cannot be spoken on
a beat. What a lesson needs is one word, the most common reading, roughly as long as the source — and
a direction for how it is said. Two fields:

```yaml
headword: asco
shortGloss: disgust, revulsion          # unchanged, for the list
lessonGloss: disgust                    # the one word spoken, in glossLangs[0]
lessonEmotion: repulsed, recoiling slightly
```

**On the lexeme, not the sense**, because a lesson drills a word and must choose exactly one meaning;
asking per sense produces three answers where one is wanted, and moves the choice from the writer —
who has just read every sense — to whoever consumes it.

**`lessonGloss` follows `glossLangs[0]`**, exactly as `shortGloss` and a sense `domain` do, and there
is deliberately no setting for it. A vocabulary's gloss languages are already ordered most preferred
first, so reordering them *is* the control. A separate setting over a single stored string could only
end up naming a language the stored text is not in.

**`lessonEmotion` is a short English direction**, in the same register and under the same rules as an
example's `emotion` — `prompts/acervo_pronounce_style.md` renders it for whichever voice answers, and
a voice that cannot take one reads the word plainly. Emojis do not appear: LexiBeat's `_EMOJI` table
maps twelve emotions onto emoji because its source was an Obsidian vault where the emoji was the only
signal available; Acervo can simply say the thing.

**And this is measured before it is trusted.** The stated risk is not that the fields are wrong but
that a larger prompt makes the *rest* of the article thinner — fewer senses, shorter notes, a
`lessonGloss` that is really just `shortGloss` again. `experiments/compose-lesson-line/` runs the
amended `prompts/acervo_compose.md` against the model set and a fixed word list, and compares
everything except the new fields with what the current prompt produces. If it degrades, the answer is
**not** to carve these two fields into their own call — that is too small a piece to be worth a
second prompt. It is to split `acervo_compose.md` into comparable parts, considered whole, which is
its own task. The experiment's write-up records which way it went and why.

### 6 · A lesson is two replicated collections, and its state is derived

`lessons` — `language`, `styleId`, `seed`, `engineVersion`, `bedFingerprint`, `pattern`, `audioRef`,
`audioMime`, `durationSeconds`, `position` — and `lessonItems` — `lessonId`, `lexemeId`, `position`,
`sourceText`, `targetText`, `emotion`, `startSeconds`, `sourceRevealSeconds`, `targetRevealSeconds`,
`endSeconds`.

- **No status column.** An empty `audioRef` is *not rendered yet*; the job says the rest. This is
  `ImagePrompt`'s rule — four facts already say all of it, and a fifth would be a thing to keep in
  step.
- **No BedSpec blob.** `styleId` + `seed` + `engineVersion` replay the bed byte-identically, and
  `bedFingerprint` is what proves it did. Nothing else in the model stores opaque JSON and this is
  not the place to start.
- **The item text is denormalised on purpose.** A `lessonItem` records what was *said*, so editing
  the word afterwards must not make the player caption a recording it no longer matches. Identical
  reasoning to `pronunciations.text`, and the reason both are safe.
- **No title field.** `selectors.ts` derives one from the source words that fit, the way
  `effectiveShortGloss` derives a gloss. Naming a lesson by hand is a non-goal.
- **`position` orders them**, sparse and renumbered on reorder. No uniqueness constraint, per the data
  rule; ordering is enforced nowhere and merely respected.

Reordering and deleting are ordinary graph writes, and therefore online-only and loud when they fail,
like every other write.

Two new collections take `SCHEMA_VERSION` to 11 and rotate the Alembic head, so this deploys as
`./deploy.sh --reset-database`. That is the normal cost of a schema change here, not an obstacle.

### 7 · Making one is a job, and the heavy work happens outside the runner

A new kind, `lesson`, subject the lesson record, with two steps:

1. **`speech`** — walk the words on the `audio` lane, `step.gate()` before each call and
   `step.progress(done, total)` after, reusing a clip that is current and recording what is missing
   through `services/pronunciations`. A word whose `lessonGloss` is empty is refused, named, and the
   job fails rather than quietly producing a shorter lesson than asked for.
2. **`music`** — one call to the service with every clip inline, then write the returned master into
   `ACERVO_MEDIA_PATH` and the rows through `merge_graph`: **file first, row second**, as
   `services/pronunciations.py` does, because nobody else holds both.

The render itself is CPU-heavy and happens **in the companion container**, which is what keeps
[`processing-flow.md`](processing-flow.md) §4.14's "anything heavy is out of scope for the runner"
true rather than merely restated. The runner waits on one HTTP call.

The clips go **inline as bytes**, base64 in the request. Twelve words is two dozen Opus clips of a
few kilobytes each; forty words stays well under a megabyte, and the service's 2 MiB cap is raised
for this route alone. The alternative — handing that container a URL and a token to fetch from — would
give a service with no credentials a credential, to save nothing.

**Cancellation lands after the render, not inside it.** The runner cancels between calls, and one
bounded call is one gap. `./deploy.sh --cancel-jobs` already documents abandoning what is inside a
call. An operations API on the render route, like the corpus's, is the fallback if a measured render
ever outlives one bounded call — and the measurement comes first.

A 429 `render_queue_full` cannot legitimately happen, the runner being one job at a time; if it does
it is a `Requeue`, not a failure.

### 8 · The words come from what you are looking at

The interface samples N lexeme ids from the scope on screen — this language, this topic, or
everything — as a pure selector over the replica, and posts the list. The server never re-derives
scope, and the route takes ids rather than a query.

That is also what makes the next step cheap: **manual selection is the same route with a different
list**, and therefore a separate, optional piece of work that changes nothing on the server. It is
written down in §4 step 9 rather than built now. Difficulty, newest-first and "words with no lesson
yet" are later options on the same dialog, and each is one selector.

**The style and the pattern catalogues are LexiBeat's**, read from its `schema` route and never
copied here — the rule `spoken-clips.md` §2.10 settled for channels. The dialog offers *Surprise me*
or one of the families the service advertises, so a new family or a second pattern in that repository
appears here with no change at all.

### 9 · A bottom bar, and only over the list

Lessons get their own surface, reached from a bar pinned to the bottom of the window — and
`.app` grows that third grid row **only when no article, external entry or Add view is open.**

The article pane is 780 px of column that already carries the view segments, the delete control, the
progress strip and `AskDock`; a second dock there is prohibited. It cannot collide by accident
either, since `AskDock` renders only when an article is open and the bar only when one is not. The
top bar is left alone: it holds search, scope, Add, sync, settings and the language menu, and on a
phone that is already everything that fits.

A lesson keeps playing while you read a word — the audio element is not the surface — and the
now-playing row is on the bar when you come back. **There is no mini-player over an article**, and
when a render finishes the notice is a toast with an action, which `App.tsx` already has.

### 10 · The track is fetched as a blob and plays from memory

The media route is behind bearer auth, so its URL cannot go in an `<audio src>` — the same reason a
picture is fetched as a blob and `LexemeArticle.tsx` once displayed none at all.

That constraint turns out to be the better design. A whole track in memory means **nothing touches
the network during playback**, which is what a locked screen and a lift need. `mediaStore.ts` gains a
third kind, `lessons`, so a device can keep or forget lessons without touching a picture or a
pronunciation, and `lessons.ts` sets MediaSession metadata and action handlers — the first in this
codebase — and drives the word display from `lessonItems`' timings.

One rule: **`lessons.ts` stops `pronunciation.ts` before it plays, and `pronunciation.ts` stops the
lesson.** Two independent audio elements racing for the same output is a bug with no good failure
mode. The iOS gesture priming `pronunciation.ts` already does applies here too.

A signed, short-lived media URL that would let the browser stream by Range is **not** built. It is a
new credential shape for a file that is better held whole.

### 11 · Two orders, named for what they are, and each use picks one

Today the catalogue's two chains are labelled by use — *Pronunciation — words and definitions* and
*Pronunciation — example sentences* — and an example is **always** read by the expressive order.
`Speak examples with their emotion` only decides whether a direction is *sent*, so switching it off
still spends the expensive voice on every sentence. With lessons there would be three uses and two
orders, and a third chain would make that worse.

So: the orders keep their ids and are renamed for their capability — *a clear, even voice* and *a
voice that takes a direction* — and Settings ▸ Pronunciation ▸ Delivery gives each of the three uses
a choice between them. **Choosing the directed order is asking for emotion**, which is why
`pronunciation_settings.expressive` is deleted rather than left beside the new control: one mechanism
where there were two, and the cheap voice reachable for examples and lesson lines alike.

No third chain. Any voice is a legitimate answer to either question, which is exactly why the
catalogue has one `audio` kind and `defaultChains` has two orders over it.

### 12 · The sample bundle is fetched on the server, and never committed

1.8 GB does not travel the way a compiled dictionary does. A dictionary rides the release archive
because it is small enough to; this cannot ride a tarball streamed over ssh, and it may not enter
git — this repository is public, and one of its sample sources is CC-BY rather than CC0.

So `pin.json` names the bundle and its digest, and a one-shot `docker compose run --rm` of the same
image fetches and verifies it into `acervo-lexibeat-samples`, against the `manifest.json` the bundle
carries. It is the dictionaries arrangement — the owner's own data, moved between the owner's own
machines, populated once and rarely again — and it is never deleted by `--reset-data`.

Until it is there the service answers `production_bundle: false` and offers the sample-free
`electronic` palette. Settings ▸ Lessons shows that as a fact, the way Settings ▸ Clips shows a
corpus that is down.

### 13 · What is deliberately not built

- **No Chatterbox, no local model, no GPU.** Interesting, and its own task; nothing here depends on
  it, and the NAS cannot run it.
- **No second provider layer, credential set or rate limiter** — the whole point of §2.3.
- **No compatibility path of any kind, and no backfill.** A word without a `lessonGloss` is not
  eligible for a lesson; nothing adapts it, nothing fills it in later, and the database is rebuilt.
- **No lesson in an export bundle.** A lesson is a rendering of words the bundle already carries,
  made from a seed the record names — it is reproducible, and a hundred megabytes of it is not what a
  text archive is for. Study state is left out for the same kind of reason.

---

## §3 · What this retires

- **`pronunciation_settings.expressive`** and the `Speak examples with their emotion` switch, replaced
  by the per-use order choice (§2.11).
- **`services/pronunciations.py:ROUTE_KINDS`** and the collection-addressed pronunciation route,
  replaced by a kind-addressed one (§2.4).
- Nothing else. There is no earlier lesson implementation to withdraw.

In the other repository, the integration retires **`normalize_lesson_rows`' six-row cap** and the
assumption that a lesson synthesises its own speech. Two things it does not need any more are
adjacent rather than required, and the owner's call: the public Space — stopped upstream — and with
it `deploy/huggingface/`, `build_space_dist.sh`, `cuda_voice.py` and the vendored CUDA runtime, which
between them are why that checkout is 9 GB and its CI takes an hour.

---

## §4 · The steps

### Step 1 · This document

Nothing else starts first.

### Step 2 · The prompt experiment, which gates step 4

`experiments/compose-lesson-line/` — apparatus and write-up in the directory, the decision and a link
here. Amend `prompts/acervo_compose.md` with `lessonGloss` and `lessonEmotion` and a paragraph that
distinguishes the single spoken translation from `shortGloss` and from a sense's gloss `terms`; run it
across the models and a fixed word list; compare sense count, example count, note length and gloss
quality against the current prompt. Record the verdict: keep, or split `acervo_compose.md`
holistically as its own task.

### Step 3 · `lexibeat` becomes a dependency

In that repository, and its own checks pass locally before the tag is pushed.

- `[build-system]`, `[project.scripts]` (`lexibeat`), a wheel, `uv lock`, and a CI job that runs the
  tests on a pull request rather than only on the way to a deploy. Python stays `>=3.12,<3.13`, which
  matches this repository exactly. `local-tts`, `experimental-tts`, `hosted-tts` and `video-demo`
  become extras the core wheel does not pull, so the image installs numpy, scipy, soundfile, librosa,
  pyloudnorm, pedalboard, fastapi and uvicorn and nothing else.
- A versioned `/api/v1` with a checked-in `docs/openapi-v1.json`, `GET /api/v1/health/live`, and a
  `schema` route reporting patterns, families and `production_bundle`.
- `POST /api/v1/lessons` taking supplied audio — `items[{source, target, source_audio, target_audio}]`,
  `pattern`, `family | "auto"`, `seed`, `profile` — answering `{artifact_id, duration_seconds,
  sample_rate, sha256, bed{family, seed, engine_version, fingerprint}, timeline}`, with
  `GET /api/v1/lessons/{artifact_id}/audio` returning a **FLAC** master. Raise the request cap for
  this route, lift the six-item limit, and decide `bars_per_utterance` from the measured audio rather
  than from a caller hint — it has the audio, so nobody else should be guessing.
- One `SuppliedBackend` behind the existing `Backend` Protocol.
- `build_timeline` moves out of `demo.py` into the library and becomes part of the response.
- Emotion leaves the supplied-lesson contract entirely: the direction is already spoken into the clip,
  so the request carries none and `EMOJI_TO_EMOTION` stays a convenience of the Markdown loader.
- The sample bundle published as a release artifact with digests, plus `bundle fetch --into DIR` and
  `bundle verify` subcommands.
- Remove the hardcoded personal vocabulary path in `cli.py` and the external-volume default in
  `library.py`. That repository may be public too, and a home path is a home path.

Then tag, release with `SHA256SUMS`, and write `deploy/acervo/lexibeat/pin.json` here.

### Step 4 · The data model and the prompt

`lessonGloss` and `lessonEmotion` on the lexeme; `lessons` and `lessonItems` as collections ten and
eleven. Server: `src/acervo/db/tables.py` (`REPLICATED`), `src/acervo/domain/projection.py`, the
bootstrap migration, `SCHEMA_VERSION` 11 in `src/acervo/domain/__init__.py`. Client: `domain.ts`
(interfaces, `EntityKind`, `VocabularyGraph`, `PRONUNCIATION_TARGETS`, `validateGraph`),
`localDatabase.ts` (`RECORD_STORES`, database version 6), `repository.ts` (`LOCAL_SCHEMA_VERSION`,
`saveLesson`, the cascade, `baseOf`), `api.ts` (`SCHEMA_VERSION`), `yaml.ts` (`ARTICLE_KEYS` and the
two fields written and read back), `selectors.ts` (the lesson view models, the derived title, the
sampler), and `transfer.ts` — lessons are not exported.

Deploy with `./deploy.sh --reset-database`.

### Step 5 · The speech orders and the two new spoken fields

Rename the two labels in `models/catalogue.json`'s usage and `web/src/ModelPanel.tsx`; add the
per-use Delivery choice to `pronunciation_settings`, `services/pronunciations.py` and
`web/src/PronunciationPanel.tsx`; delete `expressive`. Add `lessonTerm` and `lessonGloss` to
`pronunciation/targets.py`, drop `ROUTE_KINDS`, and move the route to a kind-addressed path.

### Step 6 · The deployment

`deploy/acervo/lexibeat/{pin.json,Dockerfile,entrypoint.sh}`; `scripts/fetch_lexibeat.sh` with
`--check` and `--force`; the portless service, the samples volume and `ACERVO_LEXIBEAT_URL` in
`deploy/acervo/compose.yaml`; the required wheel copy in `scripts/package_acervo_server.sh`; data
dirs, `deployment.env` paths and a health-wait loop in `deploy/acervo/install.sh`; the fetch step in
all three jobs of `.github/workflows/tests.yml` and the Dockerfile in its `multi-arch-build` matrix;
the Dockerfile in `test_server_bundle_contents.py`'s `DOCKERFILES`; the never-deleted-volume and
no-credentials assertions in `test_deployment.py`.

Then fetch the bundle on the NAS and render one lesson by hand, and **set the call timeout from that
measurement** rather than from feel — the 120 seconds this codebase used to carry was a guess, and
`python -m acervo.admin calls` exists so a bound is read rather than invented.

### Step 7 · The pipeline

`src/acervo/lessons/` — the `httpx` client that is the only place the service's wire shape is read,
with its own refusal vocabulary, as `clips/corpus.py` is for the corpus. `services/lessons.py` binds
it to `Settings`, the graph and `ApiError`. `work/lesson.py` registers the kind and joins
`work/kinds.py:_load()`. `api/routes/lessons.py` holds `POST /lessons` (the row, then the job), the
settings pair, and an allow-listed `schema` passthrough — written out, never concatenated.
`api/routes/jobs.py` gains the `lesson` entry in `ENQUEUEABLE`. `pronunciation/encode.py` adds FLAC
to its lossless set, because re-encoding lossless is not a second generation of artifacts — the rule
that forbids it applies to a lossy master. `tests/unit/server/test_layering.py` gains a stands-alone
case and a vacuity assertion for `lessons/`.

If the row is written and queuing the job then fails, the lesson shows as never rendered and Try
again queues it. That is the derived state of §2.6 doing its job.

### Step 8 · The interface

`App.tsx` for the bar and the view switch; `styles.css` for the bar and the player, with
`design/ui-prototype/` changed in the same commit; `LessonView.tsx`, `LessonPlayer.tsx`,
`LessonDialog.tsx` and `lessons.ts`; `mediaStore.ts`'s third kind at database version 3;
`ActivitySettings.tsx`'s `KIND_LABELS` and `RETRYABLE`; `ProgressStrip.tsx`'s `phase()` and
`failureOf()`; a Settings ▸ Lessons page with keep-on-device, the kept byte count and a service
status block modelled on `ClipPanel`'s corpus block.

No component imports its own stylesheet: `scripts/verify_pwa.py` holds the build to one, and the
dynamic-CSS failure it exists to catch killed the macOS application once already.

### Step 9 · Optional, and separately · choosing the words by hand

A selection mode in `LexemeList.tsx` — a Select control in the list header, a tick per row, a count
where the header was, and *Make a lesson* carrying the picks into the same dialog. It calls the same
route with a different list, so there is **no server change at all**. Worth doing when random
sampling starts to feel arbitrary, and not before.

---

## §5 · Verification

```bash
.venv/bin/python -m pytest          # incl. the layering cases and a lessons/ fixture test
npm --prefix web run test
npm --prefix web run build && npm run test:pwa      # the one-stylesheet rule
RUN_DOCKER_INTEGRATION_TESTS=true .venv/bin/python -m pytest tests/integration/test_acervo_server_docker.py
```

The wire shape is checked offline against a recorded response, the way
`tests/unit/clips/test_corpus.py` is, plus one gated live contract test against a running container.
A copy of that service's OpenAPI document is **not** committed here, for the reason
`spoken-clips.md` §5 gives: it would be re-committed on every bump and read by nobody.

**On the NAS, end to end** — `./deploy.sh --reset-database`, create the account, compose two words,
fetch the sample bundle, make a twelve-word lesson from the list, watch the steps in the progress
strip, and time the render before fixing a timeout.

**On the phone, which is the only test that matters** — a lesson plays; the words track the audio;
the screen locks and it keeps playing with lock-screen controls; a kept lesson plays with no
connection; pressing a word's play button stops the lesson instead of overlapping it.

**And the rules still hold** — reordering or deleting a lesson with the server unreachable fails
visibly and changes nothing locally; an export bundle contains no lesson; a word with no
`lessonGloss` is refused by name rather than silently dropped from the track; and nothing, anywhere,
backfills it.
