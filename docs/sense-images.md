# Acervo · Sense images

Design for the stage that gives a sense a picture. It refines `design.md` §09 rather than
replacing it: §09 already decided that image prompts are their own LLM call against the validated
article, that style variety is pedagogical, that a master is 1024×1024 WebP, and that a lexeme with
no image is complete. What was missing was *what the picture is of*, *how the prompt is written*,
and *where the work runs first*. That is this document.

Status: **In the product.** Pictures are drawn on the server and shown in the article.
`src/acervo/images/` is the pipeline — a brief writer and a renderer, standing alone on
`src/acervo/models/` so that a job and a laptop run can share it; `src/acervo/services/images.py`
binds it to Acervo; `src/acervo/work/enrich.py` draws for a word that was just saved and
`src/acervo/work/images.py` for a redraw or a new brief somebody asked for
([`plans/processing-flow.md`](plans/processing-flow.md) revises §09 below). `api/routes/images.py`
keeps what a person does directly: the settings, the readout, attaching your own picture, and ruling
a sense out.

**What has not happened is landing the 2,285 pictures drawn on the laptop**, and the reason is an
accident of history rather than anything about the design. Their `senseId`s were read from the
pre-port database. The vocabulary has since been exported and re-imported, and `transfer.ts` mints
fresh ids on import — a bundle carries no sense ids at all — so every `senseId` in those run
directories names a sense nobody holds. Because `image_prompt_id` is *derived from* `senseId`, all
2,285 filenames are wrong for the current database too. `verify` cannot see this: a run directory is
internally consistent either way, and it will keep reporting "safe to import". `publish` does see
it, refuses the whole run, and says which records are stranded.

`scripts/rekey_image_runs.py` is the matching step, keyed on what survived the round trip — language,
headword, and the sense's order within the word, all three of which the run records carry — after
which every id, filename and `imageRef` is re-derived — the reference from the bytes it copies, so a
run drawn before references carried a digest gets a correct one rather than its old name rewritten. It writes a new run directory and never edits
the one it read, and it refuses a word it cannot match rather than guessing, because a picture landing
on the wrong sense is worse than a missing one. It is a throwaway with no second use; the prompt
iteration that produced the images is in `experiments/sense-images/`.

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
| `seed` | derived from `senseId`, so a regeneration keeps the look — on a row whose `capabilities.image.seed` is `native`; see below |
| `modelId` | the model that *answered* the brief call, not the one asked first |
| `promptVersion` | checksum of `prompts/acervo_image_brief.md` + the style table |
| `imageRef` | relative path to the master, carrying a digest of its bytes, once drawn; null until then |
| `imageModelId` | the model that *drew* it, which under a chain need not be the first tried |

§09 says to seed from `lexemeId`, which was right when the plan was one image per word: the seed's
job is to keep a word looking like itself across regenerations. Per-sense images make `senseId` the
right stable key instead. Seeding both senses of `venom` from the lexeme would hand the same
starting noise to two pictures that the whole design is trying to make look different — same key,
same tendencies. The property §09 wanted survives: a sense keeps its look across regenerations,
because the key is stable. The retry counter is mixed in, so deleting a picture you disliked and
running again gives you a genuinely different one rather than the same picture back.

### A seed is only a seed where the provider takes one

Now that the picture is drawn through the catalogue, the row says whether it honours a seed.
Cloudflare does. Vertex does not — LiteLLM's transformer never puts one in the request — and OpenAI
rejects the parameter outright, so both rows declare `capabilities.image.seed: "ignored"` and the
answer comes back carrying a warning, which the record keeps under `run.usage.warnings`. The seed is
still stored, because it is what a re-run derives, but on those rows "a regeneration keeps the look"
is not true and the record says so rather than implying otherwise. Resolution is the same shape of
fact: Vertex takes an aspect ratio and its own size name, so the row carries
`params.image.imageConfig` and declares `size: "fixed"`.

### The gap that is now closed: what an undrawn record means

`imageRef: null` used to mean three things at once — "written, not yet drawn", "drawing was refused",
and "the owner does not want one here" — so work defined as *"which senses lack a picture"*
retried a permanently blocked sense forever and could not be told to stop. Three columns close it,
and every other state derives from them rather than being named:

| Field | Type | Notes |
|---|---|---|
| `attempts` | int | Render calls spent. Past a threshold nothing draws the row on its own again. |
| `failureReason` | string? | The last refusal, in the provider's words. Null on success. |
| `suppressed` | bool | The owner has ruled on this sense. Nothing ever regenerates it. |

*ready* = `imageRef` set · *pending* = empty with no attempts · *failed* = empty with a reason ·
*terminal* = failed at or past `MAX_ATTEMPTS`, which lives in `services/images.py` and not in the
record. That split is what keeps `attempts` a count: the row says what happened, the threshold says
what to do about it, and only the first of those is data.

> ### DECISION
> **An image prompt's id is derived from its `senseId`, in *every* writer.**
>
> `image_prompt_id(senseId)` — base-36 of a namespaced SHA-256 — exists in
> `src/acervo/images/ids.py` and in `web/src/ids.ts`, and the two are pinned against the same
> vectors from both sides. It is what makes two engines converge on one row with no coordination,
> what makes `suppressed` possible instead of a tombstone, and what limits a sense to one picture
> without a database constraint.
>
> It cost a bug to learn that "every writer" means the interface too. `saveArticle` minted a random
> id, so importing a bundle wrote the document's row under one id and the restored picture's under
> the derived one: the sense showed an empty frame carrying the brief *and* a picture carrying none,
> and clicking either gave the wrong half. Nothing failed — it just looked like a duplicate. Hence
> the derivation on both sides, and `articleFor` keeping one picture per sense as well, for replicas
> the older code already wrote.

> ### DECISION
> **`suppressed` is not a tombstone, and could not be.**
>
> An image prompt's id is *derived* from its `senseId`. A tombstoned row is invisible to enrichment,
> which re-briefs the sense and mints **the same id** — so tombstoning does not prevent
> regeneration, it guarantees a collision at a higher revision. The row has to stay, visible, saying
> the owner ruled on this sense.
>
> The same derivation is what makes two engines safe with no coordination whatsoever: the interface
> and the sweep converge on one row, and whichever arrives second finds the work done or is refused
> as stale.

A provider that looks at the prompt and declines is terminal for that wording: `attempts`
increments, `failureReason` records what it said, and it is deliberately **not** suppressed —
a different brief may well pass, which is what the edit-and-draw flow is for. A writer refusal *is*
suppressed, because that is a judgement about the sense rather than about a wording, and it becomes
a row with no brief so that nothing briefs the sense again. A rate limit is neither: nothing is recorded
against the sense, because an allowance running out says nothing about it and must not spend one of
its retries. A refused *credential* stops the run, since falling through would hide a mistake and
spend somebody else's allowance on it.

### Where the images already drawn will land

There are roughly 2,285 pictures in `output/images/` and `output/images-en/`, and §00 explains why
they cannot be published as they stand: their `senseId`s name senses nobody holds any more, and
`image_prompt_id` is derived from `senseId`, so every filename is wrong too.

Landing them is `scripts/rekey_image_runs.py`, a throwaway outside the pipeline. It keys on what
survived the export and re-import — language, headword and the sense's *order* within the word — and
uses the definition as a **check** on that key rather than as part of it, because a picture landing
on the wrong sense of the right word is the quiet failure worth spending a comparison on. All 2,286
records carry those four fields and no two of them collide, so the key resolves for every one.
`imageModelId` records the Vertex model that actually drew each one, which is a fact about the past
and is not re-derived from whatever the chain says today. `verify` cannot detect the mismatch,
because a run directory is internally consistent either way; `publish` can, and refuses the whole
run rather than writing half of it.

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
| `cinematic-photoreal` | Cinematic photograph |  |
| `golden-hour` | Golden-hour photography |  |
| `oil-painting` | Oil on canvas |  |
| `baroque-chiaroscuro` | Baroque chiaroscuro |  |
| `watercolour-storybook` | Watercolour storybook |  |
| `gouache-poster` | Mid-century gouache poster |  |
| `art-nouveau` | Art nouveau |  |
| `ukiyo-e` | Japanese woodblock |  |
| `anime-cel` | Anime cel |  |
| `manga-panel` | Manga panel | ✓ |
| `comic-book` | Comic-book ink and halftone |  |
| `pixar-3d` | 3D animated feature |  |
| `claymation` | Stop-motion clay |  |
| `papercraft-diorama` | Cut-paper diorama |  |
| `retro-futurism` | Retro-futurism |  |
| `film-noir` | Film noir | ✓ |
| `surrealism` | Surrealist dream logic |  |
| `vintage-botanical` | 19th-century engraved plate |  |
| `constructivist-poster` | Constructivist poster |  |
| `neon-cyberpunk` | Neon night |  |
| `pixel-art` | 16-bit pixel art |  |
| `charcoal-sketch` | Charcoal on toned paper | ✓ |
| `folk-naive` | Naïve folk painting |  |

Twenty-three, and the file is meant to be edited. `stained-glass` was one of them until round 1,
where leaded glass kept dragging every scene into a church; removing a style is editing the file,
which is the point of it being a file. Each `brief` is a full sentence of art direction,
not a label — `oil-painting` becomes *"thick impasto oil on canvas, visible brushwork, deep varnish
tones, old-master lighting"*.

> ### DECISION
> **Offer the writer every style the owner has left switched on, and let it pick. It may not invent
> one that is not on the menu.**
>
> **Because** a real style sometimes cannot express a real meaning — `vintage-botanical` has nothing
> to say about *bitterness*, and forcing it produces the bad image. The writer needs room to pass
> over a style that cannot carry the sense. Letting it *invent* one, though, breaks the record: an
> invented style has no id, so `styleId` stops naming anything and the look is not reproducible.
> The writer must return an id from its own menu, and `parse_reply` rejects the reply if it does
> not — an off-menu style is an error, not a nudge.

This replaces the sampled three-style menu, which round 1 abandoned, and the reason is worth keeping
because it is the opposite of what it looks like. With a menu of three the style is **assigned, not
chosen**: the scene gets written to fit whatever arrived at random, and the writer argues with a dice
roll instead of reading the sense. It shows up in the numbers — `baroque-chiaroscuro` drew three of
that round's fourteen images and *three of its seven rejections*, because a period style drags the
scene into its period and an architectural one into its architecture, neither of which the sentence
asked for. Random assignment buys variety at the cost of meaning, which is the wrong trade for the
only thing the picture is for.

Round 2 then found what the short menu had been hiding: **position bias**. Offered the table in file
order, the writer read the first row, `cinematic-photoreal`, as the default. The fix was not to
shorten the menu again but to turn it — `StyleTable.offer(rotate=lexemeId)` rotates by a stable
amount derived from the lexeme, which removes the anchor without taking the choice away and stays
idempotent on a re-run. Within one lexeme the writer is told not to pick the same style twice.

`cinematic-photoreal` still has a role, but it is no longer a reserved slot: photorealism is the one
register that can carry any meaning at all — an abstraction, a thing you can photograph, a joke, a
threat — so it is where the writer lands when nothing else suits. The template says so in as many
words, and it carries the same weight as every other row.

### What the owner controls

Two settings, and deliberately not a third. Rounds 1–7 tried weights, a sampled three-style menu, and
per-style applicability hints; what survived is that the owner should say *which styles exist for
them* and *how adventurously to choose among them*, and nothing finer.

Both map onto parameters the code already takes, which is why the settings screen adds no mechanism:
a style switched off is a weight of zero in `StyleTable.offer(weights)`, and *boost variety* is
`StyleTable.hints()` on or off. They are stored as the **off** list rather than the on list, for the
reason the dictionary switches record — a set of switched-*on* ids leaves anything added later
permanently silent, so a style added to `config/image-styles.yaml` must be on by default.

| Control | Shape | Default |
|---|---|---|
| **Draw pictures** | one switch, and it governs everything that draws *by itself* — the `enrich` job of a word that was just saved, and a backfill. It deliberately does not gate the per-sense buttons: switching it off is how you get a word with no pictures and then add the one you want by hand. Checked by the two drivers rather than by the routes, for that reason. | on |
| **The styles** | one switch per style, on or off. A style switched off is never offered. At least one must stay on — with none there is nothing to draw with, and "draw nothing" is the switch above rather than an empty list. | all on |
| **Boost variety** | one switch. On, each style is presented with a few of its example subjects, sampled per word, which pushes the writer toward styles it would otherwise pass over. Off, styles are offered on their own descriptions alone. | **on** |

No per-style weight, no sampling temperature. A weight is a number nobody can set meaningfully
without running a few hundred images and counting, which is what the histogram in
`experiments/sense-images/` is for and not what a settings screen is for.

**Boost variety defaults to on** because both modes were reviewed and both produce good pictures.
Round 6 (off) was judged *"on point, and not uniform"*; round 7 (on) was judged less predictable and
equally apt, with two styles appearing that had never been chosen in 300 images. On is the more
interesting of two good options, and the switch exists because the distinction is genuinely a matter
of taste rather than of correctness.

**These are per owner, and therefore server state.** Generation runs on the server, so unlike the
editor's wrapping preference they cannot live on the device. They live in `image_settings`, an
owner-scoped table that is never replicated — the same shape and the same three-state doctrine as
`model_selection`, where **no row means "follow the deployment default"** rather than meaning a gap.

---

## §06 · The prompt template

`prompts/acervo_image_brief.md`, tracked text, read at request time — content, not code, the same
rule as `acervo_compose.md`. Sketch of what it must say:

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
> no `imagePrompt` row is created, and nothing comes back for it. A provider-side block at drawing
> time is different: the row exists, `attempts` increments, `failureReason` records the provider's
> words, and drawing on its own gives up after a threshold.

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

Path shape: `images/<lexemeId>/<imagePromptId>-<digest8>.webp`, addressed by the record that owns it
**and by the bytes it holds** — a truncated SHA-256 of the stored master, the way a pronunciation's
file name is. A regeneration is therefore a new name, and the file the row used to name is removed
once the row naming its successor has landed; at most one picture per sense is kept.

The digest is not decoration. A device caches a picture under its reference, so a name that stayed
the same across a redraw meant the device went on showing the picture that had just been replaced,
and the invalidation bolted on beside it raced a `revision` frame it could not beat. With the bytes
in the name there is nothing to invalidate: the new picture is asked for under a name nothing has
ever held. Nothing parses this string — it is built in `images/ids.py`, stored, joined onto the media
directory and unlinked — so a reference written before the digest existed still names its file.

Two consequences, both now handled:

- **The route needs auth, so `<img src>` cannot fetch it directly.** `web/src/media.ts` fetches with
  the token and hands the element a blob URL — exactly what the dictionary reader already does.
  `LexemeArticle.tsx` used to put `imageRef` straight in a `src`, which is why it had never once
  displayed a picture.
- **Offline-first reads apply to pictures too.** `web/src/mediaStore.ts` is a **third** IndexedDB
  database alongside `dictionaryStore.ts`, holding whole files as Blobs and deliberately separate
  from the replica so neither wipe touches the other. Not in the replica: per-record overhead and a
  wipe on account change are both wrong for megabytes of pictures.
- **The server's media volume is read-write**, unlike the dictionaries beside it. That asymmetry
  used to be one fact and is now two: a dictionary is compiled only by the worker, so the server has
  no reason to hold a pen, while a picture is drawn by whichever of the two was asked and the file
  and the row naming it must be written by the same party.

**The transfer bundle carries the reference by default, and the bytes when asked.** `imagePrompts`
round-trip through the YAML projection, so `prompt`, `styleId` and `seed` survive an export/import.
`imageRef` and `imageModelId` deliberately do **not**: they are facts about the server that drew the
picture, and `imageRef` embeds a lexeme id that will not exist after import — keeping it imported a
live-looking reference to a file nobody has.

The bytes are an opt-in `media/<language>/<slug>-<n>.webp` directory. Named after the word file so
the two pair by eye, and suffixed by sense order rather than by prompt id, because a bundle carries
no ids a person or a second account could use — which also makes position the only pairing a restore
can key on. It defaults to off: a bundle should stay a text archive you can read, pictures are
regenerable by design, and the briefs that produced them are in the word file either way. It is the
one export that is not offline-capable, which the panel says plainly.

> ### DECISION
> **The import puts the pictures back, through the same route that attaches one by hand.**
>
> This was first built export-only, by analogy with the Obsidian mirror under `markdown/`, on the
> reasoning that reading the bytes would grow a second writer beside `repository.saveArticle`. That
> was wrong, and the round trip proved it: exporting with pictures and importing into a rebuilt
> database gave every sense its brief and *"Not drawn yet"*, which is an archive rather than a
> backup — and a backup is what the export is for.
>
> It is not a second writer, because a picture is not a graph record. `saveArticle` writes the word,
> and then each picture goes to `PUT /images/senses/{senseId}/picture` — the route a person uses to
> attach one. One pipeline, two callers, exactly as with capture.
>
> `transfer.ts` still holds no transport: it *names* the pictures and takes a callback, and
> `TransferPanel.tsx` supplies it along with the zip, because owning the zip and the browser's file
> handling is already its job.

What travels with the bytes is `imageModelId`, and the distinction is the point. `imageRef` is a
path on the server, embedding a lexeme id that will not exist after import, so it is stripped —
keeping it imported a live-looking reference to a file nobody has. `imageModelId` is not a path: it
is the name of the model that drew this picture, a fact about the past exactly as an example's
`origin` and `modelId` are. Provenance travels in a bundle; server paths do not.

That is also what tells a **restore** from a picture the owner chose, on one route. Naming the model
means the row keeps its provenance and stays replaceable; naming none means the owner picked this
file, so `imageModelId` is empty — the way an example the learner wrote carries no `modelId` — and
the row is `suppressed`, because choosing a picture is choosing it. Without that distinction every
restored picture would read as hand-chosen, and nothing would ever redraw two thousand of them.

The import **pulls** after restoring — in batches, and once at the end — and that is not an
optimisation. A word reaches the replica by itself, because `saveArticle` merges what the server
answers; a picture does not, because the image route wrote it. Without the pull an imported article
showed empty frames and a "waiting" count until the next scheduled sync came round up to a minute
later, which reads as a failed import rather than a lagging one.

A picture that cannot be put back is reported and its word is kept: the words are the part that
cannot be regenerated. And a word the import skips as already held keeps its own picture, for the
same reason it keeps its own text — an import must never cost you what you did after the export.

---

## §09 · Where the work runs

### It is a sweep, not a watcher

**§09 REVISED — the work starts from the write, and there is no sweep.**
[`plans/processing-flow.md`](plans/processing-flow.md) replaces the two engines below with one: a
save queues an `enrich` job in the same transaction as the word, and `src/acervo/work/` runs it in
the server. The half of the rule that mattered is kept — each step still asks the graph what the word
lacks, so a job run twice draws nothing — while the half that cost is gone: the interface carries no
pipeline, a word added by a script is drawn like any other, and no picture waits on a timer nobody
can see. A redraw and a new brief are jobs too, so leaving the word does not lose them.

You described a background service that monitors for new articles. The design's existing rule is
sharper and it is the one that was kept: **derive the work from a query, never from a queue.** "Which
senses have no live `imagePrompt` with an `imageRef`" is a `SELECT` on the server and a filter on the
replica, so a lost event cannot lose work, the worker being down for a week costs latency and nothing
else, and every run is idempotent by construction.

### Two engines, one pipeline, and the unit is one model call

> ### DECISION
> **The interface enriches the word you just saved. Everything else is the server's sweep. Neither
> is a queue, and they need no coordination at all.**
>
> **Because** the two have different jobs. You are looking at the word you just added, and a picture
> in a minute beats a picture in five — so `web/src/enrichment.ts` asks for it straight away, one
> unit at a time, with the progress in view. But 2,285 senses at roughly one picture a minute is
> thirty-three hours, and a backgrounded browser tab freezes its timers and drops its fetches within
> minutes; a client loop cannot be the answer to "give my whole vocabulary pictures", and it is not
> at a tablet at all when the ingest script adds a word. That is `acervo-worker images sweep`, on a
> timer.
>
> What makes this safe rather than a race is that **an image prompt's id is derived from its
> `senseId`**. Both engines compute the same id for the same sense, so the second one to arrive finds
> the work already done or is refused as a stale revision. There is nothing to lock and nothing to
> claim.
>
> And do **not** try to share a rate limit between them. `acervo.models.pacing` is process-local and
> the worker is a different container; the chain's fall-through plus a backoff on exactly the three
> transient codes *is* the pacing. A cross-process limiter would be inventing a problem.

*(Superseded, as above.)* The interface deliberately does **not** sweep the backlog on open, and the
server deliberately runs no daemon. Both were considered and both are worse: a tablet working through two thousand pictures
is not a tablet you can read on, and an in-process background task dies on every deploy, makes the
process that must stay responsive into the orchestrator, and needs a job store — which would be
owner-scoped domain data and would therefore replicate to every device, so a phone would carry a
queue of work it can never do. That is the question `docs/plans/nas-to-mac-job-queue.md` declined to
answer, and this design leaves it unasked.

### The routes

Five, and the unit of every one is a single model call:

| Route | Calls | |
|---|---|---|
| `POST /images/lexemes/{id}/brief` | 1 text | Every sense of the word at once — §03's batching. |
| `POST /images/prompts/{id}/render` | 1 image | `prompt`/`styleId` in the body is edit-and-draw. |
| `PUT /images/prompts/{id}/picture` | none | The owner's own file, as a raw body. |
| `DELETE /images/prompts/{id}` | none | Removes the picture and sets `suppressed`. |
| `GET`/`PUT /images/settings` | none | The two settings, plus the style table. |

> ### DECISION
> **Per-unit routes, not one route per word.**
>
> Not symmetry with capture. `web/src/api.ts` gives an ordinary request 15 seconds and capture 300,
> while a picture takes 30–60 and providers meter roughly one a minute. A route that briefed and drew
> a whole word would outlive even the capture timeout while the server carried on drawing — the
> client would retry, and the picture would be drawn, and billed, twice.

And three *named* actions rather than one that guesses, because they cost different things: **draw
again** is one image call with a fresh seed, **write a new brief** is one text call that rewrites
every sense of the word, and **edit and draw** costs no text call at all.

> ### DECISION
> **The server writes the file *and* the row, and this is not an exception to the capture rule.**
>
> Only headless transports ask `/capture` to apply, because a draft is a proposal for a person to
> review and the interface is where reviewing happens. Drawing has no review step and produces a
> binary the client cannot make and cannot put in the graph. So the routes write both — through
> `repository.graph.merge_graph`, the route every other writer uses, with the same validation and
> the same revision allocation. Calling it an exception would invite a second one.

### Where the pipeline lives, and why not under `jobs/`

`src/acervo/images/` stands alone on `src/acervo/models/` and imports nothing else of Acervo's — not
settings, not the graph, not `acervo.errors`. `tests/unit/server/test_layering.py` enforces it, the
same way it enforces the provider package's independence.

That independence is the point rather than tidiness: **`api/` may not import `acervo.jobs`**, so
while these modules lived under `jobs/images/` a picture could not be drawn from a route without
either breaking that rule or writing the pipeline twice. Routing through `services/` to reach
`jobs/` would have been worse — the request path would then transitively import `acervo.client`, the
HTTP client of its own service, keeping the letter of the test while breaking exactly what it exists
to protect.

What stayed in `jobs/images/` is what is genuinely batch and runs on the laptop: the run directory
that *is* the queue, the concurrent runner, `verify` and `publish`, writing the graph through
`acervo.client` — a job's write path is a client's write path. (The unattended sweep that lived here
is gone; the server's own `enrich` job took its place.)

`ArticleView` is the reuse that matters. `build_articles` takes the `changes` mapping the graph route
speaks, so the laptop run feeds it a `client.pull_graph()` payload and `services/images.py` feeds it
rows the repository projected — one view model, two feeders, the same idea `articleFor` and
`articleFromDraft` already use on the client.

### Phase A ran on the laptop, and that was right

> ### DECISION
> **Phase A ran entirely on the laptop, read the graph read-only, and wrote only to the local
> filesystem.**
>
> Three reasons, in order. The prompt needed eight rounds of iteration and a local run is a
> thirty-second edit-and-see loop. The Vertex credits expired on a calendar and the server path was
> a schema change and a deploy away. And the ingestion of ~1,500 real entries was running against
> that same server — a read-only local script could not disturb it.

Phase A was not throwaway. **It minted the real 15-character `imagePrompt` ids offline**, which is
what the ID rule already requires of every client, and wrote the files under their final names — so
publishing is a plain write of rows that already know their ids. What it could not anticipate is that
the database those ids were derived from would be rebuilt; hence §00 and the re-keying step.

## §10 · Phases

| | What | Touches the server | State |
|---|---|---|---|
| **A** | Local generation: brief writer, style offering, renderer, contact sheet | reads only | **done** |
| **B** | Import of a run into the graph and the media directory | writes | **done** |
| **C** | The schema: `example`, `attempts`, `failureReason`, `suppressed` | writes, schema | **built; needs the reset** |
| **D** | The routes, the enrichment job, the article, Settings ▸ Pictures, the export | writes | **built; needs C deployed** |
| **E** | Landing the ~2,285 pictures drawn on the laptop | writes | **needs D deployed** |
| **F** | Anki cards, one per example, with the sense image | | E, and the Anki generator, which does not exist |

Two ordering constraints, and both are about not losing work.

**C requires `--reset-database`, which destroys the database**, and there are ~1,500 hand-collected
entries in it. The sequence is: finish ingesting → export a bundle at schema version 6 → verify that
bundle imports into a throwaway database → only then deploy the schema change, recreate the account,
and re-import. `upgradeBundle` accepts version 6 as well as 7 for exactly this reason: nothing in a
word file changed, so version 7 is a version being *accepted* rather than text being rewritten,
which is the cheapest form that exception takes and the one to prefer.

**E has to come last**, and this is the one that is easy to get wrong. The reset destroys the graph
and the bundle carries no sense ids, so re-keying against anything but the *final* database is work
thrown away — the ids would be re-derived from senses that the re-import replaces.

### Phase A, as built

| | Spanish | English |
|---|---:|---:|
| Senses in scope | 1,437 | 851 |
| Drawn | **1,437** | **848** |
| Refused by the writer | 0 | 2 |
| Blocked by the provider | 0 | 1 |

Cost was about **$77** at ~$0.0336 an image, over roughly 38 hours of unattended running at the one
image per minute the project's quota allows. Eight review rounds found and fixed twenty numbered
failures in the brief-writing prompt; the reject rate went from 7 in 14 to 0 in 50, and the image
model never changed.

Two operational lessons, both of which cost real work and both of which are now built in:

- **Pace every model, not just the expensive one.** The image path had a gate and twelve retries; the
  brief path had neither, and one text-quota refusal silently lost every sense of that lexeme — ten
  senses in a thirteen-hour run. `BriefWriter.write` waits out an exhausted chain for this reason,
  and the runner retries on exactly the three transient codes.
- **A terminal outcome must be recorded as terminal.** A writer refusal and a provider block are both
  finished, and both were being re-planned on every subsequent run until they were marked. That is
  what `attempts`, `failureReason` and `suppressed` are for, and it is the difference between work
  that converges and work that spends every night on the same handful of senses.

### Phase A, concretely

New code, all in new files, so nothing the running ingestion imports is touched:

```
config/image-styles.yaml              the style table
prompts/acervo_image_brief.md        the brief-writing template
src/acervo/images/styles.py           load the table, offer every style the owner left on
src/acervo/images/article.py          the article view the brief writer is given
src/acervo/images/brief.py            build the LLM request, parse and validate the reply
src/acervo/images/compose.py          brief + style + template -> the image prompt
src/acervo/images/render.py           one (provider, model) pair -> WebP master
src/acervo/jobs/images/run.py         plan, execute concurrently, checkpoint
src/acervo/jobs/images/verify.py      is this run directory safe to publish?
src/acervo/jobs/images/publish.py     the rows into the graph, the files into the media directory
scripts/generate_images.py            check | plan | run | verify | publish | sheet
```

Both model calls go through `src/acervo/models/`, so neither file names a provider: the brief walks
the text chain and the picture is drawn by whichever image pair the pool finds free soonest.
`jobs/` may not read the owner's chain — `test_layering.py` forbids it importing `repository/` — so
`generate_images.py` is given one: the `--brief-chain` / `--image-chain` flag, else the chain the
owner chose, fetched over `GET /api/acervo/v1/models` like any other read, else the catalogue's own
order. Only an *owner* chain travels; the server's own order is resolved against the server's
credentials and would drop Vertex on exactly the machine that can reach it.

The graph is pulled read-only through `GET /api/acervo/v1/graph`, the same cursor route the app
uses, authenticated the way the ingest script authenticates.

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

The finalist report's $0.0336 per image is a **configured constant** in `config/image-benchmark.yaml`,
not a measured bill — it was there so the benchmark could rank candidates by cost, and no invoice
has been checked against it. What the first runs actually measure is **1,120 output tokens per
image**, consistently. The real figure is whatever the billing page says per output image token;
treat $0.0336 as an order of magnitude, not an amount.

Against the Spanish half of the ingestion, measured on 2026-09-05 with ingestion still running:

| | |
|---|---|
| Spanish words in the graph so far | 538 |
| Senses | 843 |
| Senses per word | ~1.57 — well under the 2.3 first assumed |
| Projected Spanish senses at ~900 words | ~1,400 |
| Measured throughput | **~1.15 images/min** |

**Quota, not cost, is the binding constraint.** The project is new, and its per-minute allowance for
`gemini-3.1-flash-lite-image` is small enough that three workers spend most of a run waiting. Ten
images took 8m45s wall clock with seven pool-wide quota pauses; every one eventually succeeded, so
nothing is lost — it is just slow. At that rate the Spanish backlog is roughly **20 hours**, which is
an overnight run and a bit, not the 2.6 hours first estimated.

The fix is a quota increase in the Cloud console (IAM & Admin → Quotas, filter on the Vertex AI
image model), and it is the single highest-leverage action available, because the credits expire on
a calendar and the throughput is what decides how much of them can be spent. Everything else — more
workers, a higher rate limit — is downstream of that number.

Pacing is one shared gate rather than per-worker backoff (`pacing.py`): a 429 pauses the whole pool
and the pause doubles while refusals continue, because workers that back off privately just arrive
together again.

## §11 · Settled, and still open

Settled:

| | |
|---|---|
| What `prompt` stores | The brief. It is what the article shows and what the dialog lets you edit; the full prompt is composed on demand and never stored. |
| Scope | Every sense, no cap. |
| Style menu | Every style the owner left on, rotated per lexeme; the writer picks and may not invent. |
| The two settings | `image_settings`, an owner-scoped table never replicated — `model_selection`'s shape and its three-state doctrine, where no row means "follow the deployment default". |
| Style storage | The switched-**off** ids, never the on ones, so a style added later arrives on. |
| Aspect | 1:1. Square suits the article and an Anki card, and it is the model's native output. |
| `attempts` / `failureReason` / `suppressed` | Columns, with the threshold in code. Derived states, no status enum. |
| Where a picture is shown | Under the sentence it was drawn from, which is what `exampleId` records; under the sense when it names none. |
| Backups of the masters | An opt-in `media/` directory in the export, plus whatever backs up the media volume. |
| Budget | Uncapped. |

Still open:

1. **How pictures are presented.** Deliberately deferred and deliberately plain for now: a square
   frame under the sentence, a fold with the brief and the model, and the controls. Several things
   about the article are due to change at once, and picture layout should be decided with them
   rather than ahead of them. What is built is the infrastructure that work will sit on — which is
   why every state occupies the same box, so nothing reflows when a picture arrives.
2. **Do the abstract senses actually work as mnemonics?** The briefs read well and the pictures are
   beautiful; whether a glowing knot of woven threads recalls *abundar en un tema* specifically, or
   merely recalls "convergence", is a judgement only use answers.
3. **Audio.** Pronunciation (`docs/design.md` §04 "Media") inherits all of this — the media directory, the
   route, and the shape of the work, so that audio is a caller rather than a rewrite. It landed as
   a step of the `enrich` job.

## §12 · What this deliberately does not do

- No lexeme-level card images.
- No local diffusion fallback. Both calls now go through `src/acervo/models/`, so which provider
  draws is a chain of catalogue rows rather than a constant — `--image-chain cloudflare,vertex`
  carries the steady state on Cloudflare FLUX.2 Klein 4B and falls through to Vertex when its daily
  allocation stops. A *local* model is a different matter: the research measured 2.5–10 GiB of
  unified memory and one image per child process, and the machine with the GPU is not the machine
  that is always on. That is the job-queue sketch's territory, not this one's.
- No automatic quality gate. The benchmark report sketches one — luminance and colour variance,
  entropy, edge density, dominant-colour share — and Gemini's 0/12 rejection rate does not justify
  building it. It becomes interesting when generation moves to a less reliable model.
- **No lexeme-level card images.** `Article.images` is still derived by `selectors.ts` and still
  rendered nowhere, because §02 decided nothing generates it. Left alone rather than removed: it is
  the shape a card image would take if one is ever wanted.
- **~~No job store~~.** There is one now, and it is the server's: a `jobs` row written in the same
  transaction as the word, never replicated. What is *outstanding* is still a query, which is what
  keeps every step idempotent. See §09 REVISED.
- **~~No cross-process rate limiter~~.** One process does the work now, so the runner holds one
  `Pace` per lane and there is nothing to share.
- No Anki anything, and the Anki generator does not exist yet.
