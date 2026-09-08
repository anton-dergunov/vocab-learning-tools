# Plan 01: Unbreak capture and make the provider legible

**Status:** Planned.
**Depends on:** nothing. This is the first plan and the only one that can be done in an hour.

## Outcome

Words can be added again. And the class of failure that caused this — a provider configured, its key
absent, and nothing saying so until someone pressed the button — is no longer possible to reach
silently: the server reports what it is configured with and why it cannot build entries, and the
interface shows that instead of discovering it at the moment of use.

This plan does not redesign anything. It is a repair plus one missing readout.

## Current state

`llmSettings()` at `deploy/acervo/pocketbase/pb_hooks/acervo.js:521-535` resolves the provider from
six environment variables and reads **only the selected provider's key**:

```js
const provider = trimmed($os.getenv("ACERVO_LLM_PROVIDER")) || "gemini";
return {
  provider: provider,
  key: provider === "vertex"
    ? trimmed($os.getenv("VERTEX_API_KEY"))
    : trimmed($os.getenv("GEMINI_API_KEY")),
  model: trimmed($os.getenv("ACERVO_LLM_MODEL")) || "gemini-3.1-flash-lite",
  ...
};
```

Five facts, together, are the outage:

1. **`llm.env` wins.** `deploy/acervo/install.sh:319-323` and `deploy/acervo/run-worker.sh:60` pass
   `--env-file deployment.env --env-file secrets.env --env-file llm.env`, in that order, and the last
   file wins. So `ACERVO_LLM_PROVIDER=vertex` written once is durable and outranks everything.
2. **The unselected key is unreachable.** With vertex selected, the `GEMINI_API_KEY` that
   `install.sh:113-148` wrote into `secrets.env` is never read. An empty `VERTEX_API_KEY` then makes
   `captureAvailable()` (`acervo.js:537-542`) false and `llmJson()` throw
   `503 capture_unavailable` — "This Acervo server has no language model configured" — while a
   perfectly good Gemini key sits one file away.
3. **The Vertex key was probably never minted.** `vertex-remote-config.txt:175` records
   `gcloud services api-keys create --service-account …` failing with
   `FLOW_APIKEY_SERVICE_ACCOUNT_BINDING_PERMISSION_ERROR`, the organization policy
   `iam.managed.disableServiceAccountApiKeyCreation`. The file then prescribes an org-policy fix and
   **ends with the recipe, never with a confirmation that the key was created.**
4. **The prescribed model is wrong for the fallback.** That runbook configures
   `--llm-model gemini-3.7-flash`, and `deploy.sh:235` even defaults vertex to it. It is not a Gemini
   Developer API model id, so flipping the provider back to `gemini` without also correcting the
   model gives a 404, which `acervo.js:630-633` maps to `503 llm_configuration`. Two different
   failures that look the same from the outside.
5. **Nobody looks.** `GET /api/acervo/v1/health` already returns `capture: <bool>`
   (`acervo.js:1271-1280`), with a comment saying it exists "so the app can say why the button is off
   rather than failing at the moment someone finally uses it". Grepping the web application for
   `/health` finds nothing. Only `tests/integration/test_acervo_app_docker.py:143,162` reads it.

Two adjacent problems found while diagnosing, cheap to fix here:

- `install.sh:194-198` retains the *inactive* provider's key through an awk filter, but `llm.env`
  only ever receives the key for the provider being configured. So the retention only works if a
  `--llm-provider gemini` run put a Gemini key there first — which, given `secrets.env` was where it
  originally lived, it may never have.
- `vertex-remote-config.txt` is untracked but was **not** gitignored, in a public repository,
  carrying a personal Google account, a GCP project and organization id, and home paths. This is the
  same hazard `.gitignore` already documents for `ingest.sh` and `TODO.txt`.

## Decisions

### The repair comes before the readout, and the readout before any redesign

The recovery is one command. It is written out in full below so that it can be run without reading
the rest of this plan, and so that the same command works the next time this happens.

### A configuration that cannot work is reported as such, with the reason

`captureAvailable()` returning a bare boolean is why this outage was silent for as long as it was:
false could mean no key, the wrong key name, a missing Vertex project, or a model that does not
exist. Health gains a small object naming the provider, the model, and — when unavailable — which
specific thing is missing. The reason names an environment variable, never a value.

Deliberately **not** built here: no validation of the model id against a provider's live model list.
That needs a network call at health time, and health must answer when the model provider is
unreachable. The model id is checked for provider *plausibility* at configure time instead, in
`deploy.sh`, where a human is present to be told.

### `deploy.sh --configure-llm` refuses a model that cannot belong to the selected provider

The failure mode in fact 4 above is a shell-level mistake and belongs in the shell. A refusal at
configure time costs nothing; the same mistake discovered through a 404 costs a deployment cycle.

### Both keys always survive a switch

`llm.env` holds every key it has been given, and switching provider changes only
`ACERVO_LLM_PROVIDER`. Switching back must never require re-entering a credential. This is a
correctness fix, not a convenience: a switch that silently discards a working key is what turned a
Vertex experiment into an outage.

### The tracked instructions are corrected in this plan, not a later one

`AGENTS.md:157` described `src/vocabgen/provider/`, `llm/`, `tts/` and `vision/` as "reusable
provider abstractions". Nothing but tests imports them, and the live model calls happen in four other
places. That sentence is what made this work look smaller than it is, and
`PROJECT_SUMMARY.md:24-28` repeats it. The same section had no statement that the server runs
Acervo's own Python, which led to a design conversation being framed around a constraint that does
not exist.

## Implementation work

1. **Recover the deployment.** Reconfigure the server for the Gemini Developer API, correcting the
   model in the same call because `llm.env` retains the old one:

   ```bash
   ./deploy.sh \
     --configure-llm \
     --llm-provider gemini \
     --llm-model gemini-3.1-flash-lite \
     --llm-api-key-stdin
   ```

   Confirm with `curl -s https://acervo.example.com/api/acervo/v1/health` before touching any code.
   If `capture` is still false, the key was not accepted; if capture then fails at use with
   `llm_configuration`, the model id is wrong.

2. **`llmSettings()` reports rather than resolves silently** — `acervo.js:521-542`. Keep the same six
   environment variables and the same defaults; add a derived `reason` describing the first missing
   requirement (`GEMINI_API_KEY is not set`, `VERTEX_API_KEY is not set`,
   `ACERVO_VERTEX_PROJECT is not set`, `ACERVO_LLM_PROVIDER is not one of gemini, vertex`). Reason is
   `null` when the configuration is usable.

3. **Health carries it** — `acervo.js:1271-1280`. Replace the `capture: <bool>` field with the object
   in `## Public interfaces and data` below. This is a breaking change to the health response and
   that is fine: backward compatibility is prohibited, and the only existing reader is
   `tests/integration/test_acervo_app_docker.py:143,162`, which is updated with it.

4. **The interface reads health.** Two places, both small:
   - **Add view** (`web/src/AddView.tsx`): when capture is unavailable, say so where the Capture
     control is, naming the model the server is configured with and the reason. The control is
     disabled with a reason rather than live and failing.
   - **Settings ▸ General** (`web/src/Settings.tsx:122-143`): one `update-status` block beside the
     existing version and update lines, reporting the provider and model this server builds entries
     with. This is the row that plan 03 later turns into a chooser, so put it where that will live.

   Fetch it alongside the existing release check in `web/src/macRelease.ts`'s pattern — health is a
   server fact, cached for the session, and its absence must not block startup, because reads are
   offline-first.

5. **`install.sh` keeps every key** — `deploy/acervo/install.sh:159-209`. The awk filter at
   `:194-198` strips the four `ACERVO_LLM_*` settings and rewrites them; change it to strip *only*
   those settings and the key currently being supplied, leaving every other `*_API_KEY` line intact.
   On first configuration, migrate `GEMINI_API_KEY` out of `secrets.env` into `llm.env` so there is
   one place a model credential lives.

6. **`deploy.sh` refuses an implausible model** — `deploy.sh:222-263`. Reject a `--llm-model` that
   cannot belong to `--llm-provider`, with a message naming both and suggesting the provider's
   default. Keep the refusal to combine `--configure-credentials` with `--configure-llm`.

7. **Correct the tracked instructions.** `AGENTS.md` Architecture gains a statement that Python is
   the server language and that the hook request path is the one place it cannot run; the stale
   "reusable provider abstractions" bullet is replaced with what is actually live and a pointer to
   `docs/plans/`. `PROJECT_SUMMARY.md:24-28` gets the same correction.

8. **Ignore the runbook file.** Add `/vertex-remote-config.txt` to `.gitignore` beside `/ingest.sh`
   and `/TODO.txt`, with the same explanatory comment. Then move it out of the working tree entirely —
   it is an operational note about a personal Google account and does not belong in a product
   checkout at all.

## Public interfaces and data

`GET /api/acervo/v1/health` — the `capture` field changes shape:

```jsonc
{
  "name": "Acervo",
  "version": "1.4.2",
  "build": "218",
  "schemaVersion": 6,
  "capture": {
    "available": false,
    "provider": "vertex",
    "model": "gemini-3.7-flash",
    // null when available; otherwise names the missing requirement, never a value
    "reason": "VERTEX_API_KEY is not set"
  }
}
```

The response still contains no key, no endpoint and no project id. `provider` and `model` are
identifiers the owner chose and needs to see; a project id is a deployment detail and stays server-side.

`llmSettings()` return shape gains one field:

```js
{ provider, key, model, geminiEndpoint, project, location, reason /* string | null */ }
```

## Acceptance tests and verification

```bash
npm run test:hooks            # the capture hook against stubbed PocketBase globals
npm --prefix web run test
npm --prefix web run build
.venv/bin/python -m pytest tests/unit -k "privacy or deployment"
```

New hook cases in `tests/hooks/capture.test.mjs`, alongside the existing Gemini and Vertex request
assertions at `:383-416`:

- vertex selected with no `VERTEX_API_KEY` → health reports `available: false` and the reason names
  `VERTEX_API_KEY`, and capture still refuses with `503 capture_unavailable`
- vertex selected with a key but no project → the reason names `ACERVO_VERTEX_PROJECT`
- an unknown `ACERVO_LLM_PROVIDER` → the reason names the variable and lists the accepted values
- gemini selected with a key → `available: true`, `reason: null`, and the request is unchanged from
  what `:383-395` already asserts

Shell cases in the deployment tests:

- configuring gemini after vertex leaves `VERTEX_API_KEY` in `llm.env`, and configuring vertex after
  gemini leaves `GEMINI_API_KEY` — assert both directions
- `--llm-provider gemini --llm-model gemini-3.7-flash` is refused, naming both

End to end, against the live server:

```bash
curl -s https://acervo.example.com/api/acervo/v1/health | python -m json.tool
#  · capture.available true, and provider/model are what was just configured

# then, in the app: Add ▸ paste a sentence ▸ Capture
#  · an entry is proposed and can be saved
#  · Settings ▸ General names the provider and model that built it

# and with the key deliberately removed:
#  · the Capture control is disabled with a reason before it is pressed, not after
```

```bash
git check-ignore -v vertex-remote-config.txt   # must print a .gitignore rule
grep -n -i 'Python is the server language' AGENTS.md
```

## Non-goals

- **No provider is added.** The catalogue, the second wire shape and Cloudflare are plan 02. This
  plan keeps `gemini|vertex` exactly as it is and only stops them failing quietly.
- **No selection UI.** Settings ▸ General reports; it does not choose. Choosing is plan 03, which
  needs the catalogue first.
- **No model-id validation against a live provider.** Health must answer while the model provider is
  unreachable. Plausibility is checked at configure time instead.
- **No change to the error taxonomy.** `llm_authentication`, `llm_configuration`,
  `llm_rate_limited`, `llm_unavailable`, `llm_unreachable`, `llm_failed`, `llm_empty` and
  `llm_unusable` keep their meanings, because `scripts/ingest_vocabulary_file.py:42-43` retries on
  exactly three of them.
- **No attempt to make Vertex work.** Whether that key was ever minted, and whether Vertex text is
  worth keeping at all, is the spike that opens plan 02.
