# Spoken clips · integrating the retrieval corpus

**Status:** Steps 1–7 are built. Step 1 is deployed and verified on the NAS; steps 2–7 are landed in
the repository and **not yet deployed** — steps 2 and 3 each rotate the Alembic head, and one
`./deploy.sh --reset-database` covers both. The other repository's Plan 07 is the mirror of this
document and needed nothing beyond its step 1.

What is built is not the same as what is tuned: the selection prompt has had five readings, recorded
in [`../clip-selection-rounds.md`](../clip-selection-rounds.md), and the experiment in
[`clip-selection-experiment.md`](clip-selection-experiment.md) is still unrun.
[`clip-curation.md`](clip-curation.md) records what those readings showed is wanted next. A sixth
reading found the selector translating only half of a passage it had chosen well; the prompt now
demands every clause and the rewrite is measured in
[`../../experiments/clip-translation/README.md`](../../experiments/clip-translation/README.md), while
whether *code* should refuse an incomplete translation is deferred to
[`translation-completeness-check.md`](translation-completeness-check.md) for want of data across
enough languages to set a threshold honestly.

The Spanish corpus on the NAS holds **250 videos / 60,001 segments** as of 11 Sep 2026, from three
of four enabled channels: `luisito-comunica` yields nothing because yt-dlp cannot resolve
`@luisitocomunica`, 15 `spanish-after-hours` videos are members-only, and a handful hit HTTP 429.
Those are upstream facts, and they are why `update-state.json` reports the *earlier* run as the last
successful one — `service.py` stamps that only when a language completes with no failures.

A word's article can already show what a word means, how it is used, and a picture of it. What it
cannot show is a native speaker saying it. That gap is what
[`spoken-usage-retrieval`](https://github.com/anton-dergunov/spoken-usage-retrieval) exists to
close, and this document is how the two projects meet.

## Outcome

When a word is saved, Acervo asks the corpus what real speakers said, hands the messy answer to a
model, and stores at most one authentic clip per sense — or none, which is a good answer. The clip
renders as an example under the sense it illustrates, plays in place, and can be removed with one
button.

Both repositories keep their own release cadence. Acervo names one version of the retrieval service
and upgrades it when it wants to, not when the other repository moves.

---

## §1 · What the other repository already gives

Read `docs/design.md` and `docs/plans/README.md` there before starting. In short:

- A **corpus of timestamped caption segments** harvested from a curated channel list, human-authored
  captions preferred. The stored unit is a reconstructed utterance with its timing, its stable
  content-derived `segment_id`, the matched surface span with character offsets, the channel and
  video, the caption provenance, and the reason the segment boundary fell where it did.
- **Morphological retrieval.** `match_mode=auto` unions surface and contiguous lemma matches, so
  `estar podrido de` retrieves `estoy podrido de`. Acervo's `lemma` field is exactly the key it
  wants.
- **A versioned HTTP contract** under `/api/v1`, snapshotted as `docs/openapi-v1.json`:
  `GET /search`, `GET /clips/{segment_id}`, `GET /status`, `GET /statistics`, channel CRUD with
  enable/disable behind an operator token, and liveness/readiness.
- **A foreground CLI.** `serve`, `update --once`, `reindex`, `channels …`, `status`, `doctor`. It
  never daemonizes; the host owns process supervision. Acervo is that host.
- **`@spoken-usage-retrieval/react`** — `SpeechClipPlayer`, a typed client, and one stylesheet with
  `sur-player`-prefixed classes and documented CSS variables. It renders a bounded YouTube excerpt
  with its own transport, progressive source text, a direct-source fallback, keyboard control and a
  reduced-motion mode. **It deliberately owns no modal**: the host does.

- **Optional clip translation**, as an asynchronous job with its own cache, producing a target
  sentence *and* a word-alignment graph the player renders interactively. Acervo stores none of it
  and switches it on last, in step 7 — §13 says why both halves of that are deliberate.

What it does **not** give, and what this integration therefore does not use: audio, forced alignment
of audio to text, and any ranking model. All three are additive there and change nothing here. Note
that its `Clip.alignment_status` (audio timing) and its `TranslationResult.alignment_status` (the
word graph) are different things that happen to share a word.

---

## §2 · The decisions

### 1 · Two repositories, one version pin

The retrieval repository has a wholly different lifecycle: it is a research project, its index is
regenerable by definition, and its interesting sessions are experiments rather than features. Acervo
is the thing with irreplaceable data. Vendoring its source, submoduling it, or letting Acervo's
build track its `main` would couple the two release cadences and make "regenerable" merely intended
rather than structurally true.

> **DECISION: the retrieval repository publishes tagged releases carrying two artifacts, and Acervo
> names one version in one tracked file.**
>
> A release is a git tag plus a Python wheel and an `npm pack` tarball attached to it. Acervo tracks
> `deploy/acervo/speech/pin.json` — the version, the tag, and a SHA-256 for each artifact, beside the
> Dockerfile that consumes it — and `scripts/fetch_speech.sh` downloads them into an untracked
> `vendor/speech/`, verifying the digests. Registry publication to PyPI and npm is a later choice
> that changes nothing here.

Upgrading is then one command and one edited file, and a build that cannot reach the pinned version
fails loudly instead of silently taking a newer one. This answers `design.md`'s standing open
question — *"Does the corpus service live in the same repo?"* — with **no**.

### 2 · A service beside Acervo, not a package inside it

`design.md` §02 already forbids sharing: *the core and the corpus do not share a database, a
container, or a backup policy.* The retrieval service holds gigabytes of disposable read-only text
that must be full-text searched; the core holds tens of megabytes of precious relational data that
must sync to a phone.

> **DECISION: `speech-retrieval` is a long-running compose service, like `anki-sync-server`, and the
> Acervo server reaches it over HTTP only.**

The wheel is a **deployment artifact, not a code dependency**. Acervo's server image does not install
it, does not import `speech_retrieval`, and never opens its SQLite file. It talks to the pinned
`/api/v1` contract through a narrow hand-written client. That keeps `yt-dlp`, Stanza and the model
files out of Acervo's image entirely, and it means a retrieval version bump is a container swap
rather than a Python dependency resolution.

The npm tarball **is** a genuine code dependency: `web/` imports `SpeechClipPlayer` and the typed
client from it.

Indexing is `docker compose exec speech-retrieval speech-retrieval update --once`, called from a
cron line through `run-worker.sh`. It is deliberately **not** a subcommand of `acervo_worker.py`:
that entry point is for *Acervo's own* work, and this is a foreign CLI shipped by a foreign image.
The service is designed for this — it builds into a temporary file and swaps it in with an atomic
rename, while readers open a fresh read-only connection per query — so an update adds videos without
a restart, and a query that straddles the swap still sees a consistent snapshot.

`exec` rather than a second `profiles: ["tools"]` container, for a reason beyond simplicity: the
index records which analyzer built it and readiness *refuses* an index built by a different analyzer
version. One image that both builds and serves cannot drift; two images can, and the symptom would
be a service that reports itself unready after a routine rebuild.

### 3 · The cache is not the index, and only one of them is disposable

The captions downloaded from YouTube are the one thing here that cost bandwidth and cannot be
politely re-fetched at will. The index built from them is derived and rebuildable by design.

> **DECISION: two directories, mounted at two subpaths of the service's one data directory.**
>
> - `$acervo_root/data/speech-cache` → `…/data/raw` — immutable acquired input. **Nothing in either
>   repository deletes this.** Not `deploy.sh --reset-database`, not `--reset-data`, not `reindex`,
>   not a version bump, not an image rebuild.
> - `$acervo_root/data/speech-index` → `…/data/index` and `…/data/derived` — rebuildable. Throwing
>   it away costs CPU and no traffic.

Host paths under `$acervo_root`, not named Docker volumes. Every existing mount takes its path from
the installer through a `"${HOST_PATH:-fallback}"` default, so a genuinely named volume would be the
first of its kind, would sit outside `$acervo_root`, and would be invisible to whoever is looking
after the machine. Both resets are then safe by construction rather than by care: `deploy.sh`
deletes nothing at all, and `install.sh` deletes three specific paths by name, none of them these.

The greenfield rule that development databases are disposable stops at the cache. It is the only
store in this deployment that is neither disposable nor reconstructible from something Acervo holds,
and the backup note should say so — the deploy-time backup sweep copies named Anki files from two
directories and will not touch it, which is correct for something this size but means the operator
owns it. Detecting videos deleted at the source, and pruning what they left behind, is the other
repository's problem and is not in scope.

### 4 · A clip is an `Example`, not a new record

`EXAMPLE_ORIGINS` already contains `subtitle`. `Example` already carries `videoRef`, `videoTitle`
and `videoStart`, `LexemeArticle.tsx` already draws a clip button, and `projection.py` already
hides the title and start when there is no reference. The model was designed for this and the
remaining work is three fields.

> **DECISION: a clip is an example with `origin: "subtitle"`.** It gains `videoEnd`, `videoChannel`
> and `clipRef` — the corpus's stable `segment_id` — and nothing else. No ninth table.

It arrives `approved: false`, like every other example a model produced. That is the smaller change —
the badge already renders — and it keeps clips out of the way of the approved/unapproved surface,
which is due a redesign of its own and should not have to inherit a special case from here.

Provenance stays modelled rather than flagged, exactly as with attestations: the origin says where
the sentence came from and `clipRef` says which segment it is, so the stored text can be audited
against the corpus at any time. `videoRef` remains the field the invariants hang on — a title, a
start, an end, a channel or a `clipRef` without a video reference is refused, and the projection
hides them all when there is none.

The `matchedForm` invariant applies unchanged: the form must occur **verbatim** in the example text,
untrimmed and un-normalised. The corpus hands over `match.text` with code-point offsets into the
same sentence, so this holds by construction — and a candidate where it does not hold loses its
`matchedForm` rather than being stored with a lie.

### 4a · A clip example's id is derived, for the reason an image prompt's is

There are two writers here and they do not coordinate: the `enrich` job of the word you just saved,
and a backfill walking words that predate it. (When this was written they were the interface and a
worker sweep; the job runner ([`../server.md`](../server.md), "Jobs") made both the server's, which does not
change the argument.) That is the same pair that draws pictures, and it is exactly why an `imagePrompt`'s id is a namespaced hash of its sense rather
than a random 15 characters — the lesson written into the data rules after a client that minted a
random one gave an imported sense two rows and *nothing failed*.

> **DECISION: a clip example's id is derived from `(senseId, clipRef)`**, by the same namespaced
> SHA-256 in base 36, implemented in both `src/acervo/clips/ids.py` and `web/src/ids.ts` and pinned
> against shared vectors from both sides — the shape `image_prompt_id` already has.

Two writers that pick the same segment for the same sense then converge on one row, and whichever
arrives second finds the work already done or is refused as stale. It also holds a sense to one
example per segment without a uniqueness constraint, which the replicated collections may not have.
A sense may still accumulate clips from *different* segments, which is correct: the pair is the
identity, not the sense alone.

This makes two derived-id cases where `AGENTS.md` currently records one, so its wording changes with
step 2 rather than after it.

Removal stays an ordinary tombstone — deliberately not `imagePrompt`'s `suppressed` field — and it
is safe only because §2.5 makes the search one-shot. A derived id means a later re-search that
re-selected the same segment would write at the tombstone's id and resurrect it. Nothing in this
work re-searches, so nothing can; a rescan must add a suppression field before it ships, exactly as
the image pipeline had to.

### 5 · The search happens after the save, never during the capture

> **DECISION: capture never consults the corpus.**

The first model call writes a clean article from the definition and the owner's own attestations.
Feeding it caption fragments would condition the whole entry on the messiest input in the system,
and the failure mode is invisible — a slightly worse definition, in every word, forever.

The order is deliberately the opposite: **write the article, then go looking for real speech that
matches the senses it already has.** The senses are the query's context, not its product. A word
whose corpus turns up nothing is a normal word with a normal article.

That also means the clip search is one-shot at save. Adding a channel does **not** re-scan the words
already held, and no rescan button ships in this work — see §2.12.

### 6 · The corpus segments; the model only selects

> **DECISION: the stored example text is the corpus's sentence, verbatim. The model chooses; it
> never rewrites, trims or joins.**

Where a shown passage starts and ends is an open research question in the other repository (its
Plan 17 exists to answer it by blind human comparison). A model that quietly re-cut the passage here
would make every one of those measurements meaningless, and would break the audit in §2.4 — stored
text that no longer matches the segment it names.

### 7 · One text call per lexeme, at most one clip per sense, and none is a good answer

> **DECISION: one corpus search and one text call per lexeme.**

The search is the lexeme's `lemma`, falling back to its `headword`, in the lexeme's `language`, with
`match_mode=auto` and `order=ranked`, bounded to **20 candidates** (the API caps at 50). The
candidates go to the model with the article's senses, and the model returns for each sense either one
candidate id or nothing — with the translation of the clip it chose, which is §13.

The senses are described to the model the way `prompts/acervo_image_brief.md` describes them, and
for the reason that prompt learned the hard way: **the definition in the language being learned is
the authority, and the glosses are hints that can mislead.** A gloss is a rough handle chosen for
closeness, and judging a fragment against the gloss rather than the definition finds instances of
the English word instead of the Spanish one. Reuse that prompt's wording rather than inventing a
second phrasing of the same rule.

The model is the **last and best quality gate**, not the retrieval mechanism. The other repository
improves ranking with traditional IR because it has millions of segments and cannot afford a model
call per candidate; Acervo can afford exactly one call per word, and spends it where a frontier
model is genuinely better than a feature — reading a messy fragment and judging whether it is really
an instance of *this* sense.

Three things follow, and all three are the point:

- **Refusing is the default, not the failure.** The prompt must make "none of these are good enough"
  cheap to say. A thin corpus should produce articles with no clips, never articles with bad clips.
- **Every returned id is validated against the request's candidate map.** An id the request did not
  offer is dropped and counted, and the count is surfaced. Dropping rather than refusing the whole
  word is deliberate: a hallucinated id is a prompt bug to fix, and refusing the batch would throw
  away the good selections with it.
- **It runs on the owner's text chain**, through `acervo.models`, with the prompt as tracked text in
  `prompts/acervo_clip_select.md`. No new catalogue kind: this is a text call, and a separate kind
  would be a knob invented before a need.

The prompt itself is a research question of its own, and it has its own document:
[`clip-selection-experiment.md`](clip-selection-experiment.md). Ship a reasonable first version with
step 3 and tune it there.

### 8 · The marker is a date, not a flag

Two questions need answering later: *which words have never been through this?* and *which words
were searched against a corpus that has since grown?* One field answers both.

> **DECISION: `clipsSearchedAt` on the lexeme — the instant the corpus was last successfully
> consulted, or null.**

- Null → never consulted. The word's enrichment, or a backfill, picks it up. This is what an
  imported word looks like.
- Set, no `subtitle` examples → consulted, nothing was good enough. Nothing comes back for it, and
  no model call is spent re-learning that the corpus is thin.
- Set and older than the corpus's own `built_at` from `GET /status` → the corpus has moved on. That
  is the rescan predicate, available for free, with no rescan button built.

It is written only on a **successful** consultation, so a retrieval service that was down leaves the
word looking untouched and Try again, or a backfill, finds it later. This is why a save can never fail because the
corpus was unreachable: the word is already written before anything is asked.

### 9 · The browser reaches the corpus through Acervo

> **DECISION: Acervo's server proxies a fixed allow-list of retrieval routes under
> `/api/acervo/v1/speech/…`, behind the same bearer auth as everything else.**

The alternative — exposing the retrieval service to the browser directly — means a second hostname,
a second CORS configuration, an unauthenticated read API on the network, and the operator token for
channel mutations somewhere near a browser. The proxy costs one router and removes all four. The
retrieval service stays bound to the internal compose network and is never published.

The allow-list is `GET /clips/{segment_id}`, `GET /search`, `GET /status`, `GET /statistics`, and the
channel routes. It is an allow-list rather than a pass-through so that adding a retrieval route
never silently adds an Acervo route. Acervo holds the operator token as deployment configuration and
attaches it to the mutating channel calls; it never leaves the server, exactly like a provider key.

On the client, `web/src/clips.ts` owns **every** call to those routes and nothing else makes one —
the rule `sync.ts` lives by for the graph and `dictionaries.ts` for dictionaries. It creates the
packaged typed client with Acervo's proxy base URL and a `fetch` that carries the session token, so
the packaged client is used unchanged rather than reimplemented.

A clip example renders from its stored fields, so the article reads offline like every other read.
Pressing it needs the network — YouTube is on the other side of it regardless. The player is opened
with the **current** clip fetched by `clipRef`, falling back to the stored video reference, start and
end when the service cannot be reached. Acervo owns the dialog; `SpeechClipPlayer` owns playback.

### 10 · One channel catalogue, and it is the retrieval service's

The retrieval repository already owns a curated catalogue (`config/channels/es.json` today), CRUD
routes, enable/disable, and a reviewable per-language curation session template. Copying that list
into Acervo would create a second thing to keep in step and a second place to curate.

> **DECISION: Acervo ships no channel list. Settings ▸ Clips reads and writes the retrieval
> service's catalogue through the proxy.**

The catalogue directory is a **mount seeded from the installed package when it is empty, and never
overwritten**, so a channel the owner added survives a version bump. Seeding is mandatory rather
than a convenience: the repository can only edit a `<language>.json` that already exists, and the
schema forbids a catalogue with no sections, so an empty directory cannot be bootstrapped through
the API at all. That is also why the wheel must carry the default catalogue as package data — today
it ships no JSON, and the file is found only because it happens to sit in that repository's working
tree.

Two costs, both honest. A channel newly shipped by a later retrieval version does not appear on its
own — the owner's list is the owner's. And a language the seed does not cover cannot be added from
Settings; that is a limitation to fix in the retrieval repository rather than to work around here.

### 11 · A third enrichment kind, not a second engine

Audio was already a second *kind* rather than a second engine, and clips are the third: one job per
word, its steps in one order, showing in one place. (Written when that queue was
`web/src/enrichment.ts`; the job runner ([`../server.md`](../server.md), "Jobs") moved it into the server's
`enrich` job, which changes where it runs and not the shape.)

One change is needed and it is worth writing down. **The rest timer becomes per kind.** A picture is
one image call metered by an image provider at roughly one a minute; a clip search is one text call
metered somewhere else. Sharing one backoff means an image 429 silences clip search for ten minutes
for no reason, which is exactly the wrong shape when the owner is watching the article they just
saved. Clip work is also ordered ahead of picture work for the same word, because it is the faster
of the two and the owner is looking at the page.

The article's empty states differ from pictures, deliberately. A sense with a search in flight says
so; a sense whose search finished and found nothing shows **nothing at all**. A picture's absence is
a gap to fill, so it gets a frame; a clip's absence is the expected outcome for most words, and a
permanent empty frame on every sense of every word would be noise.

### 12 · What is deliberately not built

- **No manual corpus search surface.** The owner does not browse the corpus and pick clips by hand.
  If that turns out to be wanted, it is a separate feature with a separate design.
- **No rescan.** Neither adding a channel nor a completed index update touches words already held.
  §2.8 leaves the predicate available; the button is not part of this work, and §2.4a says what it
  would have to add first.
- **No cross-service health dashboard.** Settings ▸ Clips shows whether the service answers and what
  its corpus contains, which is what a person actually needs. A dashboard is not that.
- **No audio, no ranking model.** Additive on the other side.

### 13 · Target-language text: two surfaces, and only one of them is Acervo's

The retrieval service can translate a clip. It should not translate *Acervo's*, and separating the
two surfaces is what makes the question easy.

**The article's line is Acervo's, and it is free.** `Example.translation`, `translationLang` and
`matchedTranslationForm` already exist with the `translation ⇔ translationLang` XOR invariant, and
`prompts/acervo_compose.md` already produces exactly that shape — a translation into
`glossLangs[0]` plus a verbatim matched form — in the *same call* that produces an example.

> **DECISION: the clip-selection call of §7 also returns the translation of the clip it chose**, in
> `glossLangs[0]`, with `matchedTranslationForm`, exactly as capture does for a generated example.

No second call, no second provider configuration. It goes into the graph, so it replicates to the
phone and reads offline like every other example — which a per-clip fetch from the retrieval service
could never do, since `GET /clips/{segment_id}` never populates `target_text` and translation there
is always a job.

**The player's target text is the service's, and it is more than a sentence.** Two provider calls —
translate, then align — yield a validated many-to-many word-alignment graph that the packaged player
renders as an interactive relation: click a word and its counterparts light up, and during playback
the translation illuminates in step with the audio. There is also an authored-track fallback, which
serves the creator's own subtitle where one exists and feeds it to the model as a reference where a
model is configured. Acervo should use none of that for anything it stores, and should not
reimplement any of it.

> **DECISION: Acervo stores nothing the retrieval service translated.** The article line is
> Acervo's; the player's target text and alignment are the service's, fetched when the modal opens,
> online-only, exactly like the clip.

**When the player's text is switched on, it runs on the owner's chain.** `TranslationProvider` and
`WordAlignmentProvider` are Protocols there, and `create_app` takes both — a public entry point. So
Acervo writes the adapter against `acervo.models` and the speech container calls `create_app` with
it injected, in place of the console script. The other repository changes nothing at all: no LiteLLM
dependency, no schema-dialect port, no error-taxonomy mapping.

`acervo.models` stands alone by design, so that image carries it and `models/catalogue.json` and
nothing else of Acervo's; Acervo's *server* image still never imports `speech_retrieval`. The chain
is **given** as `ACERVO_TEXT_CHAIN` rather than looked up, since that container has no business
reaching the database — the rule already stated for work that cannot import `repository/`. And
Vertex needs only the credentials directory two containers already mount.

One rule for that adapter: the cache is keyed on the `provider` and `model` it reports, so it
reports **the chain**, never the row that happened to answer. Otherwise fall-through thrashes the
cache. Translation and alignment are separate stages with separate keys, so they need not be served
by the same model.

### 14 · A clip never anchors a picture

> **SUPERSEDED (September 2026): a clip now ranks last instead of being excluded.** In use, a clip's
> sentence made a good scene, and the redesigned article puts a picture and its clip on one card
> rather than on two full-screen surfaces. The order is `attestation`, `manual`, `llm`, `tatoeba`,
> `wiktionary`, `subtitle`; a clip anchors only a sense with no other sentence. The reasoning below is
> kept as the record of why it was first excluded.

`src/acervo/images/article.py` ranks example origins for the image brief writer, and `subtitle`
currently sits third — above `llm`, which is last. Left alone, the first real clip would become the
preferred thing to illustrate.

> **DECISION: `subtitle` is excluded from the anchor set outright, and `llm` is promoted above
> `tatoeba` and `wiktionary`.** New order: `attestation`, `manual`, `llm`, `tatoeba`, `wiktionary`.
> A sense whose only example is a clip anchors on the sense text.

Excluded rather than ranked last, because ranking last still picks a clip when it is the only
example, and falling back to the sense is the wanted outcome rather than a worse one.

- **A picture of what the clip already shows is drawn for nothing.** The clip is real footage of the
  situation; illustrating it re-renders what the learner is about to watch. A picture earns its
  place on a sense or a written example that has no footage.
- **They are heading for separate surfaces** — pictures full-screen, then clips full-screen,
  scrolled independently. Two surfaces built from one sentence would show the same thing twice.

And `llm` above `tatoeba` and `wiktionary` because a generated example is written for *this* sense,
in the vocabulary's own languages, carrying a translation and both matched forms. The other two are
chosen for neither, and read worse.

---

## §3 · What this retires

- `docs/server.md` §3 reserves `src/acervo/corpus/` — *"a separate store with a separate
  database"* — and §7 notes it *"still has no code to put a boundary around"*. It never will: the
  corpus is a separate repository and a separate service. Delete the reservation and say where the
  corpus actually lives. What lands in Acervo is `src/acervo/clips/`, which is about *choosing* a
  clip and holds no corpus at all.
- `design.md`'s *Still open* question **"Does the corpus service live in the same repo?"** is
  answered: no, and §1 above says why.
- `design.md` §07's engine choice (Meilisearch vs FTS5) is moot — the other repository made
  it, and it is SQLite.
- `LexemeArticle.tsx`'s `"Clip playback is not wired up yet"` placeholder.

---

## §4 · The steps

Roughly one session each. Each one leaves the application working.

### Step 1 · The pin, the service, and the deployment

The version contract and nothing about words yet.

- In the retrieval repository: one version rather than three drifting literals, the default channel
  catalogue carried as package data in the wheel, a release workflow on tag push, and the first
  tagged release with the wheel and the `npm pack` tarball attached. This is its Plan 07, items 1–3.
- `deploy/acervo/speech/pin.json` — version, tag, and a SHA-256 per artifact, beside the Dockerfile
  that consumes it. `scripts/fetch_speech.sh` fetches into an untracked `vendor/speech/` and
  verifies the digests.
- **The Dockerfile is Acervo's**, not that repository's: its own locked contract says the package
  never self-daemonizes and that process, volumes and credentials are the host's. No ffmpeg, which
  only the audio path needs, and no Stanza, which `analyzer=auto` degrades away from without ever
  downloading a model.
- A `speech-retrieval` compose service: internal-network only, no published port,
  `restart: unless-stopped`, the two directories of §2.3, and a catalogue directory seeded from the
  installed package when empty and never overwritten.
- **The healthcheck asserts `/api/v1/health/live`, not `/health/ready`.** Readiness is 503 until an
  index exists, so a readiness gate would fail the very first deployment of a perfectly good
  service. Readiness is a corpus fact and belongs in Settings ▸ Clips.
- `install.sh` creates the directories and starts the third service; neither reset path can reach
  the cache. Keeping the corpus fresh is the server's nightly `corpus.update` step, or Update now in
  Settings ▸ Clips: both ask that service to update itself over HTTP, so the analyzer recorded in the
  index always matches the one serving it. (It was `run-worker.sh index-clips` through `exec` until
  [`../server.md`](../server.md), "Jobs".)
- `vendor/speech/` ships in the release archive the way compiled dictionaries do, because
  `compose.yaml` builds from the extracted release root.
- The web build installs the pinned tarball, imported through `lazy()`.

**Done when:** the Acervo server can reach the corpus on the internal network and `/status` reports
an indexed language; a second `update --once` re-downloads nothing and swaps the index without a
restart; the caption cache survives `deploy.sh --reset-database`.

### Step 2 · The data model

No behaviour, only the shape, so that everything after it has somewhere to write.

- `videoEnd`, `videoChannel`, `clipRef` on `Example`; `clipsSearchedAt` on `Lexeme`. Client model,
  wire projection, snake_case storage, the Alembic bootstrap (one head — this is a rebuild, not a
  migration), `yaml.ts` both directions, and the export bundle.
- Validation in both copies: the clip fields all require `videoRef`, and the projection hides them
  all without one. `matchedForm` verbatim, unchanged.
- The derived id of §2.4a in both `src/acervo/clips/ids.py` and `web/src/ids.ts`, pinned against
  shared vectors, alongside `image_prompt_id`. Update the data rule in `AGENTS.md`, which today
  records exactly one derived id.
- `upgradeBundle` gives the three new fields their absent defaults — the one sanctioned place for
  that, because an exported bundle outlives the schema it was written under.
- **§14's anchor set**, here rather than in step 3, so there is never a window in which a picture
  can be anchored to a clip. `SenseView.anchor` filters `subtitle` out before its `min()`
  and already returns `None` when nothing is left, which is the supported "the picture belongs to
  the sense" state. It is independently live today — `seed_data.py` already writes `subtitle`
  examples.

**Done when:** a word with a hand-written clip example round-trips through YAML, export and import
unchanged; a sense whose only example is a clip briefs against the sense rather than the clip; and
`./deploy.sh --reset-database` deploys the new schema.

### Step 3 · The pipeline

- `src/acervo/clips/` stands alone the way `acervo.images` does — it imports `acervo.models` and the
  narrow retrieval client and nothing else of Acervo's, and `test_layering.py` says so.
- `prompts/acervo_clip_select.md`, tracked text, read at request time.
- `services/clips.py` binds it: settings, the owner's chain, the graph, and the `llm_*` codes.
  Read (transaction) → search → model call (**no** transaction) → write (transaction), through
  `repository.graph.merge_graph` like every other writer.
- `POST /clips/lexemes/{lexeme_id}/find`, one unit of work, in the threadpool.
- `clip_settings`, owner-scoped and never replicated, with `image_settings`'s three-state doctrine:
  no row means "follow the deployment default".

**Done when:** the route turns a saved lexeme into clip examples against a fake retrieval service in
tests, refuses nothing it should keep, drops and counts an id it was not offered, and writes
`clipsSearchedAt` only on success.

### Step 4 · The proxy and the player

- The allow-listed proxy under `/api/acervo/v1/speech/…`, with the operator token attached
  server-side only. A test asserting the token is absent from every response body.
- `web/src/clips.ts` owns every call to it.
- Acervo's own dialog around `SpeechClipPlayer`, themed onto Acervo's palette through the package's
  documented CSS variables. Change `design/ui-prototype/` and `styles.css` together.
- The article's clip button plays instead of apologising; the service being unreachable falls back to
  the stored reference and start.

**Done when:** a clip stored in step 3 plays from the article, and still offers a direct link with
the retrieval service stopped.

### Step 5 · The foreground enrichment

- A third `EnrichmentKind`, ordered ahead of picture work for the same word, with the rest timer
  keyed by kind.
- The article shows a sense's search in flight and shows nothing when it finished empty.
- A remove button on a clip example — a tombstone, and nothing re-adds it, because §2.5 makes the
  search one-shot.

**Done when:** saving a word shows the article immediately, the clips appear under their senses
without a reload, and a stopped retrieval service leaves the saved word intact with the failure in
the activity panel.

### Step 6 · Settings ▸ Clips, and the backlog

- The pane, shaped like Settings ▸ Dictionaries: does the service answer, what does its corpus hold,
  the channel list with enable/disable/add/remove through the proxy, and the switch that turns
  save-time searching off.
- The backlog. *(Built as the server's `enrich` job ([`../server.md`](../server.md), "Jobs") rather than as a sweep:
  `admin jobs enqueue enrich --missing`, behind `run-worker.sh backfill`, queues the ordinary
  `enrich` job for every word with a null `clipsSearchedAt` — the same pipeline, bounded by
  `--limit`, and not a second one.)*

**Done when:** `backfill --dry-run` prints what it would queue and spends nothing; `--limit 20`
queues twenty words; running it twice queues nothing the second time.

### Step 7 · The player's target text

Optional, additive, and last because nothing above it needs it. Acervo-only work: the other
repository already exposes the seam and changes nothing.

- An adapter implementing its `TranslationProvider` and `WordAlignmentProvider` Protocols against
  `acervo.models`, reporting the **chain's** identity as `provider`/`model` so fall-through does not
  thrash the translation cache.
- A small Acervo entrypoint that calls `create_app` with the adapter injected, replacing the console
  script as the container's command. The image gains `acervo.models` and `models/catalogue.json`,
  and `ACERVO_TEXT_CHAIN` plus the credentials mount that makes Vertex work.
- The player's translation props wired through the modal of step 4.

**The schema is both sent and said, and that is what this step turned out to be about.** The
service's two prompts name no field at all — they end with "Return only the requested structured
result" and leave the shape entirely to a `responseSchema`, which is how its own Gemini adapter
works. Acervo's side had *two* things wrong with carrying that across, and either alone was enough
to fail every clip: the schema went into `response_format` bare, which is not a `response_format`
and which LiteLLM maps to nothing whatever, and it arrived in Google's GenAI dialect with its type
keywords in capitals.

**The resolution went further than fixing either.** Sending the schema correctly is what finally
showed what sending it costs, and the answer was measured rather than argued: no schema is sent
anywhere now, here included. The adapter renames the dialect and writes the shape into the
instructions, and that text is the whole contract. The alignment stage was the strongest case for
keeping a schema — it restricts every id to an enum of that request's own tokens — and against
constructed ground truth it bought no accuracy at any size it worked at, while above roughly a
hundred tokens the provider rejected it outright with a 400 this chain treats as terminal. See
`AGENTS.md`, "Constrained decoding is not used".

Three further facts, each of which produced the same single grey line in the player:

- **The image must carry `google-auth`.** LiteLLM does not require it and reaches Vertex through a
  deferred import of it; the server image gets it through `google-genai` and this one installs
  LiteLLM alone. A catalogue row is checked for environment variables and a credentials file, never
  for an importable library, so the row looked available and raised on the first call.
- **The startup guard must ask the question the chain asks.** Asking whether *any* text row is
  credentialed, while `chain.resolve` honours `ACERVO_TEXT_CHAIN`, injects a provider that can only
  fail. Injecting nothing is what produces the truthful "Translation is unavailable."
- **The service caches a refusal.** A stage that produced unusable output is remembered and served
  from that memory ever after, `cache_hit` and all, unless `retry_failed` is sent — so a correct fix
  still shows the old failure on every clip already attempted. The player's retry is wired to that
  flag, and it is the only way out from inside the interface.

  Clearing that cache wholesale means deleting `data/speech-index/derived/translations.sqlite3`, and
  **the service must be restarted afterwards**. `TranslationStore.__init__` creates the tables, and
  it runs once, in the container's lifespan — so deleting the file under a running service leaves it
  opening a fresh zero-byte database with no tables, and every query fails from then on. The symptom
  is a corpus that answers but reports itself unavailable, with a `translations.sqlite3` of exactly
  0 bytes on disk. Stop, delete, start; or delete and `docker restart acervo-speech-retrieval-1`.

`_Stage` also had to run its call off the event loop. `generate` is synchronous, and awaiting it
inline held the single uvicorn loop for the length of a model call — during which nothing in that
container answered, its own three-second healthcheck included.

**Done when:** opening a clip shows the translation and its word alignment; an exhausted provider
falls through to the next without re-translating what is already cached; and a deployment with no
chain configured shows the authored caption where one exists and no target text where none does.

---

## §5 · Verification

Beyond each step's own criterion:

- `.venv/bin/python -m pytest`, `npm --prefix web run test`, `npm --prefix web run build`,
  `npm run test:pwa`, `npm run test:mac`.
- The retrieval contract pinned in two pieces rather than against a copy of `openapi-v1.json`.
  A **recorded response** — `tests/unit/clips/fixtures/search-es-picar.json`, a real `/search` answer
  trimmed to three results — is both Acervo's statement of the contract in the shape Acervo actually
  consumes and the data every fake corpus serves; re-record it when the pin moves. Beside it, a
  **gated live check** (`RUN_SPEECH_CONTRACT_TESTS=true`) asserts against a service that is running
  that the routes still exist and the fields the client reads are still named what they were named.

  This replaces the vendored-spec check this section first asked for, and the reason is worth
  keeping. The spec belongs where it is generated: in the retrieval repository, snapshotted with one
  test that turns a renamed field into a failing pull request. A 117 KB copy here would have to be
  re-committed in full on every pin bump, would produce a diff nobody reads in a repository that
  otherwise ships lists and never data, and would still only assert — one level removed — what the
  live check asserts against the thing actually serving.
- `test_layering.py` extended: `acervo.clips` imports no settings, graph or database; `api/` does
  not import `jobs/`.
- Shared vectors for the derived clip id, asserted from both `tests/unit/` and `web/src/ids.test.ts`,
  the way `image_prompt_id` already is — and a test that two searches of one lexeme against one fake
  corpus produce one row and not two.
- A test asserting the retrieval operator token never appears in a proxied response body, in the
  shape of `test_it_never_returns_a_key_or_how_a_provider_is_reached`.
- Reading a word's article with the retrieval service stopped, on a device with no network.
