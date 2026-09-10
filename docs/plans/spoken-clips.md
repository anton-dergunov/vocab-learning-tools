# Spoken clips · integrating the retrieval corpus

**Status:** Planned. Nothing blocks it. The other repository's Plan 07 is the mirror of this
document and moves to *In progress* when step 1 lands.

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

What it does **not** give, and what this integration therefore does not use: translation of a clip,
audio, forced alignment, and any ranking model. All of those are additive there and change nothing
here.

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
> `speech/pin.json` — the version, the tag, and a SHA-256 for each artifact — and
> `scripts/fetch_speech.sh` downloads them into an untracked `vendor/speech/`, verifying the digests.
> Registry publication to PyPI and npm is a later choice that changes nothing here.

Upgrading is then one command and one edited file, and a build that cannot reach the pinned version
fails loudly instead of silently taking a newer one. This answers `acervo-design.md`'s standing open
question — *"Does the corpus service live in the same repo?"* — with **no**.

### 2 · A service beside Acervo, not a package inside it

`acervo-design.md` §02 already forbids sharing: *the core and the corpus do not share a database, a
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
The service is designed to rebuild its index atomically from the cache while serving, so an update
adds videos without a restart.

### 3 · The cache is not the index, and only one of them is disposable

The captions downloaded from YouTube are the one thing here that cost bandwidth and cannot be
politely re-fetched at will. The index built from them is derived and rebuildable by design.

> **DECISION: two named volumes, mounted at two subpaths of one data directory.**
>
> - `acervo-speech-cache` → `…/data/raw` — immutable acquired input. **Nothing in either repository
>   deletes this.** Not `deploy.sh --reset-database`, not `--reset-data`, not `reindex`, not a
>   version bump, not an image rebuild.
> - `acervo-speech-index` → `…/data/index` and `…/data/derived` — rebuildable. Throwing it away
>   costs CPU and no traffic.

The greenfield rule that development databases are disposable stops at the cache volume. It is the
only store in this deployment that is neither disposable nor reconstructible from something Acervo
holds, and the backup note should say so. Detecting videos deleted at the source, and pruning what
they left behind, is the other repository's problem and is not in scope.

### 4 · A clip is an `Example`, not a new record

`EXAMPLE_ORIGINS` already contains `subtitle`. `Example` already carries `videoRef`, `videoTitle`
and `videoStart`, `LexemeArticle.tsx` already draws a clip button, and `projection.py` already
hides the title and start when there is no reference. The model was designed for this and the
remaining work is three fields.

> **DECISION: a clip is an example with `origin: "subtitle"`.** It gains `videoEnd`, `videoChannel`
> and `clipRef` — the corpus's stable `segment_id` — and nothing else. No ninth table.

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

There are two writers here and they do not coordinate: the interface's enrichment engine, which
searches the word you just saved, and the sweep, which walks the backlog. That is the same pair that
draws pictures, and it is exactly why an `imagePrompt`'s id is a namespaced hash of its sense rather
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
`match_mode=auto` and `order=ranked`, bounded to a small candidate set (start at 20; the API caps at
50). The candidates go to the model with the article's senses, and the model returns for each sense
either one candidate id or nothing.

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
  `prompts/acervo_clip_select.txt`. No new catalogue kind: this is a text call, and a separate kind
  would be a knob invented before a need.

The prompt itself is a research question of its own, and it has its own document:
[`clip-selection-experiment.md`](clip-selection-experiment.md). Ship a reasonable first version with
step 3 and tune it there.

### 8 · The marker is a date, not a flag

Two questions need answering later: *which words have never been through this?* and *which words
were searched against a corpus that has since grown?* One field answers both.

> **DECISION: `clipsSearchedAt` on the lexeme — the instant the corpus was last successfully
> consulted, or null.**

- Null → never consulted. The sweep picks it up. This is what an imported word looks like.
- Set, no `subtitle` examples → consulted, nothing was good enough. The sweep leaves it alone, and
  does not spend a model call re-learning that the corpus is thin.
- Set and older than the corpus's own `built_at` from `GET /status` → the corpus has moved on. That
  is the rescan predicate, available for free, with no rescan button built.

It is written only on a **successful** consultation, so a retrieval service that was down leaves the
word looking untouched and the sweep finds it later. This is why a save can never fail because the
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

The catalogue directory is a **volume seeded from the image on first run and never overwritten**, so
a channel the owner added survives a version bump. The cost is honest and worth stating: a channel
newly shipped by a later retrieval version does not appear on its own. The owner's list is the
owner's.

### 11 · A third enrichment kind, not a second engine

`enrichment.ts` already says it: *audio is a second `kind`, not a second engine.* Clips are the third,
in the same queue, showing in the same activity panel, and the word unit enqueued at save covers
both a clip search and the picture work.

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

- **No translation of a clip.** The example stores `translation: null`. The other repository's
  translation capability is additive and can be adopted later without a schema change here.
- **No manual corpus search surface.** The owner does not browse the corpus and pick clips by hand.
  If that turns out to be wanted, it is a separate feature with a separate design.
- **No rescan.** Neither adding a channel nor a completed index update touches words already held.
  §2.8 leaves the predicate available; the button is not part of this work, and §2.4a says what it
  would have to add first.
- **No cross-service health dashboard.** Settings ▸ Clips shows whether the service answers and what
  its corpus contains, which is what a person actually needs. A dashboard is not that.
- **No audio, no alignment, no ranking model.** All additive on the other side.

---

## §3 · What this retires

- `docs/acervo-server.md` §3 reserves `src/acervo/corpus/` — *"a separate store with a separate
  database"* — and §7 notes it *"still has no code to put a boundary around"*. It never will: the
  corpus is a separate repository and a separate service. Delete the reservation and say where the
  corpus actually lives. What lands in Acervo is `src/acervo/clips/`, which is about *choosing* a
  clip and holds no corpus at all.
- `acervo-design.md`'s *Still open* question **"Does the corpus service live in the same repo?"** is
  answered: no, and §1 above says why.
- `acervo-design.md` §07's engine choice (Meilisearch vs FTS5) is moot — the other repository made
  it, and it is SQLite.
- `LexemeArticle.tsx`'s `"Clip playback is not wired up yet"` placeholder.

---

## §4 · The steps

Roughly one session each. Each one leaves the application working.

### Step 1 · The pin, the service, and the deployment

The version contract and nothing about words yet.

- In the retrieval repository: cut a tagged release with the wheel and the `npm pack` tarball
  attached. This is its Plan 07, items 1–3.
- `speech/pin.json` — version, tag, and a SHA-256 per artifact. `scripts/fetch_speech.sh` fetches
  into an untracked `vendor/speech/` and verifies the digests.
- A `speech-retrieval` compose service built from the wheel: internal-network only, no published
  port, a healthcheck asserting HTTP 200 on `/api/v1/health/ready` using a binary the image
  **actually has**, `restart: unless-stopped`, and the two volumes of §2.3 mounted at their subpaths.
  The catalogue volume, seeded if empty.
- `install.sh` creates the volumes and never clears the cache one. `run-worker.sh index-clips` runs
  `update --once` through `exec`, for a cron line.
- The web build installs the pinned tarball.

**Done when:** the Acervo server can reach `/api/v1/status` on the internal network and it reports an
indexed language; `update --once` adds a video without restarting the service; the cache volume
survives `deploy.sh --reset-database`.

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

**Done when:** a word with a hand-written clip example round-trips through YAML, export and import
unchanged, and `./deploy.sh --reset-database` deploys the new schema.

### Step 3 · The pipeline

- `src/acervo/clips/` stands alone the way `acervo.images` does — it imports `acervo.models` and the
  narrow retrieval client and nothing else of Acervo's, and `test_layering.py` says so.
- `prompts/acervo_clip_select.txt`, tracked text, read at request time.
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
- `jobs/clips/` — the sweep, which asks the graph for lexemes with a null `clipsSearchedAt` and runs
  the same pipeline, bounded by `--limit`, writing through `client.py`. `acervo_worker.py clips`
  and `run-worker.sh find-clips`.
- Run it over the imported backlog.

**Done when:** `find-clips plan` prints what it would do and spends nothing; `sweep --limit 20`
walks twenty words; running it twice does the second half.

---

## §5 · Verification

Beyond each step's own criterion:

- `.venv/bin/python -m pytest`, `npm --prefix web run test`, `npm --prefix web run build`,
  `npm run test:pwa`, `npm run test:mac`.
- A contract test in Acervo pinning the retrieval routes it depends on against the vendored
  `openapi-v1.json`, so a version bump that changes them fails a test rather than a save.
- `test_layering.py` extended: `acervo.clips` imports no settings, graph or database; `api/` does
  not import `jobs/`.
- Shared vectors for the derived clip id, asserted from both `tests/unit/` and `web/src/ids.test.ts`,
  the way `image_prompt_id` already is — and a test that the enrichment engine and the sweep, run
  over one lexeme against one fake corpus, produce one row and not two.
- A test asserting the retrieval operator token never appears in a proxied response body, in the
  shape of `test_it_never_returns_a_key_or_how_a_provider_is_reached`.
- Reading a word's article with the retrieval service stopped, on a device with no network.

---

## §6 · Open questions

- **Does a clip arrive `approved: false`?** Capture's generated examples do, so consistency says
  yes, and the article shows an *unapproved* badge until the owner rules. The counter-argument is
  that the owner rules by watching and by pressing remove, which makes the badge noise. Decide in
  step 5 with the article in front of you.
- **How many candidates?** 20 is a starting point. Too few and the good clip is never offered; too
  many and the prompt drowns. The experiment document measures it.
- **Do glosses go into the selection prompt?** The image brief writer was burned by exactly this —
  glosses carry metaphors the word does not have. The definition should probably rule here too.
- **What does the owner's chain mean for a word saved offline?** Nothing is written, nothing is
  searched, and `clipsSearchedAt` stays null. That is correct today and is worth re-checking once
  the sweep exists.
