# Plan 08: The Python server

**Status:** Phases 0–2 complete, and the parts of phase 3 the cutover could not leave behind.
Phase 3's `models/` package and HTML sanitiser, and phase 4, remain.
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

## Phase 3 · Capture and dictionaries move into Python — **mostly complete**

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

## Phase 4 · The existing Python folds in

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
