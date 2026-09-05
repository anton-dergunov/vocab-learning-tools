# Acervo · Sense images

Design for the stage that gives a sense a picture. It refines `acervo-design.md` §09 rather than
replacing it: §09 already decided that image prompts are their own LLM call against the validated
article, that style variety is pedagogical, that a master is 1024×1024 WebP, and that a lexeme with
no image is complete. What was missing was *what the picture is of*, *how the prompt is written*,
and *where the work runs first*. That is this document.

Status: proposal, under review. Nothing here is built yet.

---

## §01 · The one idea

**The image exists to make one word recallable, not to illustrate a sentence.**

Every decision below follows from that. The picture is a mnemonic hook, so the target meaning must
be the loudest thing in the frame; the sentence is the scaffolding that tells the prompt writer what
scene to build, not a specification to reproduce faithfully. A beautiful, accurate picture in which
the word is one small element among many has failed at the only job it has.

Worked pair, from the reference entry:

| Sense | Anchor example | What must dominate |
|---|---|---|
| toxic fluid | *The snake injects venom through its hollow fangs.* | **the venom** — not the snake |
| extreme bitterness | *Her voice was full of venom when she spoke about her rival.* | **the bitterness, made physical** |

The second is the interesting one, and the one that decides whether this feature is worth building.
A prompt writer that renders "a woman looking angry" has produced a picture of *anger*, which the
learner already has a word for. A prompt writer that renders her words leaving her mouth as a thin
green corrosive vapour that blisters the tabletop between them has produced a picture of *venom*.
Externalising the abstraction as a physical presence in the scene is the core technique, and it is
written into the template as an instruction with examples, not left to the model to discover.

---

## §02 · What gets an image

> ### DECISION
> **One image per sense. None per lexeme.**
>
> **Because** the emoji already carries the lexeme-level anchor at zero cost, and a great many
> headwords — `venom`, `anhelar`, `caído` — have no single picture at all, while each of their
> senses does. §03 of the design keeps `senseId: null` for a lexeme-level card image; that shape
> stays in the schema and stays unused. Nothing generates it.

The anchor example, in order of preference:

1. an example whose `origin` is `attestation` — the learner met the word in this sentence, so the
   picture attaches to a memory that already exists;
2. `origin: manual`;
3. the first `llm` example;
4. no example at all — the definition and gloss are enough. Generate anyway. A sense with no example
   is not a signal to skip; it is a signal that the sentence cannot help.

The whole sense goes to the prompt writer — definition, domain, every gloss, every example, and the
lexeme's notes — with the anchor marked. The anchor drives the scene. It does not define it: the
writer may build a different scene when a better one exists for the same meaning, and is told so
explicitly. What it may not do is drift to a *different sense*.

---

## §03 · Two calls, and the batch boundary

```
article (validated, from the graph)
   │
   ├─ 1. prompt writer  ── one LLM text call per LEXEME, covering all its senses
   │        in:  headword, pos, register, language, notes, every sense with its
   │             examples, and a sampled style menu per sense
   │        out: one entry per sense — chosen styleId, anchor example id,
   │             a short scene brief, or a refusal
   │
   └─ 2. renderer       ── one image call per SENSE
            in:  the composed prompt = template + brief + style brief
            out: 1024×1024 WebP master
```

> ### DECISION
> **Batch the prompt writer across the senses of one lexeme, never across lexemes.**
>
> This is §09's rule and it earns its keep here specifically. One call that sees both venom senses
> can deliberately make them look nothing alike — different style, different setting, different
> palette — which is the entire reason per-sense images beat one image per word. Batching across
> lexemes throws that away and makes a retry coarse.

The renderer is per sense because image models take one prompt and return one image.

---

## §04 · What is stored

> ### DECISION
> **`imagePrompt.prompt` stores the short scene brief. The full prompt sent to the image model is
> composed, not stored.**
>
> The full prompt is a pure function of things already recorded: `prompt` (the brief) + `styleId`
> (names a row in the tracked style table) + `promptVersion` (checksum of the tracked template).
> Storing it as well would store the same text twice and put a wall of instruction text in the
> article view, where the field is already rendered. This is exactly how `image_benchmark/jobs.py`
> already composes `f"{brief}. {style.suffix}"`, so there is one idea here, not a new one.
>
> The cost is honest and small: change a style's wording and yesterday's image is no longer
> byte-reproducible. `styleId` and `promptVersion` record that it changed, and §01 of the design
> already says images are regenerable. Reproducing the *file* was never the point; reproducing the
> *intent* is, and the brief carries that.

The brief is one or two sentences, written for a person to read: *"A viper's fangs sunk into a bare
forearm, a single luminous chartreuse droplet swelling at the fang tip and beading down, the snake
itself dim and out of focus behind it."* That is what the article view shows and what a "regenerate
this one, but…" flow will let you edit.

Existing fields, used as follows:

| Field | Value |
|---|---|
| `lexemeId` | the lexeme |
| `senseId` | the sense — always set |
| `prompt` | the scene brief |
| `styleId` | the style the writer chose from the menu |
| `seed` | derived from `senseId`, so a regeneration keeps the look |
| `modelId` | the model that wrote the brief |
| `promptVersion` | checksum of `prompts/acervo_image_brief.txt` + the style table |
| `imageRef` | relative path to the master, once drawn; null until then |
| `imageModelId` | the model that drew it |

§09 says to seed from `lexemeId`. Per-sense images make `senseId` the right stable key — two senses
of one word seeded identically would fight the variety the whole design is built on.

### The gap: nothing records a failure

`imageRef: null` currently means both "written, not yet drawn" and "drawing was refused or failed".
A sweep defined as *"which senses lack an image"* therefore retries a permanently blocked sense
forever. Two fields close it, and they are the only schema change this design needs:

| Field | Type | Notes |
|---|---|---|
| `attempts` | int | Drawing attempts made. The sweep skips a row past a threshold. |
| `failureReason` | string? | Last refusal or error, in the provider's words. Null on success. |

> **This change requires `--reset-pocketbase`, which destroys the database.** It must not happen
> until the current ingestion has finished and a transfer bundle of the real vocabulary exists.
> See §10.

---

## §05 · Styles

A style is content, not code: `config/image-styles.yaml`, one row per style, loaded the way the
dictionary catalogue is. Each row carries an `id`, a `label` for the settings screen, a `brief`
spliced into the image prompt, a default `weight`, and a `mono` flag where the style is
monochrome — a monochrome style can quietly destroy a meaning that depends on colour, and the
prompt writer is told to avoid one when it does.

Deliberately absent from every one of these: *flat*, *schematic*, *simple shapes*, *silhouette*,
*icon*, *minimal*, *readable at small size*. The finalist benchmark's `warm_compact_scene` suffix
asks for "silhouettes that remain readable after reduction to 192 pixels" and its own report flags
that wording as a mistake. It is not carried forward. These images are looked at on a tablet at
roughly the size of a photo in a feed, and they should be worth looking at.

| id | Label | mono |
|---|---|---|
| `cinematic-photoreal` | Cinematic photograph | |
| `golden-hour` | Golden-hour photography | |
| `oil-painting` | Oil on canvas | |
| `baroque-chiaroscuro` | Baroque chiaroscuro | |
| `watercolour-storybook` | Watercolour storybook | |
| `gouache-poster` | Mid-century gouache poster | |
| `art-nouveau` | Art nouveau | |
| `ukiyo-e` | Japanese woodblock | |
| `anime-cel` | Anime cel | |
| `manga-panel` | Manga panel | ✓ |
| `comic-book` | Comic-book ink and halftone | |
| `pixar-3d` | 3D animated feature | |
| `claymation` | Stop-motion clay | |
| `papercraft-diorama` | Cut-paper diorama | |
| `retro-futurism` | 1970s sci-fi paperback | |
| `film-noir` | Film noir | ✓ |
| `surrealism` | Surrealist dream logic | |
| `vintage-botanical` | 19th-century engraved plate | |
| `constructivist-poster` | Constructivist poster | |
| `neon-cyberpunk` | Neon night, cyberpunk | |
| `pixel-art` | 16-bit pixel art | |
| `charcoal-sketch` | Charcoal on toned paper | ✓ |
| `stained-glass` | Stained glass | |
| `folk-naive` | Naïve folk painting | |

Twenty-four, and the file is meant to be edited. Each `brief` is a full sentence of art direction,
not a label — `oil-painting` becomes *"thick impasto oil on canvas, visible brushwork, deep varnish
tones, old-master lighting"*.

> ### DECISION
> **Sample three styles per sense, ranked, and let the prompt writer pick one of the three. It may
> not invent a fourth.**
>
> **Because** a real style sometimes cannot express a real meaning — `vintage-botanical` has nothing
> to say about *bitterness*, and forcing it produces the bad image. Giving the writer an escape
> hatch costs one sentence of instruction. Letting it *invent* a style, though, breaks the record:
> an invented style has no id, so `styleId` stops naming anything and the look is not reproducible.
> Instead, every menu includes `cinematic-photoreal` as its last entry, which can express anything.
> The writer must return the id it picked.

Sampling is weighted random without replacement, seeded from `senseId`, so re-running the sweep
proposes the same menu and the whole stage is idempotent. Within one lexeme the writer is told not
to pick the same style twice.

**Weights are per owner.** For the local phase they live in the run's config file. Where they live
in the product is deferred — see §11 — but not on the device: generation runs on the server, so the
weights have to be server state, unlike the editor's wrapping preference.

---

## §06 · The prompt template

`prompts/acervo_image_brief.txt`, tracked text, read at request time — content, not code, the same
rule as `acervo_compose.txt`. Sketch of what it must say:

**The job.** You are writing a scene brief for an image model. The picture is a memory hook for one
word in one meaning. A learner who does not know the word should be able to look at the picture and
guess the meaning.

**The accent rule.** Name the one thing that must dominate the frame, and make the whole scene point
at it — scale, composition, light, focus, colour contrast. Everything else is subordinate and simple
enough not to compete. The target meaning is never one detail among equals.

**Exaggerate.** Theatrical, dramatic, physically impossible if it helps. This is expected, not
tolerated. A picture that is merely accurate is a worse mnemonic than one that is memorable.

**Abstractions get bodies.** When the meaning is not a thing you can photograph — bitterness,
longing, disgrace — give it a physical presence in the scene: a substance, a light, a weight, a
deformation of the space around it. Two worked examples ship in the template, both for *venom*.

**Never render text.** No letters, captions, signage, labels, logos, watermarks, pseudo-text — and
above all never the vocabulary word. A flashcard with the answer written on it is broken.

**Say what you chose.** Return the styleId, the anchor example, the brief, and nothing else.

### Forbidden, and the line

Refuse rather than produce: hate insignia of any kind, Nazi and SS symbols above all; sexualised
imagery; exposed genitals or breasts; nudity; any depiction of a child in an unsafe or suggestive
context; graphic gore; desecration of religious symbols where the word is not itself about them;
identifiable real people; real brand marks.

Permitted, and this half matters as much: rage, contempt, disgust, fear, grief, drunkenness, insult,
threat, vulgar register, implied violence. `atrocity`, `boludo`, `dumb`, `snake bites man` all get
pictures. The line the template draws is **depict the emotion or the situation, not the anatomy and
not the atrocity in graphic detail**. A safety rule that quietly refuses half of a learner's real
vocabulary is a broken feature, not a cautious one.

> ### DECISION
> **A refusal is a successful outcome, and it is not retried.**
>
> §09 already says `none` is a success. The writer returns `refused: true` with a one-line reason,
> no `imagePrompt` row is created, and the sweep does not come back for it. A provider-side block
> at drawing time is different: the row exists, `attempts` increments, `failureReason` records the
> provider's words, and the sweep gives up after a threshold.

---

## §07 · Output format

Master: **1024×1024 WebP, quality ~88**, from Gemini's 1K PNG output. This is §09's decision
unchanged. Square because both consumers — the article fold and an Anki card — want square, and
because it is the model's native output so nothing is upscaled or thrown away. Easy to revisit; it
is one line of config.

Derive variants from the master, never generate twice: 768 for Anki if deck size bites, 256 for a
list thumbnail.

---

## §08 · Where images live

> ### DECISION
> **A static media directory served the way compiled dictionaries are, with `imageRef` holding a
> relative path.**
>
> `imageRef` is already a 500-character text field, not a PocketBase file field, so the schema
> assumed this. `main.pb.js` already mounts `ACERVO_DICTIONARIES_PATH` at
> `/api/acervo/dictionaries/{path...}` behind `requireAuth`, outside `pb_public` so the service
> worker never tries to download it; `ACERVO_MEDIA_PATH` at `/api/acervo/media/{path...}` is the
> same pattern with a different directory. It keeps the database small, it byte-ranges, and
> `package_acervo_server.sh` and `install.sh` already know how to carry a data directory.

Path shape: `images/<lexemeId>/<imagePromptId>.webp`. Content-addressed by the record that owns it,
so a regeneration overwrites in place and nothing accumulates orphans.

Two consequences to note now and handle in the display phase:

- **The route needs auth, so `<img src>` cannot fetch it directly.** The client will need to fetch
  with the token and hand the element a blob URL — exactly what the dictionary reader already does.
- **Offline-first reads apply to images too.** The natural home is a third IndexedDB database
  alongside `dictionaryStore.ts`, holding whole files as Blobs, deliberately separate from the
  replica so neither wipe touches the other. Not in the replica: per-record overhead and a wipe on
  account change are both wrong for megabytes of pictures.

**The transfer bundle carries the reference, not the bytes.** `imagePrompts` round-trip through the
YAML projection already, so `prompt`, `styleId`, `seed` and `imageRef` survive an export/import; the
WebP files do not. That is the right call — a bundle should stay a text archive you can read — and
it means the media directory is a separate backup concern under §17, alongside PocketBase's data
directory. Images are regenerable by design; the briefs that produced them are what must not be lost,
and those are in the bundle.

---

## §09 · Where the work runs

### It is a sweep, not a watcher

You described a background service that monitors for new articles. The design's existing rule is
sharper and I would keep it: **derive the work from a query, never from a queue.** "Which senses
have no live `imagePrompt` with an `imageRef`" is a `SELECT`, so a lost event cannot lose work, the
worker being down for a week costs latency and nothing else, and every run is idempotent by
construction.

It is also not a service in this repo's sense. `acervo-worker` is one-shot by design —
`profiles: ["tools"]`, no ports, `docker compose run --rm`, exit — and AGENTS.md is explicit that a
new job is a new *subcommand*, never a new compose service. So:

```bash
docker compose -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker \
  images sweep --owner learner@account.example.com --limit 200
```

driven by cron or a timer. Nothing runs continuously.

### But not first

> ### DECISION
> **Phase A runs entirely on the laptop, reads the graph read-only, and writes only to the local
> filesystem.**
>
> Three reasons, in order. The prompt is going to need several rounds of iteration and a local run
> is a thirty-second edit-and-see loop. The Vertex credits expire in a week or two and the server
> path is at least a schema change and a deploy away. And the ingestion of ~1,500 real entries is
> running right now against that same server — a read-only local script cannot disturb it.

Phase A is not throwaway. **It mints the real 15-character `imagePrompt` ids offline**, which is
what the ID rule already requires of every client, and writes the files under their final names. The
import in Phase B is then a plain write of rows that already know their ids, pointing at files
already sitting at their final paths.

---

## §10 · Phases

| | What | Touches the server | Blocked by |
|---|---|---|---|
| **A** | Local generation: brief writer, style sampling, renderer, contact sheet | reads only | nothing |
| **B** | One-off import of the run into the graph and the media directory | writes | A reviewed and accepted |
| **C** | `acervo-worker images sweep`, plus `attempts` / `failureReason` | writes, schema | **a transfer bundle of the real vocabulary must exist first** |
| **D** | Article view: render, regenerate, delete; style weights in Settings | | C |
| **E** | Anki cards, one per example, with the sense image | | D and the Anki generator, which does not exist |

The ordering constraint that matters: **C requires `--reset-pocketbase`, which destroys the
database.** The sequence is finish ingesting → export a bundle → verify the bundle imports into a
throwaway database → only then change the schema. Nothing about the image work justifies risking
1,500 hand-collected entries.

### Phase A, concretely

New code, all in new files, so nothing the running ingestion imports is touched:

```
config/image-styles.yaml           the style table
prompts/acervo_image_brief.txt     the brief-writing template
src/vocabgen/images/styles.py      load the table, weighted sample seeded from senseId
src/vocabgen/images/brief.py       build the LLM request, parse and validate the reply
src/vocabgen/images/compose.py     brief + style + template -> the image prompt
src/vocabgen/images/render.py      Vertex Gemini 3.1 Flash Lite Image -> WebP master
src/vocabgen/images/run.py         plan, execute concurrently, checkpoint, manifest
scripts/generate_images.py         plan | run | sheet
```

`google-genai` is already a pinned dependency, so the renderer is a direct call, not the benchmark's
`uv run --no-project` subprocess. The graph is pulled read-only through `GET /api/acervo/v1/graph`,
the same cursor route the app uses, authenticated the way the ingest script authenticates.

Output under `output/images/<runId>/`: a `manifest.json`, one `<imagePromptId>.json` per job holding
the brief, the composed prompt, the style, the seed, the models, timings and cost, and one
`<imagePromptId>.webp` beside it. Jobs are keyed by id and skipped if already complete, so a run is
resumable and a re-run is free.

`sheet` writes one self-contained HTML page — word, sense, gloss, anchor example, chosen style,
brief, image — sized for reading on a tablet, with accept/reject writing a decisions file. That
file is what Phase B imports, and what tells us which prompt revision to make next.

The review ladder you asked for: **10 → 50 → 100 → the rest**, with the template edited between
each. `--limit` and a `--only` selector cover it.

### Budget and wall clock

The finalist report measures Gemini 3.1 Flash Lite Image at **$0.0336 per image and 16.3 s mean**.
Against the ingestion in flight:

| | |
|---|---|
| Lexemes, once ingestion finishes | ~1,500 |
| Senses per lexeme, assumed | ~2.3 |
| Images | **~3,450** |
| Image spend | **~$116** |
| Brief-writing calls | ~1,500 text calls, small next to the above |
| Serial wall clock | **~15.6 hours** |
| At 6 concurrent | **~2.6 hours** |

Concurrency is the thing to get right, not cost. Serial generation does not fit in an overnight run
comfortably; six concurrent workers does, with room for retries. The rate limiter and retry policy
already in `src/vocabgen/provider/` cover the Vertex quota side.

---

## §11 · Open questions

1. **Brief or full prompt in `prompt`?** I recommend the brief (§04). Say if you would rather have
   the exact bytes stored and accept the article view showing a wall of text.
2. **Every sense, or a subset?** Every sense is ~3,450 images and ~$116. Capping at the first three
   senses of a lexeme, or skipping `archived` lexemes, would cut it materially. My instinct is to
   generate everything while the credits exist and prune later, because the credits are the scarce
   thing — but it is your budget.
3. **Menu of three, or one forced style?** I recommend three with a guaranteed-expressive fallback
   (§05).
4. **Where do per-owner style weights live?** Deferred to Phase D. It needs server-side owner state
   and there is no preferences collection yet; `sync_state` is exempt from replication and is the
   wrong place. Worth deciding before D, not before A.
5. **1:1, or 4:3?** Square by default. If the article view wants a wide image, now is the cheap time
   to say so — regenerating later costs the credits twice.
6. **`attempts` / `failureReason` (§04)** — agreed as the one schema change, or would you rather the
   worker keep failure state locally and leave the schema alone?
7. **Are the generated images backed up anywhere?** They are regenerable in principle, but not once
   the Vertex credits are gone. If the answer is "restic over the media directory", that should be
   arranged before the overnight run, not after.
8. **How much of the remaining credit is this allowed to spend?** Everything above assumes one full
   pass plus a margin for regenerating rejects.

---

## §12 · What this deliberately does not do

- No lexeme-level card images.
- No local diffusion fallback yet. §09's provider chain stands as the plan; Phase A hardcodes
  Vertex, because the point of Phase A is to spend expiring credits, and Cloudflare FLUX.2 Klein 4B
  is the documented successor when they run out.
- No automatic quality gate. The benchmark report sketches one — luminance and colour variance,
  entropy, edge density, dominant-colour share — and Gemini's 0/12 rejection rate does not justify
  building it. It becomes interesting when generation moves to a less reliable model.
- No regenerate-with-a-note flow. Phase D.
- No Anki anything. Phase E, and the Anki generator does not exist yet.
