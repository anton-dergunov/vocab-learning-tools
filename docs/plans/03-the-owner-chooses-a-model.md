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

**Status:** Planned (re-aimed).
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

1. **Export first.** `Settings ▸ Data ▸ Export` before anything else in this plan. The reset is
   destructive and this is the only warning that matters.

2. **Add the collection** to `pb_migrations/1787868000_acervo_core.js`, beside `sync_state` at
   `:41-51` and shaped like it: owner relation with `cascadeDelete`, all five API rules `null` so the
   hook is the only writer, and — being non-replicated — no `syncFields` and no `revision`. One
   record per owner.

3. **Do not replicate it.** Confirm it is absent from `REPLICATED` in `main.pb.js:1`, absent from
   `COLLECTIONS` in `acervo.js:127-148`, and therefore absent from `ownerGraph`. A test should assert
   its absence, because the failure mode is silent: it would simply start appearing in every client's
   replica.

4. **Two routes** in `dispatch()` at `acervo.js:1266-1383`, beside the existing `/health`:
   - `GET /models` — owner-scoped, returns the shape below
   - `PUT /models/selection` — owner-only, validates every id against the catalogue and every kind
     against `kinds`, refuses an empty chain, writes the record

5. **Resolve a chain, not a setting.** Replace the single-row resolution from plan 02 with an ordered
   walk: for each row in the chain for `text`, build the request; on 429 or 5xx continue to the next;
   on anything else stop and throw as today. Exhausting the chain reports the *last* error, because
   that is the one the owner can act on. Stamp the answering row's model into `modelId` at
   `acervo.js:1096` / `draftFrom` `:929`.

   The chain is re-read from the collection per request, which is what makes a change take effect
   with no restart. It is one indexed read against a local SQLite file; do not cache it.

6. **`web/src/api.ts`** gains the two calls; **`web/src/repository.ts`** gains the write, because
   interface code reads and writes only through `AcervoRepository`.

7. **Settings ▸ Models** — a new `ModelPanel.tsx` beside `DictionaryPanel.tsx`, and one entry in the
   `pages` array at `Settings.tsx:94-102` plus one line in the body. Each row shows the provider, the
   model it will use, its cost or free-tier note from the catalogue, and — when unavailable — the
   reason. Reordering is the interaction; a row the server has no key for cannot be ordered into a
   chain.

8. **Fold plan 01's General readout into this page.** The provider-and-model line added to Settings ▸
   General in plan 01 was placed there so that it could become this. Move it, do not duplicate it.

## Public interfaces and data

`GET /api/acervo/v1/models`:

```jsonc
{
  "schemaVersion": 7,
  "providers": [
    {
      "id": "gemini-free",
      "label": "Gemini (free tier)",
      "kinds": ["text", "image", "audio"],
      "model": { "text": "gemini-3.1-flash-lite" },
      "available": true,
      "reason": null,
      "note": "500 requests a day at no cost; 429 when exhausted"
    },
    {
      "id": "cloudflare",
      "label": "Cloudflare Workers AI",
      "kinds": ["text", "image", "audio"],
      "model": { "text": "@cf/meta/llama-4-scout-17b" },
      "available": false,
      "reason": "ACERVO_KEY_CLOUDFLARE is not set"
    }
  ],
  "chains": {
    "text":  ["gemini-free", "cloudflare"],
    "image": ["vertex", "cloudflare"],
    "audio": ["gemini-free"]
  }
}
```

No key, no base URL, no project id. `reason` names an environment variable and never a value.

`PUT /api/acervo/v1/models/selection`:

```jsonc
{ "chains": { "text": ["cloudflare", "gemini-free"] } }
```

Only the kinds present are changed. Refusals: `unknown_provider` naming the id, `unsupported_kind`
when a row does not declare that kind, `provider_unavailable` when the server holds no credential for
it, `empty_chain`. All 400s — this is a bad request, not a model failure.

The collection, one record per owner:

```jsonc
{
  "id": "…15 lowercase alphanumerics…",
  "owner": "…users id…",
  "chains": { "text": [...], "image": [...], "audio": [...] },
  "edited_at": "2026-09-08T10:04:00Z"
}
```

No `revision`, no `deleted`: it is never replicated, so there is nothing to order against and no
tombstone to keep.

## Acceptance tests and verification

```bash
.venv/bin/python -m pytest tests/unit/server
npm --prefix web run test
npm --prefix web run build
npm run test:mac
RUN_DOCKER_INTEGRATION_TESTS=true .venv/bin/python -m pytest tests/integration/test_acervo_app_docker.py
```

Hook cases:

- `GET /models` for an owner with no record returns the deployment default as the chain
- `GET /models` never returns a string matching a configured key value — assert on the whole response
  body, not on named fields, because the failure this guards against is a field added later
- `PUT` with an unknown id, an unsupported kind, an uncredentialed provider, and an empty chain each
  refuse with the right code
- an owner's chain is invisible to another owner
- **the collection is not in `REPLICATED` and not in `COLLECTIONS`** — assert absence explicitly
- first row 429s → the second answers, and `modelId` names the *second* row's model
- first row 500s → same
- first row 401s → **no fall-through**, `llm_authentication` is thrown, nothing is created
- the chain is exhausted → the last error is reported, not the first

Web cases in `ModelPanel.test.tsx`, following `DictionaryPanel.test.tsx`:

- an unavailable row renders its reason and cannot be ordered into a chain
- reordering issues one repository write
- the server being unreachable fails loudly and leaves the displayed order unchanged

Live, and this is the test that matters:

```bash
# after ./deploy.sh --reset-database and re-creating the account:
#  · Settings ▸ Models lists every catalogue row, with the uncredentialed ones marked
#  · put cloudflare first, save
#  · Add ▸ capture a word — WITHOUT redeploying or restarting anything
#  · the entry's examples carry a cloudflare modelId
#  · put gemini-free first, capture again, and modelId changes with no restart

# and the fall-through, on the real free tier:
#  · exhaust the day's Gemini quota, or point the row at a bad model to force a 4xx
#  · a 429 produces an entry from the second provider
#  · a bad key produces a refusal naming authentication, and no entry
```

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
