# Plan 08: The Python server

**Status:** Phase 0 complete; phases 1–4 planned.
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

## Phase 1 · The service skeleton

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

## Phase 2 · The replication core, and cutover

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

## Phase 3 · Capture and dictionaries move into Python

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
