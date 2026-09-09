# Plan 03: The owner chooses a model

> **RE-AIMED by [08 · The Python server](08-the-python-server.md), 8 Sep 2026.**
>
> Unchanged in substance: a per-kind provider chain, owner-scoped, server-side, non-replicated, taking
> effect on the next capture with no restart. What changes is where it is built — routes and storage on
> the Python service rather than a hook and a PocketBase collection — and that it no longer costs a
> database rebuild, because the schema is being rebuilt anyway. Depends on 04, not 02.

> **Narrowed by [04](04-one-python-provider-package.md), 9 Sep 2026.** The unit this plan selects
> and reorders is a **(provider, model) pair**, not a provider. A row in `models/catalogue.json`
> names several models per kind because a free tier is metered per model — Gemini's free tier gives
> 500 requests a day to `gemini-3.1-flash-lite` *and* 500 to `gemini-3.5-flash-lite`, separately —
> so the second is reached by the first one's 429 and is worth listing. `chain.resolve()` already
> returns pairs and `Answer.attempts` already records them; what this plan adds is letting the owner
> enable, disable and reorder them instead of taking the catalogue's order.
>
> Two smaller things 04 left for this plan: `ACERVO_TEXT_CHAIN` names row ids only, so the
> deployment default cannot yet pin one model of a row — the owner record is where that belongs; and
> a row now carries `usageUrl`, a console link filled in from the environment, which Settings ▸
> Models should render beside each provider. No provider serves a usage figure over its API, so a
> link is the honest answer rather than a number.

**Status:** Complete, 9 Sep 2026.
**Depends on:** [04](04-one-python-provider-package.md) — there must be a catalogue to choose
from before there is a chooser.

## Outcome

Settings ▸ Models lists the providers this server holds credentials for and lets the owner put them
in order, per kind. The next capture uses the new order. Nothing restarts, nothing is redeployed, and
the choice follows the owner to their phone, their laptop and the native application, because it
lives on the server rather than in a browser.

When the first provider in a chain is rate limited or down, the next one answers and the entry
records which one actually did. When the first provider's key is wrong, nothing falls through and the
owner is told.

## Current state

There is no way to influence the model from the interface at all. The provider and model come from
`ACERVO_LLM_PROVIDER` and `ACERVO_LLM_MODEL` in `llm.env`, which is written by
`deploy.sh --configure-llm` over ssh and read once per request from the process environment. Changing
either means a deployment.

Two settings patterns exist and they are deliberately separate:

- **Owner-scoped, replicated, server-persisted** — `vocabularies` and `topics`. Defined in
  `pb_migrations/1787868000_acervo_core.js:57-95` with `ownerField()` and `syncFields`, written only
  through the hook, edited in `web/src/Configuration.tsx`. This is how account-level facts are stored.
- **Per-device, `localStorage`, never replicated** — `web/src/editorPreferences.ts`,
  `web/src/searchScope.ts`, and the disabled-dictionary set in `web/src/dictionaries.ts:60-91`. Each
  is a keys map, a `try`/`catch` read with a default, a setter that dispatches a `CustomEvent`, and a
  `use…` hook. This is how *this screen's* preferences are stored.

There is no settings or preferences collection: `pb_migrations/1787868000_acervo_core.js` creates
exactly nine collections and none of them is one. `sync_state` (`:41-51`) is the precedent that
matters here — it is owner-scoped, it is **not** replicated, and it is exempt from the no-uniqueness
rule because of that.

The closest existing surface to what this plan builds is `web/src/DictionaryPanel.tsx`: a tracked
catalogue rendered as rows, each with a switch, each reporting its own state, mounted into Settings
as one line at `Settings.tsx:173`.

## Decisions

### The choice is server state, not device state

A model choice is not like line numbers in the editor. It decides what the owner's vocabulary is
*made of* — which model wrote a definition, at what cost, to what quality — and an entry captured
from a phone should be built by the same model as one captured from a laptop. It also has to be
readable by the server at request time, because the server is what calls the model and the key never
leaves it.

So: a server-only, owner-scoped collection, non-replicated the way `sync_state` is. It is **not**
added to `REPLICATED` in `main.pb.js` and **not** added to the hook's `COLLECTIONS` graph array. It is
not vocabulary, it does not sync, and a client reads it through a route rather than out of the
replica.

The per-device alternative was considered and rejected for one specific reason beyond the above: the
server would then have to accept a provider id on every capture request, which makes the choice
something a headless transport can assert. An iOS Shortcut should not be able to pick a model.

### The cost is a database rebuild, and it is stated first

Adding a collection means changing the canonical bootstrap migration, and PocketBase records applied
migrations by filename, so an existing database ignores a rewritten one. `./deploy.sh
--reset-database` is the supported path and this plan's first implementation step is to export.

That is a real cost and it is worth naming why it is accepted rather than adding a second migration
file: the bootstrap migration is defined as canonical, and a schema assembled from a chain of
migrations is exactly the compatibility machinery this project prohibits.

### The route reports what the server can do, never how

`GET /api/acervo/v1/models` returns the catalogue rows the server holds credentials for, plus the
owner's current chain. It never returns a key, and never a base URL with a credential interpolated
into it. A row the server is *not* credentialed for is still listed, marked unavailable with the
reason — the same reason vocabulary plan 01 put on health — because "why can I not pick Cloudflare"
is a question the interface should answer without a shell.

### A chain, not a selection

The owner orders providers per kind rather than picking one. This is what makes the free tier usable:
`gemini-free` first, `cloudflare` behind it, and a day's 500 calls running out becomes a slower entry
rather than a stopped ingest.

Falling through is limited, per the locked contract: **429 and 5xx only.** An authentication failure
or a rejected configuration stops and is reported. Routing around a bad key hides the mistake and
spends money at the next provider, and the owner would find out from a bill.

### The entry records the model that answered

`draftFrom` already stamps `modelId` onto generated examples (`acervo.js:929`, `examples.model_id` in
the migration at `:182`). With a chain, that field must name the provider and model that actually
produced the text, not the one at the head of the list. Provenance is modelled, never flagged — an
example is not marked "fallback", it simply says what made it.

### One page, built like the dictionary page

Settings ▸ Models follows `DictionaryPanel.tsx` and `Configuration.tsx` exactly: rows from a
catalogue, an ordinary online-only write through the repository, failing loudly and changing nothing
locally when the server is unreachable. Reuse `config-section`, `config-help`, `config-switch` and
`config-row`. No new visual language, and the prototype in `design/ui-prototype/` changes in the same
commit as `styles.css` if either does.

## Implementation work

Rewritten on implementation: the version this replaces was written for PocketBase and named
`pb_migrations/`, `acervo.js` and `main.pb.js`, none of which survived [plan 08](08-the-python-server.md).

1. **`models/chain.py` gains `Choice`** — `str | tuple[str, str]`. A bare id is "this row, every
   model it offers for this kind"; a pair is "this row, exactly this model". The owner's record
   stores pairs and `ACERVO_TEXT_CHAIN` stores ids, and both must reach one resolver, because
   `walk()` and `unconfigured()` funnel through it.
2. **A `model_selection` table**, shaped like `sync_state`: owner FK, a unique index on `owner`, and
   no `revision`/`deleted`/`edited_by`, which is what makes it structurally unreplicable rather than
   merely unreplicated. `chains` is a JSON column holding exactly the document the route takes and
   returns. Adding it means renaming the Alembic head to `0002_bootstrap`, so an existing database
   refuses to serve rather than silently lacking the table — `--reset-database` is the deploy.
3. **`repository/model_selection.py`** with `chains(owner)` and `save(owner, changes)`. Nothing is
   created eagerly: no row means "follow the deployment default", which is a legitimate answer
   rather than a gap, so there is no `ensure_` function and no write on any read path. A new
   layering rule keeps the catalogue out of `repository/`, so validation has one home.
4. **`services/models.py`** — `chain_readout` is split out of `capture_health` so `/health` and
   `GET /models` cannot drift on "can this build entries"; `chain_for(settings, owner, kind)` is the
   precedence ladder, re-read per request.
5. **`owner` threads through capture** — `run_capture` already holds it. Required, with no default,
   so an omission is a `TypeError` rather than a silent fall to the deployment default.
6. **Two routes** in `api/routes/models.py`, registered in `app.py` before `static.install`.
7. **`web/src/ModelPanel.tsx`**, one section per kind, reusing `TopicEditor`'s arrows and
   `DictionaryPanel`'s switch. `api.ts` gains the two calls — **not** `repository.ts`, which owns the
   replica and nothing else; the external-dictionary list is the precedent.
8. **The General readout moves here**, as this plan always said. It is moved rather than duplicated:
   General read the *deployment's* provider from `/health`, and this pane reads the owner's chain.

## Public interfaces and data

`GET /api/acervo/v1/models` returns `providers` — each with `label`, `kinds`, `models` per kind,
`available`, `reason`, `usageUrl`, `notes` — and `chains`, one per kind:

```jsonc
{ "source": "owner",  "reason": null,
  "pairs": [{ "provider": "cloudflare", "model": "cloudflare/@cf/..." }] }
```

`source` lets the interface tell a saved order from the server's own. `pairs` is what is *stored*,
not what will be walked, so an uncredentialed pair keeps its place. `chains[kind].reason` comes from
the same producer `/health` uses, so a mistyped `ACERVO_TEXT_CHAIN` renders a reason instead of
failing the pane.

No key, no base URL, no project id. `usageUrl` *does* carry a `requires` value — Cloudflare's
account id is what makes the link point at the right dashboard — and that is why this route is
authenticated where `/health` is not.

`PUT /api/acervo/v1/models/selection` takes `{"chains": {"text": [...], "image": null}}`. Only the
kinds present change; `null` forgets one and returns it to the deployment default, without which a
single choice would be a one-way door. It answers with the same body `GET` returns. Refusals, all
400: `invalid_input`, `unsupported_kind`, `unknown_provider`, `unknown_model`, `duplicate_pair`,
`empty_chain`.

**No `provider_unavailable`** — see the amended contract in [README.md](README.md). **No
`schemaVersion`**: that number guards the replicated graph wire and its client twin decides whether
a replica is wiped; this route adds no field to any replicated record.

## Acceptance tests and verification

```bash
.venv/bin/python -m pytest
npm --prefix web run test && npm --prefix web run build
```

Server, in `tests/unit/server/test_models.py` and `test_capture.py`:

- no record → every kind `source: "deployment"`; an owner chain outranks `ACERVO_TEXT_CHAIN`; the
  env var still decides when there is no record
- the owner pins one model of a two-model row and it is the only one called
- a chain saved through the route decides the next capture **in the same process**
- 429 → the next pair answers and `modelId` names it; 401 → no fall-through, one call; exhausted →
  the last error
- a pair whose key is gone is skipped, and that kind can still be reordered
- a pair naming a model the catalogue no longer offers → `llm_configuration`, zero model calls
- one owner's chain is invisible to another
- not replicated: absent from `COLLECTIONS`, no `revision`/`deleted` column, and after a save the
  body of `GET /graph?since=0` contains neither the provider id nor the model string.
  `tables.REPLICATED` is declared and never read, so a test against it would prove nothing
- `/health` reports the deployment default while `GET /models` reports the owner's

Web, in `ModelPanel.test.tsx`: every model of a provider is selectable; an unavailable row renders
its reason and can still be switched on and reordered; one toggle is one write naming one kind;
switching the last one off sends `null` rather than an empty chain; the server's answer replaces
what was clicked; a refusal notifies and leaves the shown order alone.

Live, after `--reset-database`, `--create-account` and re-importing the bundle: reorder in
Settings ▸ Models, capture a word **without redeploying**, and confirm the entry's `modelId` names
the pair now at the head.

## Non-goals

- **No per-request model override.** The submitter may name the word (`headword`) but not the model.
  A headless transport asserting a model is a cost decision made by an iOS Shortcut.
- **No replication of the choice into the client replica.** It is server state read through a route.
  A client that cannot reach the server cannot capture anyway, because writes are online-only.
- **No per-vocabulary or per-topic model.** One chain per kind per owner. Nothing asks for more, and
  a Spanish-versus-Chinese model split is speculative until a specific model is worse at one.
- **No cost tracking or spend limits.** The catalogue's cost notes are documentation for a human
  making a choice, not a budget the server enforces. If that is ever wanted it is its own plan.
- **No automatic reordering.** The server does not learn that one provider is faster and promote it.
  The owner's order is the owner's order.
- **No retry within a row.** A 429 moves to the next provider rather than sleeping;
  `scripts/ingest_vocabulary_file.py:42-43` already owns the slow retry for bulk work, and a
  synchronous capture must not block for 60 seconds.
