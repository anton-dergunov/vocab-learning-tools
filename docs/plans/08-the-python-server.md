# Plan 08: The Python server

**Status:** Complete, except `models/`, which is [plan 04](04-one-python-provider-package.md)'s
acceptance boundary rather than this one's.
**Depends on:** nothing. It unblocks everything else.

The design this executes is [`docs/acervo-server.md`](../acervo-server.md). Read that first — it
carries the reasoning, the layering rules and the frozen wire contract. This file is the order of
work and the acceptance boundary of each step.

## Outcome

PocketBase and `deploy/acervo/pocketbase/pb_hooks/` are deleted. One FastAPI + SQLite service serves
the whole HTTP surface, reproducing the wire contract the PWA and macOS host already speak, so no
client code changes. `src/acervo/` is one layered, installed Python package.

## Why this comes first

Plans 02, 03 and 04 all assume `pb_hooks/acervo.js` is where a model gets called. That assumption is
what this plan removes, and it is why plan 02's central contract — "the hook carries two wire shapes,
and only two" — was flagged as contested in the roadmap before any of it was built. Doing this first
means the provider work is written once, in Python, against a catalogue described once.

---

## Phase 0 · Cleanup and ground truth — **complete**

No behaviour change. What landed:

- `PROJECT_SUMMARY.md` deleted; it described files removed in `04fc346`.
- The superseded provider abstraction deleted — `provider/`, `llm/`, `tts/`, `vision/`, `config.py`:
  392 source lines with no non-test importer, and 798 lines of tests that existed only to test them.
  `provider/rate_limiter.py` went with it; `pacing.py` moved up out of `images/` and took over its one
  live caller, the file ingestion, which now gets a thread-safe gate it did not have.
- Markdown-era remnants deleted: four dead helpers in `fileops.py` (`slugify_filename` survives, in
  `anki_sync/naming.py` beside its only caller, with its tests), `config/{defaults,local,
  image-providers.example}.yaml`, `test-data/`, `requirements/{media,dictionary-spike}.txt`, and the
  `anki/` and `data/` directories that held nothing but stale bytecode.
- `requirements/core.txt` lost `ollama`, `openai`, `python-box`, `python-dotenv` — all unimported.
- `src/vocabgen/` → `src/acervo/`, with a real `[build-system]`, installed editable, and the
  `sys.path.insert` shim removed from every script. `pytest.ini` no longer puts `src` on the path.
- `docs/acervo-server.md` written; `AGENTS.md` re-aimed.

One thing this exposed and fixed: `tests/unit/anki_sync/test_input_bundle.py` invoked a script through
its shebang, so it ran under whichever `python3` was first on `PATH`. It now uses `sys.executable`.

---

## Phase 1 · The service skeleton — **complete**

Stands up beside PocketBase on a second port. Nothing cuts over, and the application keeps working
throughout.

**Build**

- `settings.py` — pydantic-settings, the one place the environment is read.
- `db/` — engine, session factory, and the four connection settings plus `BEGIN IMMEDIATE`
  (`acervo-server.md` §4). Alembic bootstrap for all nine tables. The exact column, constraint and
  index inventory is `deploy/acervo/pocketbase/pb_migrations/1787868000_acervo_core.js`; port it
  faithfully, including the deliberate **absence** of a unique index on `vocabularies.language` and
  the deliberate **presence** of one on `sync_state.owner`. The migration's comments explain both and
  should survive the move.
- `api/` — the app, the `{data} | {error}` envelope with handlers for `RequestValidationError`,
  `HTTPException` and `Exception`; CORS; bearer auth accepting both header shapes; the three static
  surfaces with their two different auth policies, Range support, path containment, and a graceful
  degradation when a directory is absent.
- `admin.py accounts create` — password from stdin, `sync_state` row created in the same transaction.
- `GET /health`, returning plan 01's envelope exactly, including `capture{available, provider, model,
  reason}` where `reason` names an environment variable and never a value.

**Acceptance**

| | |
|---|---|
| `Origin: acervo://app` | preflight and response both carry CORS headers |
| errors | a 400, 401, 409 and 500 all match `{"error":{"code","message"}}`; a ≥500 does not leak its internal message |
| `Range: bytes=0-1` on a downloads file | 206, two bytes, **no credentials required** |
| same on a dictionary artifact | 206 with a token, 401 without |
| a full artifact GET | carries `Content-Length` |
| `GET /` | serves the PWA; an unknown path falls back to `index.html` |
| healthcheck | asserts HTTP 200, not a TCP connect |
| a missing downloads or dictionaries directory | the service still starts |

---

## Phase 2 · The replication core, and cutover — **complete**

The largest phase, and the one that deletes PocketBase.

**Build**

- `domain/` and `repository/graph.py`: merge in graph order, tombstone in reverse, revision
  allocation, the projections, and validation. `acervo-server.md` §6 lists the thirteen rules that
  must be carried over verbatim — each has real semantics, each has a test today, and each is
  something a reasonable re-derivation gets subtly wrong.
- Routes: `/session`, `/session/refresh`, `/graph` GET and POST, `/graph/reset`, `/mac-release`.
- `GET /graph` must be a pure read. Creating the owner's `sync_state` row at account creation is what
  makes that possible, and it retires the create-race retry that exists only to cover the alternative.
- Rewrite the seeder as `admin.py seed`, writing through the service layer. Its per-record `exists()`
  idempotency does not survive the graph route: re-posting an existing record at revision 0 is a
  `409 stale_record`, not a no-op. Going through the service layer rather than HTTP also means it
  needs no password.
- Rewrite `tests/integration/test_acervo_app_docker.py` — 470 lines, currently one sequential test
  function — as a session fixture plus roughly a dozen tests. Its `/api/collections/…` assertions are
  PocketBase-implementation and go; the invariants they cover (cross-owner sense refused, cross-owner
  topic reference refused) are contract and must be re-expressed through `POST /graph`. Against a
  Python process there is no image to build, so this drops from a minute to milliseconds.

**Cut over.** Compose drops PocketBase; the service takes 27702 and serves `/`. Then delete
`pb_hooks/`, `pb_migrations/`, `pb_public/` (25 committed build artefacts that should never have been
tracked), the PocketBase `Dockerfile`, `scripts/stage-pocketbase.sh` and
`scripts/create_acervo_account.py`.

**Deployment blast radius** — all of it moves in this one change:

- `deploy/acervo/compose.yaml` — service name, build, the `/pb/*` paths, the volume, the healthcheck.
  The healthcheck currently shells out to `wget`, which alpine has and `python:3.12-slim` does not; a
  container whose healthcheck binary is missing reports unhealthy forever, and the installer then
  fails the deployment of a service that is running perfectly.
- `deploy/acervo/install.sh` — around eighteen sites. The four-line credential stream it reads is
  **positional**; removing the superuser without changing `deploy.sh`'s end of it misparses silently
  instead of failing. `secrets.env` on an already-deployed server carries `ACERVO_PB_SUPERUSER_*` and
  the installer hard-fails on its absence, so this needs a one-shot strip in the shape of the existing
  `GEMINI_API_KEY` migration.
- `deploy.sh` — around sixteen sites, including `docker inspect acervo-pocketbase-1` and
  `docker port acervo-pocketbase-1 8090`. Renaming the compose service silently breaks
  `./deploy.sh status`, which is the operator's only remote diagnostic.
- `deploy/acervo/remote-helper.sh` — the same container name; check whether its `PROTOCOL` handshake
  forces a helper reinstall.
- `scripts/package_acervo_server.sh`, `package.json`, `deployment.env.example`,
  `secrets.env.example`, and six sites in `tests/unit/anki_sync/test_deployment.py` — which despite
  its path is the 1,040-line deployment-script suite, around 85 % of it untouched by this.
- `--reset-pocketbase` becomes `--reset-database` everywhere.

**Acceptance**

- The rewritten integration suite passes against the Python service.
- **`npm --prefix web run test` passes with no change to `web/src/`.** If it needs one, the contract
  was not reproduced — that is the whole test.
- Sign in from the real PWA *and* the macOS host against a locally deployed service; pull a seeded
  graph, edit a word, confirm the revision advances and a second device sees it.
- `./deploy.sh --local` and `./deploy.sh status` both work.

---

## Phase 3 · Capture and dictionaries move into Python — **complete except `models/`**

**Build**

- `services/capture/` — resolve, compose, `draft_from`, apply. Around 540 Python lines: it shrinks by
  roughly 15 %, not by half. `draft_from` is the highest-risk block in the whole port; it is where a
  model's sloppiness is absorbed, and every one of its guards is deliberate and tested.
- `services/dictionaries/` — the artifact listing and the two online connectors, now with a real HTML
  sanitiser rather than a single regex.
- `models/` — the provider catalogue and `text()`, from plan 04, serving the request path as well as
  batch. It must map provider errors back onto the existing `llm_*` codes: the file ingestion retries
  on exactly `llm_rate_limited`, `llm_unavailable` and `llm_unreachable`, so an SDK whose exception
  hierarchy replaces the status mapping changes the retry behaviour without changing the retry code.
- Rewrite `tests/hooks/*.test.mjs` — 788 lines — as pytest. Every `it()` body is a contract test and
  survives, including the eight capture-health cases plan 01 added. The `FakeApp`/`FakeRecord`
  harness is deleted: against a real service with a temporary SQLite file you test the real thing.
  Drop `test:hooks` from `package.json`.

**Acceptance**

- The rewritten capture and dictionary tests pass.
- A live capture end-to-end produces a reviewable draft; the deterministic path runs against a stub
  through `ACERVO_LLM_ENDPOINT`, which redirects the Gemini path only and never Vertex.
- `pb_hooks/` no longer exists anywhere in the tree or the release bundle.

---

## Phase 4 · The existing Python folds in — **complete**

**Build**

- `client.py` replaces all four hand-rolled clients: `seed_acervo_demo.PocketBase`,
  `ingest_vocabulary_file.Client`, `images/graph.ReadOnlyClient`, and the fourth inside the
  integration test.
- `jobs/images/` writes the graph through it, giving Phase B of
  [`acervo-sense-images.md`](../acervo-sense-images.md) a target at last — the 2,285 images already
  generated have somewhere to land.
- `consumers/anki/` gains its study-state write path.
- `acervo-worker` gets a service credential and a network path to the service. It has neither today,
  because nothing has ever written from it. Preserve the volume asymmetry: `acervo-dictionaries` is
  read-write in the worker and read-only in the server.

**Acceptance**

- A job writes study state through `client.py` and the change appears in a client pull with a new
  revision.
- Exactly one HTTP client against the Acervo API exists in the tree.

---

## Non-goals

- **No data migration.** Backward compatibility is prohibited, the databases are disposable, and the
  owner's words are already exported. A rebuilt database mints a new `datasetId`, the clients stop and
  ask, and the owner re-imports through the existing bundle importer. That is the designed path.
- **No new client features.** The wire contract is frozen for the duration; `web/` changing is the
  signal that something went wrong.
- **No Prefect.** `jobs/` are plain functions with CLI entry points. Adopting an orchestrator later
  means writing a wrapper that calls them, which is exactly what §09's Phase 1 discipline asks for.
- **No corpus work.** `corpus/` gets a package boundary and a stated separation from the core
  database, and nothing else.
- **No admin UI.** PocketBase's went unused. If a database ever needs inspecting, it is one file.

---

## Implementation and verification record

*9 September 2026.*

### What was built, and what changed about the plan

Phases 1 and 2 landed together with **capture and the dictionary routes**, which this plan had put in
phase 3. That was not a choice so much as a correction: phase 2 deletes `pb_hooks/`, and the hook was
the only implementation of `POST /capture`, `GET /dictionaries` and `GET /dictionaries/online/{source}`.
Cutting over without them would have left the deployed server unable to add a word. What remains of
phase 3 is `models/` — plan 04's provider catalogue, which replaces `services/llm.py` wholesale — and
a real HTML sanitiser in place of the one regex carried over from the sandbox.

`src/acervo/` now holds `settings.py`, `domain/` (ids, the eight-entry projection table, the
validation rules), `db/` (tables, engine, one Alembic head), `repository/` (session, accounts,
graph), `api/` (app, errors, auth, static, six route modules), `services/` (llm, prompts, capture,
dictionaries), `admin.py` and `seed_data.py`.

Four decisions worth recording:

- **The Alembic bootstrap creates tables from `db/tables.py` rather than restating them.** There is
  no upgrade path to write a diff against, so a second description of the schema would be a copy with
  no reader and one more thing to keep in step.
- **`reading()` uses `AUTOCOMMIT`.** `engine.begin()` fires the `BEGIN IMMEDIATE` listener, which
  would take SQLite's single write slot to answer a cursor poll — the most frequent request in the
  system. The pure read the design asks for needs that opt-out to actually be pure.
- **Every request-path endpoint that blocks runs in the threadpool.** Reading a JSON body forces an
  `async def`, and two 120-second model calls on the event loop would stall every other request for
  four minutes — the same failure the "a repository function owns its own session" rule prevents at
  the database.
- **The JWT signing key is `sha256(secret + token_key)` rather than the two concatenated.** The
  per-user mix is preserved and the key is a full 32 bytes however short the configured secret is.

### Two things the plan got wrong

- **`pb_public/` was not tracked.** The plan called it "25 committed build artefacts that should
  never have been tracked". `.gitignore` had covered it since it was created; only `.gitkeep` was in
  the index. Nothing was recovered because nothing had been lost.
- **The packaging script needed more than a path change.** The new image installs the package out of
  the bundle, so `pyproject.toml` and `README.md` had to travel with it —
  `test_server_bundle_contents.py` caught that on the first run, which is exactly the failure it was
  written for. That test now compares the images against the archive entries rather than against the
  staged directory list, because the archive is what actually ships.

### Verification, and what it printed

```
.venv/bin/python -m pytest -m "not integration"     366 passed
npm --prefix web run test                           266 passed, 20 files, 0 changes under web/src/
npm --prefix web run build && npm run test:pwa      Acervo PWA verification passed
RUN_DOCKER_INTEGRATION_TESTS=true pytest tests/integration/   5 passed
```

`web/src/` was not touched, which was the acceptance test for the whole port.

172 of those 366 are the new `tests/unit/server/` suite. The 32 `it()` bodies of `tests/hooks/` all
survive in it, against a real service over a temporary SQLite file rather than against a `FakeApp`;
`tests/hooks/` and `npm run test:hooks` are gone. Two of the ported cases could not be reached
through the graph route at all — a clip title with no video reference, and a vocabulary with no
gloss language — because the validator refuses to write either. Both are now asserted directly
against the projection and the service, which is the honest shape: the guard exists for a writer that
did not come through the route.

A full local deployment was built, started and driven end to end, then torn down:

```
./deploy.sh --local --configure-credentials    both healthchecks pass; no superuser step
./deploy.sh --local --status                   state=running, health=healthy on 27701 and 27702
./deploy.sh --local --create-account           Created learner@account.example.com (ya3vjq7453rzc7s)
admin.py seed                                  Seeded 100 records; a second run seeded 0
GET  /                                         200 text/html, <title>Acervo</title>
GET  /words/picar                              200 — an unknown path is a client-side route
GET  /api/acervo/v1/nope                       404 {"error":{"code":"not_found",…}}
GET  /api/acervo/v1/graph?since=0              cursor 100, eight keys, serverTime 24 characters
POST /api/acervo/v1/graph                      picar 18 -> 101; a stale replica got 409 stale_record
GET  /api/acervo/v1/graph?since=100            the second device saw exactly the edited record
GET  /api/acervo/downloads/… Range: bytes=0-1  206, two bytes, no credentials
GET  /api/acervo/v1/dictionaries               401 anonymous, 200 signed in
GET  /api/acervo/v1/mac-release                {"data": null}
```

### Not verified here

- **Signing in from the real PWA and the macOS host**, and **re-importing the export bundle**. Both
  need a browser; the bundle importer is `TransferPanel.tsx` and there is no headless path to it.
  The export at `acervo-all-2026-09-08.zip` was checked for completeness before any of this began:
  3 vocabularies, 13 topics, 1,481 lexemes reconciling against es 914 / en 566 / zh-Hans 1.
- **The remote deployment.** `PROTOCOL` went 4 → 5, so the server needs
  `./deploy.sh --install-helper` once before `--reset-database` will run there.

---

## Implementation and verification record — phase 4 and the sanitiser

*9 September 2026, after the deployment was verified and the vocabulary re-imported.*

### The sanitiser, chosen by measurement

`plain_text` was one regex. Replaced by a `html.parser` tokeniser in
`services/dictionaries/markup.py`, having measured the candidates against a fragment carrying every
failure mode the real Wikimedia markup has:

```
today's regex   to b">itch.ib-brac{display:none}first sub-sensesecond sub-sense &amp; a&nbsp;gap … inside -->
lxml            to itch.ib-brac{display:none}first sub-sensesecond sub-sense & a gap, and prose where a < b
html.parser     to itch first sub-sense second sub-sense & a gap, and prose where a < b
```

`lxml.html.text_content()` still gets two of five wrong — `<style>` contents leak and list items run
together, because it inserts no block separator — so reaching for it adds a dependency without
removing a decision. The deciding point is that this is a **streaming text extraction, not a tree
query**: the only state needed is "am I inside a discarded element", and a tokeniser has no tree to
misbuild on a third party's sloppy markup. The discard set is `web/src/externalHtml.ts`'s, so the two
ends agree about what `<script>` means. Output stays plain text, because the wire contract is frozen.

An availability argument (lxml is in `dev.txt` but not the server image) was written into the plan
first and was wrong: the server can carry any dependency it needs. The measurement is the reason.

One thing added beyond the five: invisible typesetting characters — soft hyphen, zero-width space,
BOM — are stripped, because none of them is `\s` and a soft hyphen inside a word makes two strings
that read identically compare unequal. ZWNJ and ZWJ are deliberately kept: they are semantic in
Persian, Arabic and Indic scripts and in emoji sequences.

### One client, and why it is httpx

`client.py` replaced two copies of the same thirty lines plus the integration suite's helper. The two
had drifted in three ways that each mattered — 600-second versus 300-second timeouts, one carrying
the error `code` and one discarding it, and both inferring the method from the body so a bodyless
POST could not be expressed at all.

`httpx`, not `urllib`, and again the first argument in the plan was the wrong one. On merit: httpx is
already the project's outbound client in `services/llm.py` and `services/dictionaries/online.py`, so
the tree now holds *one* HTTP library rather than two; a reused `httpx.Client` gives connection reuse,
which a publish of thousands of records and a walk of hundreds of captures both want; and header
freedom is why the integration test no longer drops to raw urllib for its `Range` case.

Three layers, each the one below plus exactly one decision: `fetch` decides nothing, `raw` decides how
to read a body, `call` decides what counts as a failure. **No retries in the transport** — the file
ingestion's own tests assert `sleeps == [15, 30]` and four attempts through a real socket, and they
still pass unchanged, which was the point.

`http=` accepts a borrowed client, so a write path is testable against the application in-process:
Starlette's `TestClient` *is* an `httpx.Client`. `ASGITransport` was the obvious route and is
async-only, which a synchronous client cannot use.

### The tree, and the rule that was doing nothing

`images/` → `jobs/images/`, `anki_sync/` → `consumers/anki/`, `image_benchmark/` and its two entry
points → a top-level `research/` outside the distribution. The moves cost two real fixes beyond the
imports: every `from ..pacing import` broke, because the packages went a level deeper, and the moved
test files compute the repository root by counting parent directories.

The point of the `jobs/` move was not tidiness. `test_the_request_path_does_not_import_batch_work`
had been **vacuously true** — `acervo.jobs` matched nothing — so the rule the design leans on was
passing without testing anything. `test_layering.py` now has a guard against exactly that, and two
new rules: batch work reaches the graph only through `client.py`, and nothing that ships imports
`research/`. Its import reader also resolves relative imports now; reading only absolute ones was a
hole big enough to drive `from ...db import engine` through.

`corpus/` was not created. There is no corpus code; an empty package nothing imports is a directory,
not a boundary, and the separation is stated where a reader looks.

### The two write paths

`jobs/images/publish.py` and `consumers/anki/state.py`, both through `client.py`, neither needing a
schema change — so no `--reset-database` and the restored vocabulary was never at risk.

Two orderings in the publish are deliberate: **files before rows**, because a row whose file is
missing is a broken `imageRef` the owner sees while an orphan file is not; and **every check before
any write**, because a half-published run is worse than an unpublished one.

For the study state, three things the export did not have. `retrievability` was hardcoded `None`
against a `Float NOT NULL` column bounded to (0, 1); it now comes from Anki's own
`card_stats_data(...).fsrs_retrievability`, asked for **only when the card has a memory state** —
Anki answers `0.0` otherwise, and stored as-is that reads as "certainly forgotten". `last_review` was
`.isoformat()`, which yields `+00:00` and six fractional digits and the route refuses both; there is
now one `instant_of` in `domain/ids.py` that everything with a `datetime` goes through. And `system`
and `syncedAt` were not produced at all.

The collapse rule, because a row has one `reps` and a note may have several cards: counts add up, the
memory state comes from the least stable card, the last review is the most recent, and every id stays
in `card_ids`. `queue`, `suspended` and `flag` are dropped — no columns, and adding them means
rebuilding the database for information nothing reads.

### Two decisions taken against the plan

- **The worker does not `depends_on` the server.** The plan asked for it so a `run --rm` could not
  race an unstarted service. But a dependency applies to *every* verb: it would build and start the
  whole API service to compile a dictionary, and drag it into an Anki integration test that has
  nothing to do with it. In production the server is `restart: unless-stopped`; when it is not up the
  client says "The Acervo server could not be reached" in exactly those words.
- **The worker's credential is the owner's own account.** The plan said "a service credential", which
  cannot work: every record is owner-scoped and a cross-owner reference is refused, so a second
  account could not write study state against the owner's lexemes at all. It is deliberately not
  given `ACERVO_JWT_SECRET`, which signs every account's tokens.

### Verification

```
.venv/bin/python -m pytest -m "not integration"     588 passed
npm --prefix web run test                           266 passed, 0 changes under web/src/
RUN_DOCKER_INTEGRATION_TESTS=true pytest tests/integration/   passed
```

Both acceptance clauses, in `tests/unit/server/test_write_paths.py`, against the real routes over an
in-process client: a verified run lands as `imagePrompts` with derived ids and revisions above zero,
its files come back through `/api/acervo/media/` behind auth, a second publish writes nothing, and a
run naming senses the account does not hold publishes *nothing at all* rather than the good half.
Anki state lands as one `studyStates` row per word with a new revision, a retrievability strictly
between 0 and 1, and a 24-character `lastReview`; a second pull updates that row rather than adding
one; and a timestamp in the shape `.isoformat()` would have produced is refused by the route, which is
the reason `instant_of` exists.

"Exactly one HTTP client" is a test rather than a habit: no module but `client.py` both names
`/api/acervo` and opens a connection, with an allow-list for the four callers that legitimately speak
HTTP to Google, to dictionary sources, or to model providers.

### Still not done

- **`models/`** — plan 04, unblocked and next.
- **Publishing the 2,285 existing images.** They cannot be published as they stand: their `senseId`s
  came from the pre-port database, the re-import minted fresh ones, and because `image_prompt_id` is
  derived from `senseId` every filename is wrong too. `verify` cannot see it; `publish` refuses the
  run and says which records are stranded. `docs/acervo-sense-images.md` records what a re-keying step
  would have to match on.
- **A live `pull-state` against the deployed server**, which needs a real Anki round trip on the NAS.
