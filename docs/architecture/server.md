# The Acervo server

**Design document · 9 Sep 2026 · Rev. D · the port has landed, and `models/` with it**

What runs on the always-on machine, in what language, and how it is arranged so that the features
in `design.md` §05–§12 can be added to it rather than squeezed into it.

This is a companion to the product design, not a restatement of it. `design.md` says what
Acervo is and what the sync protocol guarantees; this says where the code that keeps those promises
lives.

> **Status.** The port is complete and §3's tree is now true in full: `models/` landed and
> `services/llm.py` is deleted. `corpus/` is gone from the tree entirely — see §7. Section §7 tracks
> what was built.

---

## §1 · The problem this replaces

The server was one JavaScript file — `deploy/acervo/pocketbase/pb_hooks/acervo.js`, 1,564 lines —
running in goja, the ES5-ish engine embedded in the PocketBase binary. No npm, no Node APIs, no
crypto, no async, no standard library to speak of. It is deleted; this section is why.

That file was two files stuck together, and only one of them had to be there.

| | Lines | Why it was in goja |
|---|---:|---|
| Projection table, merge, revision allocation, validation, guards | ~570 | Needed `event.app`, PocketBase's transaction handle. **A real reason.** |
| Capture | 641 | Must answer inside a request — which is not the same thing |
| Online dictionary connectors | 148 | Adjacency. Nothing more. |

The second group is the one that grows. Article chat (§06), audio, stories, comics, grounding (§09)
and corpus lookups (§07) all land there, and every one of them wants a library.

The constraint had already started deciding things it had no business deciding:

- The provider roadmap locked "two wire shapes, and only two", because reaching Vertex over its
  OpenAI-compatible endpoint means RS256-signing a JWT, and goja cannot.
- The provider catalogue had to be *described twice*, in JS and in Python, because a hook cannot
  depend on a second service being up.
- There was a hand-rolled HTML stripper — one regex — because goja has no library that does it.

None of those are engineering judgements. They are what an ES5 sandbox does to a design.

And the load-bearing argument for the shape — *revisions must be allocated by a save hook, because
the route is not the only writer* — is an artefact of the database living inside another process.
When the database is the service's own, it collapses into one repository function that every writer
calls.

---

## §2 · The decision

> **DECISION: One Python service owns the whole server. PocketBase is deleted.**

FastAPI over SQLite, serving the identical HTTP contract the PWA and the macOS host already speak.
The wire contract is frozen: no client code changes, and `npm --prefix web run test` passing
untouched is the acceptance test for the port.

Three things this buys, in order of how much they matter:

1. **The request path gets a standard library.** Everything on the roadmap that must answer inside a
   request — chat, grounding lookups, a real HTML sanitiser, any provider that needs a signed token
   — becomes ordinary work instead of a constraint to design around.
2. **One language.** Corpus indexing and IR, YouTube harvest, TTS, image generation, Anki, comics,
   stories: the roadmap is Python from end to end, and so is the author.
3. **One writer, in process.** Batch jobs, capture and the sync route share one transaction
   primitive rather than one of them holding the database and the others going through HTTP.

### What was given up, honestly

PocketBase's admin UI (never used), its auth (≈120 lines to replace, and nothing depended on its
token format), its migration runner (Alembic, and the *rebuild* doctrine survives — see §5), and a
pinned binary that worked. The rewrite is real work. It is paid for once, against a roadmap that
would otherwise pay the goja tax on every feature.

### Alternatives rejected

- **Modularise the hook.** Splits the file, keeps the sandbox. The two-wire-shape and
  described-twice constraints become permanent.
- **Thin hook proxying to an always-on Python service.** Two server languages forever, a hop on
  every synchronous call, and the domain model still defined in JavaScript. This was the standing
  decision of 8 Sep 2026 and is superseded by this document.
- **PocketBase as an internal store behind a Python listener.** Worst of both: an HTTP round trip
  per record write and no transactions.

---

## §3 · Shape

```
src/acervo/
  settings.py        the one place the environment is read
  domain/            pydantic models — the canonical server model and the wire projection
  db/                SQLAlchemy tables, engine, session factory, alembic/
  repository/        the only code that touches the database
  api/               FastAPI: routers, the error envelope, auth, the static surfaces
  services/          request-path work with no database concern of its own
  models/            the provider catalogue, and text() / image() / speech() / ocr()
  article.py         one word and its senses, the view every enrichment reads
  images/            the sense-image pipeline: a brief per lexeme, a picture per sense
  clips/             the clip pipeline: a corpus search and one selection per lexeme
  speech/            the corpus's translation seam, running on the owner's chain
  ocr/               photo capture's page: an OCR engine's words to lines and sentences
  dictionaries/      the external-dictionary artifact compiler
  jobs/              one-shot batch work, run by acervo-worker
  consumers/anki/    the headless Anki robot
  client.py          the one HTTP client against the service
  admin.py           the management CLI
experiments/         experiments and benchmark tooling; never imported by the service
```

### The six rules

**1 · `repository/` is the only code that touches the database.** Routes, services and jobs all go
through it. This is the server-side twin of the rule the client already lives by: *interface code
must read and write only through `AcervoRepository`*.

**2 · A repository function is a transaction.** It opens its own session and closes it. There is no
`Depends(get_db)` and no request-scoped session.

This is not tidiness. Capture makes two model calls of up to 120 seconds each, and today it runs
them deliberately outside any transaction, wrapping only the write. The idiomatic FastAPI
request-scoped session plus `BEGIN IMMEDIATE` would open an exclusive write transaction on the first
read of the request and hold it across both calls, blocking every other request for up to four
minutes. Owning session lifetime in the repository makes that impossible to write by accident rather
than something to remember. Anything that must be atomic across several operations is *one*
repository function.

**3 · `api/` may not import `jobs/`.** §09: *capture → article → review must work with the
orchestrator down, and the sync API must not know Prefect exists.* A package boundary is how that
stays true when nobody is watching it.

**4 · One revision counter per owner, shared by all eleven tables, allocated in the same transaction
as the record it numbers.** Never a per-table sequence. A record left at revision zero is invisible
to every `revision > cursor` pull, permanently and silently — the failure has no symptom until
someone notices a word missing on another device weeks later.

**5 · Batch jobs write through `client.py`, against the service's own graph route.** Same route,
same validation, same revision allocation as a phone. One writer process, one pipeline — the rule
already applied to capture transports: *adding a transport must not add a second pipeline.* It also
retires the four hand-rolled PocketBase clients that grew independently.

This once carried an exception for the corpus, which had its own store and wrote to it directly.
That exception is retired: the corpus is not in this repository. It is
[`spoken-usage-retrieval`](https://github.com/anton-dergunov/spoken-usage-retrieval), deployed
beside the server as its own container from a pinned release, and nothing here writes to it —
§02's *the core and the corpus do not share a database, a container, or a backup policy* is now
true by construction rather than by discipline.

**6 · `models/` stands alone; `services/models.py` is where it meets Acervo.** The package decides
*what kind of thing* went wrong — a closed seven-value `Reason` — and the binding layer decides what
Acervo's wire calls that. The `llm_*` codes carry Acervo's HTTP statuses and prose written for the
owner, so they do not belong in a package meant to be usable without Acervo; and "429 means try the
next row" is provider knowledge, so it does not belong in every caller that has to know it.

This is the rule this server can break most quietly. One `from acervo.errors import ApiError` in
`call.py` collapses the split and everything still works — the tests pass, capture works, and the
package is simply no longer the thing it was built to be. So `test_layering.py` asserts it.

### Synchronous and asynchronous

The server is the unit that works, and the package layout draws the line.

- **`api/` + `services/` — synchronous.** Capture for review, chat, the graph and article routes,
  session, health, dictionary lookups, pressing play. Must work with everything else down.
- **`work/` — asynchronous, in the same process.** A durable `jobs` row per piece of work, and a
  runner that takes one at a time: a saved word's enrichment, a headless capture, a redraw, the
  nightly corpus update. It calls the same `services/` functions the routes call, so a job and a
  request are one pipeline entered from two places.
- **`jobs/` — batch work that runs somewhere else.** The Anki consumer, the dictionary compiler and
  the laptop image run, one-shot through `acervo-worker`, writing the graph through `client.py`.

> **DECISION: the request waits only while the owner is waiting on its answer to continue.
> Anything that lands on a stored record while the owner may walk away is a job.**

| Synchronous (the owner is waiting) | A job (the result lands on a record) |
|---|---|
| `POST /capture`: resolve and compose for review | the enrichment of a saved word |
| `POST /chat` | a headless capture |
| pressing play on a pronunciation | a redraw, a new brief, edit-and-draw |
| dictionary lookups | the nightly corpus update; loops and stories |

A redraw is a job even though the owner asked for it: the point was being able to leave the word
while it fills in, and a request that dies when the article closes is not that. **There are no
client retries anywhere.** A synchronous failure is shown and the owner presses again; the provider
chain's fall-through still happens inside the request.

### Jobs

**Work is started by the write that makes it necessary.** A save that creates a lexeme, or adds a
sense to one, queues an `enrich` job inside `repository.graph`, in the same transaction as the
record — so every writer is covered (`POST /articles`, `POST /graph`, a capture job's save, an
approved chat edit) and a client never asks for enrichment. A job's own writes create no lexemes or
senses, so they queue nothing. Editing a sense's text does not re-enrich: a picture that no longer
fits is the owner's call, through Redraw. A bundle import saves without enrichment, restores its
pictures, and then queues `enrich`, which skips what the restore put back.

**Why a job table, when the design once forbade a queue.** The old rule — *derive the work from a
query, never from a queue* — was written for Prefect as an optional orchestrator and pictures drawn
on a MacBook that might be away for a week. Its arguments, and what answers each now:

| The argument | The answer |
|---|---|
| A lost enqueue loses work. | The job is written in the same transaction as the word that needs it: both exist or neither does. |
| A job store is owner-scoped data, so it would replicate to every phone. | `sync_state` and `model_selection` are owner-scoped and never replicated; `jobs` is the third. |
| An in-process task dies on every deploy. | A deploy refuses while jobs are open, or cancels them when told to. Nothing crosses a version. |
| It makes the process that must stay responsive the orchestrator. | The work is waiting on remote APIs, and no database session is held across a model call. The load is a thread waiting on sockets. |
| A backgrounded tab freezes its timers. | True, and the argument *for* the server. |

What the rule got right is kept. **Steps are idempotent by derivation**: a job says *which word*, and
what that word still lacks — senses without a brief, `clipsSearchedAt IS NULL`, the recordings the
settings want — is read from the graph when each step runs, so a job run twice writes nothing the
second time. **Derived ids make writers converge**, so a person's action and a job on the same sense
cannot create two rows. And **"none" is a success**: a word with no picture or no clip is complete.

**The record.** One `jobs` table, owner-scoped, never replicated, owned by `repository/jobs.py`: kind,
subject, a small JSON input, state (`queued` → `running` → `done` | `failed` | `cancelled`), trigger,
steps with their progress and error codes, and a parent for the words a capture created. It is exempt
from the no-uniqueness rule like the other two, and carries one partial constraint: **at most one
open `enrich` per lexeme**. An enqueue that meets a queued one does nothing; one that meets a running
one sets `rerun`, and a fresh job is queued when it finishes. Finished jobs are kept 14 days; a
failure is kept until it is dismissed.

**`enrich` is clips, then pictures, then pronunciations.** Clips first because one call covers every
sense, it is the fastest, and it is the step that changes the example set; pictures second because
they are what the owner is waiting to see; recordings last because they are invisible and by then
the examples are final. Each step reads its own switch when it starts, so a setting changed mid-job
affects the next step, and a failed step is recorded and the job goes on.

**Retry and pacing live in the runner**, and a route makes one attempt. The chain decides *which* pair
answers — fall-through, hedging, cooldowns — and the runner decides *whether to ask again*: only on
the three transient codes, resting rather than sleeping inside a request, with one limiter per lane
now that one process does all the work. Exhaustion is recorded where the owner will look — a
picture's `failureReason`, a step's error — and the word stays usable.

**The runner** (`src/acervo/work/`) is a thread started from the application's lifespan, running one
job at a time because the allowances are the owner's own; a job that must wait gives up its turn.
Cancellation is checked between model calls. **Nothing resumes**: a job still running when the
process stops is marked interrupted, and Try again queues a new one. `work/` may import `services/`
and `repository/` but never `api/`, `services/` does not know jobs exist, and a route reaches jobs
only through `repository/jobs.py` (`test_layering.py`).

**A deploy never carries a job across a version.** Carrying state across means versioning it, and
the jobs involved take minutes. `./deploy.sh` reads the open jobs from the running server and
refuses; `--cancel-jobs` cancels them first; `--jobs open|cancel` asks without deploying. A job
queued between the check and the stop comes back interrupted — an accepted race.

**Telling the device.** `GET /events` is one authenticated stream with two messages: a job's state,
and "the owner's revision moved". On the second the device pulls; on the first it updates its map of
open jobs, rebuilt from `GET /jobs?open=true` after a reconnect. It is read with `fetch`, because
`EventSource` cannot send a bearer header. It carries notifications and never records, so a replica
still changes one way only, and without it the 60-second pull still converges. Whether a long-lived
stream passes through the macOS host's web view and Tailscale Serve unbuffered has not been checked;
the pull is the fallback either way.

**Headless capture is one job per submission**, because the caller cannot know how many words a text
holds — resolving discovers that. The `capture` job resolves, stops at a duplicate or composes and
saves each word to the Inbox through the same save, records each word's outcome, and creates one
child `enrich` per saved word. Interactive capture stays synchronous, because someone is reviewing
it.

**One timed run.** Settings ▸ Schedule holds one hour and a switch per step; at that hour one
`nightly` job runs its steps in order, so they can never compete for an allowance. A failed step does
not stop the next, a night the server missed runs once when it comes back, and missed nights do not
accumulate. There is no cron and no host scheduler.

**A new capability is a new job kind, and nothing else.** A kind declares a name, a subject (a
lexeme, a set of ids, or none), its steps and its output — always a record or a media file written
through `merge_graph` — and inherits queuing, retry, pacing, cancellation, the event stream and the
interface's progress for free. That is how loops and stories were added. A kind may do light CPU
work, an encode or a composite; anything heavy is out of scope for the runner.

---

## §4 · Storage

> **DECISION: SQLite, one file, for the core graph.**

One owner, 20–50 MB, and a write rate measured in words per day. It removes a container instead of
adding one, and it is what §17's backup design already assumes — `sqlite3 .backup` is the documented
layer-1 path. The corpus gets its own store later; §02 forbids sharing one.

Four connection settings, each of which is silently wrong if omitted:

| Setting | Why |
|---|---|
| `journal_mode=WAL` | Readers do not block the writer |
| `synchronous=NORMAL` | WAL's companion; `FULL` buys an fsync per commit for nothing here |
| `busy_timeout=5000` | Ordinary contention |
| `foreign_keys=ON` | **Defaults off, and is per-connection.** Without a SQLAlchemy `connect` listener every foreign key in the schema is decorative |

And one that is easy to miss entirely: **`BEGIN IMMEDIATE`**, via an engine `begin` listener. Under
WAL, a deferred transaction that reads and then writes fails its lock upgrade with `SQLITE_BUSY`
*immediately* — the busy handler is not invoked for an upgrade, so `busy_timeout` does not save you.
The revision counter reads-then-writes on every single write, so this is not a corner case.

Two consequences follow, and both are design, not tuning:

- **`GET /graph` must be a pure read.** It is the most frequent request in the system, once every
  60 seconds per visible client. Today it can create the owner's `sync_state` row, which is why it
  runs in a transaction. Creating that row at account creation instead makes the cursor poll a read,
  and retires the create-race retry that exists only to cover the alternative.
- **A `since=0` pull is unbounded** and materialises the whole vocabulary before serialising. Same
  as today, and §01 says the core stays small enough for that to be fine — but it is the first
  thing to measure if that ever stops being true.

### Derived stores beside the database

Two stores live beside the database file and in no table: the loop take cache (`takes/`) and the
meaning map's (`maps/`). Both are derived and server-local. Neither is replicated or served as a
file, so neither needs a mount, an environment variable or a schema change.

The meaning map keeps:
- `maps/embeddings/<model>/`: one `.npy` per sense text, named by the digest of the model and the
  text;
- `maps/artifacts/<owner>/<language>.json`: the map as last drawn.

### The meaning map

One language's senses laid out by what they mean, with named regions, drawn by
`GET /map/{language}`. The package is `src/acervo/meaning/`; the look and the interaction are the
prototype's (`design/ui-prototype/README.md`, "The map"); the measurements are
[`experiments/meaning-space/`](../../experiments/meaning-space/README.md).

**One map per language, one point per sense.** A single multilingual space was the first idea and
was dropped: a learner's languages serve different purposes, so the words held in each are a
different set of interests, and pooled they would make regions that describe no single language's
vocabulary. A point is a sense rather than a word because polysemy is exactly what a word-level map
collapses. What is embedded is `{headword} ({pos}) — {definition} — {gloss terms}`, the template
the discovery experiment (`interest-aligned-vocabulary-recommendation`) uses, so the two compute the
same vectors.

**The encoder is `intfloat/multilingual-e5-small`**, pinned in `models/encoder.json`, baked into
the image and loaded offline on the first map anyone asks for: 118 M parameters, 384 dimensions,
about half a gigabyte of the NAS's memory. It must be multilingual even with one map per language,
because every embedded text mixes two — a Spanish definition with English glosses. The model id is part of the cache key, so trying a stronger one
(bge-m3, EmbeddingGemma) is a setting and a recompute, and waits for the discovery experiment's
held-out recall to say whether it would be better.

**Computed on the server, not the device**: a phone pays for it in latency and battery, the server
is idle, and every device then reads the same answer.

**Where embeddings live** was a choice between four options:

| Option | Why not, or why |
|---|---|
| A replicated collection | Megabytes of floats no device needs, a `LOCAL_SCHEMA_VERSION` bump, and a model change rewriting every row's revision |
| Columns on `senses` | A derived value in an authored record, and a changed replicated shape |
| A server-only table | A schema change, so a throwaway converter, and lost on every `--reset-database` |
| **A content-addressed cache beside the database** | **Chosen**: no table, no schema, and it survives rebuilds and re-imports because it is keyed on text rather than on ids an import re-mints |

Invalidation is the digest: a sense whose text changes gets a new key and only it is embedded
again; a new picture or example costs nothing.

**The artifact carries no vectors and no text** — ids, positions, regions, labels and each sense's
five nearest senses of other words — and the device joins the ids to its replica, so an edited
headword shows at once and a map already drawn reads offline. Its **version** is the fingerprint and
the state of the names together, because naming changes the map without changing its layout: asked
by fingerprint alone, a device holding the unnamed map would be told it was current and never see
the names. A device sends its version as `?have=` and a current map answers `{"current": true}`.

**Drawn on request, not by a job.** A map is redrawn when the set of `(senseId, text digest)` pairs
has changed, under one lock per owner and language. It is seconds of local CPU with no model call,
and the one-at-a-time runner would leave it an hour behind an import. The one cold cost is the first
embedding of a language: on a laptop, 1,443 Spanish senses took 35 s cold and 3.4 s warm, and the
NAS is several times slower. It is paid once, behind *Drawing your map*.

**The map moves as little as it can, and is never pinned.** A fixed UMAP seed does not keep a
picture in place: removing 2% of the English words returned the map mirrored. So each layout is
aligned onto the previous one (Procrustes: rotation, reflection, scale and shift). That was not
enough at the `min_dist` that gives the map islands — one edited Spanish sense still moved the median
point 140 units of 1,000 — so a layout also *starts* from the previous one, with every held sense
where it was and a new one beside its three nearest. One edited sense then moved the median point
37 units, and 2% more words moved the rest 39, against 179 from a cold start.

**Regions** are Ward clustering on the **2-D layout**, cut at about 8 regions and about 30
neighbourhoods, with no noise class. On the layout rather than the vectors, because a label has to
sit over its points and a cluster found in 384 dimensions can land in pieces across the plane; no
HDBSCAN, because it marks much of a thousand-word vocabulary as noise, and that noise is the long
tail of minor interests worth keeping. Below about 150 senses regions churn between layouts, so such
a map shows only words. **Names are model-written** — one `map.name` job per new layout, on the
owner's text chain, stale-checked by fingerprint — because on the real vocabulary the deterministic
labels read as lists (nearest headwords) or as definition boilerplate (c-TF-IDF) where the model's
read as places. Until the job lands a region shows its most central words; the map never waits for
a name. The owner's standing rules are not appended, since the prompt only labels.

**On the device** the last map per language is kept in `mapStore.ts`, a store separate from the
replica, so the map opens at once and offline; the current one then arrives and new points fade in
while moved ones glide. With no stored map and no server it says so rather than spinning. The
component, `web/src/meaningMap/`, imports nothing of Acervo's (`boundary.test.ts`), and
`src/acervo/meaning/` stands alone like `images/`, so the map can move to the discovery repository
and come back as a package.

What the map may become — ghosts, other layers — is in
[`similar-projects.md`](../research/similar-projects.md), "Exploring the vocabulary".

### Write-path performance, measured

Measured against a real replica of 1,719 words (10.8k records, 7.9 MB); device figures are from a
laptop, and a tablet is several times slower.

| | Before | After |
|---|---|---|
| Device work to merge one saved word | ~190 ms (six whole-replica clones and a full validation) | 0.18 ms |
| Export panel, on every repaint beside a running import | ~1,020 ms | 12 ms |
| Server, restoring one imported picture | 430–630 ms (re-encoded at WebP `method=6`) | 90–210 ms (stored byte for byte) |

The rest was already cheap: an article save takes 22–30 ms and an empty pull 17 ms over Tailscale.
Updates also stopped rewriting the primary key, which with foreign keys on made SQLite scan every
child index on each edit.

Four further options, each worth doing only once a measurement says so:

- **Save only what changed.** `save_article` gives every record of an entry a new revision even when
  it is unchanged. Skipping equal records means fewer writes and less for other devices to pull; the
  `base` check is unaffected. *When* editing a large word feels slow, or a typo fix visibly re-pulls
  whole entries elsewhere.
- **Pipeline the import** — a word's pictures two or three at a time, or two words in flight. It
  hides round trips rather than removing work. *When* a full-bundle import still takes more than a
  few minutes; time one first.
- **A cheaper WebP encode.** `method=6` costs about twice `method=4` (0.24 s against 0.12 s on the
  laptop), inside a model call that takes seconds. *Only with* a blind size and quality comparison,
  as audio had.
- **A first-paint cache for cold start** — the last list's headwords and glosses in local storage,
  or the heavy collections loaded after the list. Both are a second path to the same data. *When*
  the tablet's figure in Settings ▸ Sync says the replica read dominates.

### Migrations

> **DECISION: Alembic defines and bootstraps the schema. It is not an upgrade path.**

One head, and *rebuild the database* stays how a schema change is deployed — the doctrine already
written down and already tested. Development databases and incompatible replicas are disposable.
Offering `alembic upgrade head` as a second, untested path against real data would be a promise
nobody has decided to keep.

**The head revision id is derived from the schema**, and this is the part that had to be learned the
hard way. It used to be the literal `"0002_bootstrap"`, so a schema change depended on somebody
remembering to bump it — and the sense-image change did not. `bootstrap` then compared a stamped
database against an unchanged head, found them equal, and served it: every route naming a new column
returned an anonymous 500 while `/health` and the rest stayed green, so the installer reported a
healthy deployment and the interface reported being offline. That is precisely the confusion the
stamp exists to end, so the id is now a digest of the tables, columns, indexes and foreign keys.
Change the schema and the head changes with it; a database written under the old one is refused **by
name, before the server serves a single request**, and `--reset-database` is named in the refusal.

A deployment that needs a rebuild therefore *fails* rather than half-working, which is the right way
round: `tests/unit/server/test_bootstrap.py` asserts the refusal rather than asserting that some
later route breaks.

---

## §5 · Auth

Nothing depends on PocketBase's token format: the web client stores an opaque string, the macOS host
puts it in `UserDefaults` untouched, and nothing anywhere decodes it. So the replacement is chosen on
merit rather than compatibility.

- **Passwords:** argon2. Minimum eight characters, as today.
- **Tokens:** JWT, HS256, with a per-user `token_key` mixed into the signing key so that changing a
  password invalidates outstanding tokens — the one PocketBase behaviour worth reproducing.
- **Lifetime: 30 days**, chosen rather than inherited. The client refreshes once at startup and never
  again, so PocketBase's 7-day default signs out a phone left unopened for eight days.
- **Unknown email and wrong password return the same 401, with the same message** — as today — plus a
  dummy hash verify on the unknown-email path so timing does not leak what the message will not.
- **Both `Bearer <token>` and a bare token are accepted.** Existing callers are split between the
  two, and `HTTPBearer` answers a bare one with a 403 that no client handles.

Registration stays closed. Accounts are made by `admin.py accounts create`, reading the password from
stdin, and the owner's `sync_state` row is created in the same transaction.

---

## §6 · The wire contract

Frozen. It is reproduced exactly, and `web/` is the conformance suite.

| Route | Auth | Notes |
|---|---|---|
| `GET /api/acervo/v1/health` | none | Includes `capture{available, provider, model, reason}`. `reason` names an environment variable and **never** a value |
| `POST /api/acervo/v1/session`, `/session/refresh` | none / bearer | |
| `GET /api/acervo/v1/graph?since=` | bearer | Pure read |
| `POST /api/acervo/v1/graph` | bearer | One transaction, all-or-nothing |
| `POST /api/acervo/v1/graph/reset` | bearer | Confirmation token `delete-all-words` |
| `POST /api/acervo/v1/capture` | bearer | Two model calls; no transaction held across them. Takes a `resolution` from `/capture/resolve` and then makes one |
| `POST /api/acervo/v1/capture/resolve` | bearer | The quick look-up a photo tap makes: resolve alone, on the `quick` chain. Writes nothing |
| `POST /api/acervo/v1/photo/read` | bearer | A raw image body in, a page of words, lines and sentences out. Stores the photo pending; writes no record |
| `GET /api/acervo/v1/dictionaries`, `/dictionaries/online/{source}` | bearer | |
| `GET /api/acervo/v1/mac-release` | none | `{"data": null}` when there is no release — the Mac host decodes an optional |
| `GET /api/acervo/dictionaries/{file}` | **bearer** | Static, Range-capable |
| `GET /api/acervo/downloads/{file}` | **none** | Static, Range-capable |
| `GET /` | none | The PWA |

Every JSON response is `{"data": …}` or `{"error": {"code", "message"}}`. The client treats *any*
body without `data` as a generic failure, so FastAPI's `{"detail": …}` must never reach it:
`RequestValidationError` becomes `400 invalid_input`, and a ≥500 keeps its message off the wire.

Four things about that table are load-bearing and easy to unify by accident:

- **The two static mounts have different auth policies on purpose.** Downloads are open because the
  macOS updater fetches them with no credentials; dictionaries are closed because the service worker
  must not precache tens of MiB and because the data is third-party and mostly share-alike.
- **Both must answer `Range`.** The dictionary reader reads artifacts by byte range, so a dictionary
  the device does not hold is read over the network by the same code. Two silent ways to lose it:
  putting compression in front of these routes, which strips `Content-Length`; and hand-rolling a
  `StreamingResponse` to bolt on auth, which has no Range handling at all. Check the token in the
  route and return a `FileResponse`.
- **A photo is served to its owner only.** Everything else under the media route is readable by any
  signed-in account, because a record names it; a photo is a picture of the owner's own world, and
  `photos/{owner}/…` says whose it is. A pending one is never served at all.
- **Path containment must be re-implemented.** PocketBase's directory filesystem gave it for free.
- **CORS must be configured.** PocketBase allowed every origin by default; FastAPI sends nothing. The
  macOS host loads its interface from `acervo://app` and calls the server cross-origin with headers
  that trigger a preflight. Without CORS every call fails inside the browser with no server-side log,
  and the client reports it as *"The Acervo server could not be reached"* — the wrong diagnosis, with
  no evidence pointing anywhere near the truth.

### The rules the port must carry over verbatim

These have real semantics, each has a test, and each is something a reasonable re-derivation gets
subtly wrong.

1. The eight-collection order is merge order, and reversed, tombstone order — with vocabularies and
   topics excluded from the sweep.
2. `matchedForm` must occur **verbatim** in the example text: untrimmed, uncased, un-normalised.
   Capture silently drops a form that fails this exact test, so loosening the validator breaks the
   drop and tightening it turns a good capture into a 400. Same for `matchedTranslationForm`.
3. Chinese lexemes require a reading, on a **prefix** test, so `zh-Hant-TW` and `zho` match. Both
   copies, with both messages.
4. `translation` ⇔ `translationLang`, and `imageRef` ⇔ `imageModelId`: XOR on emptiness.
5. A clip title or start time requires a video reference — *and* the projection that hides both when
   there is no reference. Two mechanisms for one invariant, both asserted.
6. `origin: "attestation"` requires a source attestation, which must share the owner **and** the
   sense's lexeme — a two-hop join.
7. A `fromSentence` of `null`, `""` or absent must not collapse to `0`, or the learner is credited
   with every model-invented example.
8. A stale revision refuses the whole batch; an unknown id with a non-zero revision is also stale.
9. `datasetId` is the `sync_state` row id: stable across restarts, unique per owner, and *changed* by
   a rebuild. A fresh random id at row creation gives all three; the owner's user id gives none.
10. Wire timestamps are exactly `YYYY-MM-DDTHH:MM:SS.mmmZ` — 24 characters, three fractional digits.
11. Ids are 15 characters of `[a-z0-9]`, from `secrets.choice`.
12. An id already held by another owner is `id_conflict`, not an overwrite. It takes a second lookup,
    and skipping it is a silent cross-owner write.
13. The LLM HTTP-status → error-code mapping is a contract, not an implementation detail: the file
    ingestion retries on exactly `llm_rate_limited`, `llm_unavailable` and `llm_unreachable`. An SDK
    whose exception hierarchy replaces those codes changes the retry behaviour without changing a
    line of the retry code.

---

## §7 · Where this stands

| Phase | | |
|---|---|---|
| **0** | Cleanup and ground truth | **done** |
| **1** | The service skeleton: settings, db, auth, health, the static surfaces | **done** |
| **2** | The replication core, and cutover — PocketBase deleted here | **done** |
| **3** | Capture and dictionaries in Python; `pb_hooks/` gone | **done** |
| **4** | The existing Python folds in: one client, jobs write the graph | **done** |

`models/` has landed, which closes §3. It is a tracked catalogue of provider rows, `text()`,
`image()` and `speech()` over LiteLLM, one hand-written adapter for the two kinds LiteLLM does not
cover on Cloudflare, and a chain that falls through on 429, 5xx, a timeout and a dropped connection
and never on anything else. Capture goes through it and `services/llm.py` is gone.

It brought §3's sixth rule with it, which is the one this server can break most quietly.

The chain then became the *owner's*, in a
`model_selection` table shaped like `sync_state` — owner-scoped, never replicated, and absent
until something is chosen, because "no row" means "follow the deployment default" rather than
naming a gap. `services/models.py` resolves owner, then environment, then catalogue order, and
re-reads it per request: that is what makes Settings ▸ Models take effect on the next capture
with nothing restarted. `/health` stays owner-independent — it is the liveness probe and the
pre-sign-in readout, so an unauthenticated body that varied by caller would be wrong behind a
cache — and `GET /models` is where an owner sees their own.

`corpus/` will never exist. The reservation assumed the corpus would be built here; it was built as
its own repository instead, with its own release cadence, and Acervo consumes one pinned version of
it over HTTP. What landed in `src/acervo/` is `clips/` — about *choosing* which recorded utterance
illustrates a sense, holding no corpus at all: a narrow HTTP client, the selection call, and the
derived id that keeps two writers on one row. The design is
[`docs/features/spoken-clips.md`](../features/spoken-clips.md).

`article.py` arrived with it, and is the seventh rule in all but name: **an enrichment pipeline may
import the provider package and the article view, and nothing else of Acervo's.** `images/` and
`clips/` both want one word, its senses and their examples; what differs is the judgement each makes
afterwards, so the assembling is shared and the judgement is not — `images.article.anchor_for`
decides which example a picture illustrates and no other package has an opinion about that.
`acervo.article` itself imports nothing of Acervo's at all, which is what makes it safe to be the
thing they share, and `test_layering.py` enforces both halves.

Phase 0 deleted the superseded provider abstraction (`provider/`, `llm/`, `tts/`, `vision/`,
`config.py` — 392 source lines with no non-test importer, and 798 lines of tests for them), the
markdown-era remnants, and `PROJECT_SUMMARY.md`; renamed `src/vocabgen/` to `src/acervo/` and made it
an installed package rather than a `sys.path` insertion; and wrote this document.

Phases 1 and 2 landed together with the parts of phase 3 the cutover could not honestly leave
behind. Deleting `pb_hooks/` deletes the only implementation of `/capture`, `/dictionaries` and
`/dictionaries/online/{source}`, so those came forward: a server that cannot add a word is not a
server. What stayed for phase 3 proper was `models/` — the provider catalogue, which replaced
`services/llm.py` wholesale and has since landed — and a real HTML sanitiser in place of the one
regex carried over from the sandbox, which has not.

`web/src/` did not change, which was the acceptance test for the whole port.

Phase 4 folded the existing Python in. `client.py` replaced the four hand-rolled clients; `images/`
became `jobs/images/` and `anki_sync/` became `consumers/anki/`, which is what made rule 3 testable
rather than vacuous — `api/` may not import `jobs/` had matched nothing at all until `jobs/` existed.
`image_benchmark/` moved out to `research/` (now `experiments/`), outside the distribution. Two write paths that had never
existed now do: a verified sense-image run into `imagePrompts` and the media directory, and Anki's
FSRS state into `studyStates`. Neither needed a schema change, which is why none of it required
rebuilding the database.
