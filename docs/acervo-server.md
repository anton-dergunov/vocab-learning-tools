# The Acervo server

**Design document · 8 Sep 2026 · Rev. A · language settled, port in progress**

What runs on the always-on machine, in what language, and how it is arranged so that the features
in `acervo-design.md` §05–§12 can be added to it rather than squeezed into it.

This is a companion to the product design, not a restatement of it. `acervo-design.md` says what
Acervo is and what the sync protocol guarantees; this says where the code that keeps those promises
lives.

> **Status.** The decision is taken and Phase 0 has landed. PocketBase is still serving today.
> Section §7 tracks what is built and what is not, and is the only part of this document that
> describes the present rather than the target.

---

## §1 · The problem this replaces

The server was one JavaScript file — `deploy/acervo/pocketbase/pb_hooks/acervo.js`, 1,564 lines —
running in goja, the ES5-ish engine embedded in the PocketBase binary. No npm, no Node APIs, no
crypto, no async, no standard library to speak of.

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
  models/            the provider catalogue, and text() / image() / speech()
  dictionaries/      the external-dictionary artifact compiler
  jobs/              one-shot batch work, run by acervo-worker
  consumers/anki/    the headless Anki robot
  corpus/            a separate store with a separate database
  client.py          the one HTTP client against the service
  admin.py           the management CLI
research/            benchmark tooling; never imported by the service
```

### The five rules

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

**4 · One revision counter per owner, shared by all eight tables, allocated in the same transaction
as the record it numbers.** Never a per-table sequence. A record left at revision zero is invisible
to every `revision > cursor` pull, permanently and silently — the failure has no symptom until
someone notices a word missing on another device weeks later.

**5 · Batch jobs write through `client.py`, against the service's own graph route.** Same route,
same validation, same revision allocation as a phone. One writer process, one pipeline — the rule
already applied to capture transports: *adding a transport must not add a second pipeline.* It also
retires the four hand-rolled PocketBase clients that grew independently.

The exception that proves it: the corpus is not the graph. It has no revisions, no replication and
millions of rows, so corpus jobs write `corpus/`'s own store directly (§02: *the core and the corpus
do not share a database, a container, or a backup policy*).

### Synchronous and asynchronous

The line is §09's, and the package layout draws it:

- **`api/` + `services/` — synchronous.** Capture, the graph routes, session, health, dictionary
  lookups. Must work with everything else down.
- **`jobs/` — asynchronous.** Images, audio, Anki push and FSRS pull, corpus harvest and indexing,
  export, and the sweeps.

Jobs are plain Python functions with CLI entry points, run one-shot by `acervo-worker`. If Prefect
is adopted it is a wrapper that calls them, never something they import — §09's Phase 1 discipline.
And flows are sweeps, not queue consumers: *"which lexemes lack an image" is a query against the
core*, not a queue entry.

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

### Migrations

> **DECISION: Alembic defines and bootstraps the schema. It is not an upgrade path.**

One head, and *rebuild the database* stays how a schema change is deployed — the doctrine already
written down and already tested. Development databases and incompatible replicas are disposable.
Offering `alembic upgrade head` as a second, untested path against real data would be a promise
nobody has decided to keep.

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
| `POST /api/acervo/v1/capture` | bearer | Two model calls; no transaction held across them |
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
| 1 | The service skeleton: settings, db, auth, health, the static surfaces | not started |
| 2 | The replication core, and cutover — PocketBase deleted here | not started |
| 3 | Capture and dictionaries move into Python; `pb_hooks/` is gone by the end of 2 | not started |
| 4 | The existing Python folds in: one client, jobs write the graph | not started |

Phase 0 deleted the superseded provider abstraction (`provider/`, `llm/`, `tts/`, `vision/`,
`config.py` — 392 source lines with no non-test importer, and 798 lines of tests for them), the
markdown-era remnants, and `PROJECT_SUMMARY.md`; renamed `src/vocabgen/` to `src/acervo/` and made it
an installed package rather than a `sys.path` insertion; and wrote this document.

Until Phase 2 lands, `pb_hooks/acervo.js` is still the server and is still authoritative about
behaviour. Where this document and that file disagree about *what happens today*, the file is right.
