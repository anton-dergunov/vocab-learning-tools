# Plan 02: One wire shape and one catalogue

> **SUPERSEDED by [08 · The Python server](08-the-python-server.md), 8 Sep 2026.**
>
> This plan's central contract — *"the hook carries two wire shapes, and only two"* — assumed the
> hook keeps calling models. It does not: `pb_hooks/` is being deleted. The roadmap flagged the
> contract as contested before any of this was built, and it is now settled the other way.
>
> **What dies with it:** the two request builders, the goja constraint that forced Vertex's native
> `generateContent` to stay (RS256-signing a JWT is ordinary work in Python), and — the real prize —
> the rule that *the catalogue schema is described twice*. In one language it is described once, and
> the paired tests guarding the two descriptions are not needed.
>
> **What survives, and moves into [04](04-one-python-provider-package.md):** the catalogue as a row
> of data rather than a class; the row schema and its `capabilities` declaration; the `keyEnv`
> indirection and the rule that a `baseUrl` never embeds a key; the deployment work (generalising
> `install.sh`'s `gemini|vertex` whitelist and `deploy.sh`'s default model ids, and packaging
> `models/` into the release bundle); and the LLM status → error-code taxonomy, which is a contract
> because the file ingestion retries on exactly three of its codes.
>
> Kept for its diagnosis of the current state and its provider research. Do not implement it.

**Status:** Superseded.
**Depends on:** [01](01-unbreak-capture-and-make-the-provider-legible.md) — capture must be working
and health must be legible before the request builder is touched.

## Outcome

A text provider stops being a branch in the code and becomes a row of data. Adding Cloudflare,
OpenAI, OpenRouter, Groq or a local Ollama server is an entry in `models/catalogue.json` and a key in
the server's key file — no JavaScript, no Python, no deployment-script change. The hook carries two
request builders, permanently, and the reason there are two rather than one is written down.

## Current state

`llmJson()` at `deploy/acervo/pocketbase/pb_hooks/acervo.js:585-662` is one function with a boolean
provider branch:

```js
const vertex = settings.provider === "vertex";
const url = vertex
  ? "https://aiplatform.googleapis.com/v1/projects/" + encodeURIComponent(settings.project)
    + "/locations/" + encodeURIComponent(settings.location)
    + "/publishers/google/models/" + encodeURIComponent(settings.model) + ":generateContent"
  : settings.geminiEndpoint.replace(/\/+$/, "") + "/v1beta/models/"
    + encodeURIComponent(settings.model) + ":generateContent";
const generationConfig = { responseMimeType: "application/json" };
if (vertex) generationConfig.thinkingConfig = { thinkingLevel: "MEDIUM" };
else generationConfig.temperature = 0.2;
```

Both arms are Google-shaped and both authenticate with `x-goog-api-key`. Adding a third provider
means a third arm and a third set of response-parsing rules, and the parsing below it
(`:644-661` — skip `parts[i].thought`, unfence, `JSON.parse`) is written against Google's response
envelope specifically.

The same knowledge is duplicated across four files that do not know about each other:
`compose.yaml:16-21` and `:84-89` list six environment variables; `install.sh:175` whitelists the
string `gemini|vertex`; `install.sh:183-191` hardcodes the two key names; `deploy.sh:235` hardcodes
the two default model ids. Adding a provider today means editing all four plus the hook.

`config/image-providers.example.yaml` already sketches the registry this plan builds —
`default_provider`, `providers: {<id>: {provider, options}}`, `*_env` indirection for credentials,
and a `fallback_order`. It is loaded by nothing and has never run.

## Decisions

### Two wire shapes, and only two, and here is why

Almost every provider worth having speaks OpenAI's `/chat/completions`, including the ones Google
runs. One builder covers:

| Row | Base URL |
|---|---|
| Gemini Developer API | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Cloudflare Workers AI | `https://api.cloudflare.com/client/v4/accounts/<id>/ai/v1` |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Ollama, or any local server | `http://host:11434/v1` |

**Vertex is the exception, and it is a hard one.** Vertex does publish an OpenAI-compatible endpoint
at `.../locations/<loc>/endpoints/openapi/chat/completions`, but it authenticates with a Bearer OAuth
access token — `credentials.token` from Google's auth libraries — not with an API key. Minting one
from a service account means RS256-signing a JWT and exchanging it, inside goja, which is an ES5-ish
engine with no crypto library. So Vertex keeps the native `generateContent` path it already has,
reached with the restricted `x-goog-api-key` it already uses.

That gives the hook exactly two builders: `openai` and `google`. **A third is not permitted.**
Needing one means the hook has outgrown being a request builder, and the answer at that point is to
move the model call into Python behind a route — where LiteLLM already handles the breadth — not to
add a branch. Write that trigger into the code comment, not only here.

### Spike before building: is Vertex text reachable at all?

Plan 01 leaves an open question that changes this plan's shape. `vertex-remote-config.txt:175`
records the Vertex API key creation failing on an organization policy and never confirms it later
succeeded. Before writing the `google` builder into the catalogue design, establish which of these is
true:

- **The key exists and works.** Keep the `google` wire shape as designed above.
- **The key does not exist and the org policy still blocks it.** Then Vertex text from the hook is
  not reachable at all, and the honest move is to drop the `google` wire shape from the hook
  entirely, leaving one builder, and reach Vertex only from Python (plan 04), where ADC works and
  `images/preflight.py:37` already does it. **This is the better outcome if it is available** — one
  wire shape in the hook is strictly simpler than two.

Do the spike first. It is a `curl` and a `gcloud services api-keys list`, and it decides whether this
plan ships one builder or two.

### A row carries capability, not just an address

Providers genuinely differ in ways the caller must know about, and pretending otherwise is what makes
abstractions leak. A row therefore declares what it supports rather than being assumed uniform: does
it accept a JSON schema natively, or must the schema go in the prompt and be validated afterwards;
does it take a thinking budget; what does it cost. This is the one idea worth borrowing from the
`BackendCapabilities` table in `earworms_generator`'s `lexibeat/voice.py` — a declaration, not a
class hierarchy.

Kept deliberately small: a handful of boolean and enum fields, no per-provider code. If a row ever
needs behaviour rather than declaration, that is a signal the provider does not belong in the hook.

### The catalogue is described twice, on purpose

`acervo.js` reads it, and Python (plan 04) reads it. That is the same arrangement the dictionary
artifact format has in `container.py` and `dictionary.ts`, and it carries the same obligation: **a
change to either description is a change to both**, with a pair of tests whose whole job is to fail
on the day they disagree.

The alternative — one description, in Python, served to the hook — means the hook cannot build a
request without a second service being up, and capture is synchronous. Not worth it for a file that
changes a few times a year.

### Secrets stay out, and stay out of arguments

The catalogue names a key's environment variable; it never contains a key. The server's key file
keeps mode 600 and its values keep arriving over stdin, never as command arguments where they would
reach shell history and process listings.

## Implementation work

1. **Run the Vertex spike** and record the answer in this document before step 2. It decides whether
   the hook ends up with one builder or two.

2. **Write `models/catalogue.json`**, at the repository root beside `dictionaries/`, with the schema
   in `## Public interfaces and data`. Seed it with `gemini-free`, `cloudflare`, `openai`,
   `openrouter`, `ollama-local`, and `vertex` if the spike says it is reachable. Costs and free-tier
   limits go in the row as documentation for the chooser in plan 03 — the numbers in
   `docs/image-generation-research.md` are the source for the image rows later.

3. **Replace the branch in `llmJson()`** — `acervo.js:585-662`. The function takes a resolved
   catalogue row, dispatches on `row.wire` to one of two builders, and keeps everything below
   unchanged in meaning:
   - the status mapping at `:625-643`, because `scripts/ingest_vocabulary_file.py:42-43` retries on
     exactly `llm_rate_limited`, `llm_unavailable` and `llm_unreachable`
   - the `thought`-part skip at `:648-655`, which moves into the `google` response reader
   - `unfenced()` and the `JSON.parse` failure mapping to `llm_unusable`, which stay shared — models
     wrap JSON in fences regardless of wire shape

   The `openai` reader takes `choices[0].message.content`. JSON mode is `response_format:
   {"type":"json_object"}` where the row declares native support, and prompt-side instruction plus
   post-parse validation where it does not.

4. **Load the catalogue in the hook.** Copy it into the image the way `prompts/` is copied
   (`deploy/acervo/pocketbase/Dockerfile:20-22`), read it through a cached reader like
   `promptText()` at `acervo.js:561-576`, and give it its own `ACERVO_MODELS_PATH` with the same
   default-under-`/pb/pb_hooks` shape. It is content, not code, exactly as the prompts are.

5. **Generalize the deployment scripts.** `install.sh:175`'s `gemini|vertex` whitelist becomes "an id
   present in the catalogue"; `install.sh:183-191`'s two hardcoded key names become "the `keyEnv` the
   row names"; `deploy.sh:235`'s two default model ids come from the row's `defaultModel`. The key
   file holds one entry per credentialed row and, per plan 01, keeps every key it has been given.

6. **Package it.** Add `models/` to the archive in `scripts/package_acervo_server.sh:18` beside
   `prompts`, and keep the key file excluded as `llm.env` already is at `:20`.

7. **Pair the two descriptions.** `tests/hooks/catalogue.test.mjs` and, later,
   `tests/unit/models/test_catalogue.py` load the same file and assert the same invariants: every row
   has the required fields, every `wire` is one of the two known shapes, every `keyEnv` is referenced
   by the deployment scripts, and no row contains anything that looks like a secret.

## Public interfaces and data

`models/catalogue.json` — tracked, no secrets, read by both the hook and Python:

```jsonc
{
  "version": 1,
  "note": "Acervo ships the list of providers, never a credential and never a model.",
  "providers": [
    {
      "id": "gemini-free",
      "label": "Gemini (free tier)",
      "kinds": ["text", "image", "audio"],
      "wire": "openai",
      "baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai",
      "keyEnv": "ACERVO_KEY_GEMINI",
      "defaultModel": { "text": "gemini-3.1-flash-lite" },
      "capabilities": { "jsonSchema": "native", "thinking": "native" },
      "limits": { "note": "500 requests a day at no cost; 429 when exhausted" }
    },
    {
      "id": "vertex",
      "label": "Vertex AI",
      "kinds": ["text", "image"],
      "wire": "google",
      "keyEnv": "ACERVO_KEY_VERTEX",
      "requires": ["ACERVO_VERTEX_PROJECT", "ACERVO_VERTEX_LOCATION"],
      "defaultModel": { "text": "gemini-3-flash" },
      "capabilities": { "jsonSchema": "native", "thinking": "native" }
    },
    {
      "id": "cloudflare",
      "label": "Cloudflare Workers AI",
      "kinds": ["text", "image", "audio"],
      "wire": "openai",
      "baseUrl": "https://api.cloudflare.com/client/v4/accounts/{ACERVO_CLOUDFLARE_ACCOUNT_ID}/ai/v1",
      "keyEnv": "ACERVO_KEY_CLOUDFLARE",
      "requires": ["ACERVO_CLOUDFLARE_ACCOUNT_ID"],
      "capabilities": { "jsonSchema": "prompt", "thinking": "unsupported" },
      "notes": "Image models need multipart/form-data and are not reachable over this wire shape."
    }
  ]
}
```

Field meanings, which are the half of the contract the schema cannot carry:

- `wire` — `"openai"` or `"google"`. The **only** two values, ever. See the locked contract in
  `README.md`.
- `kinds` — which of text, image and audio this provider can serve. The hook only ever resolves
  `text`; Python resolves all three.
- `keyEnv` / `requires` — names of environment variables, never values. `requires` is what
  `captureAvailable()` checks beyond the key.
- `capabilities.jsonSchema` — `"native"` (send `response_format`), `"prompt"` (instruct in the prompt
  and validate the parsed result), or `"unsupported"`.
- `baseUrl` may interpolate a `requires` variable, as Cloudflare's account id shows. It may never
  interpolate a `keyEnv`: a key does not belong in a URL.

## Acceptance tests and verification

```bash
npm run test:hooks
.venv/bin/python -m pytest tests/unit -k "privacy or deployment"
npm --prefix web run build
```

Hook cases, replacing and extending `tests/hooks/capture.test.mjs:383-416`:

- an `openai`-wire row builds `POST {baseUrl}/chat/completions` with `Authorization: Bearer <key>`,
  a `messages` array carrying the system and user prompts, and `response_format` present only when
  the row declares `jsonSchema: "native"`
- a `google`-wire row builds the unchanged `generateContent` URL with `x-goog-api-key` — byte for
  byte what `:396-416` asserts today, so the existing Vertex behaviour is pinned, not rewritten
- an `openai` response with fenced JSON in `choices[0].message.content` parses
- a `google` response whose first part is `thought: true` skips it, as `:648-655` does today
- a row whose `requires` variable is unset reports unavailable with that variable named (plan 01's
  contract, now driven by the row)
- an unknown `wire` value is refused at load time, not at request time

Live, after deploying:

```bash
# one capture per wire shape, same word, and compare the entries
#  · gemini-free  → an entry is proposed, and modelId names the gemini model
#  · cloudflare   → an entry is proposed, and modelId names the cloudflare model
#  · vertex       → only if the spike said the key exists

# and the thing that proves this plan worked: add a provider without touching code
#  · append a row for a local Ollama server to models/catalogue.json
#  · ./deploy.sh --configure-llm --llm-provider ollama-local --llm-model qwen3:8b
#  · capture a word against it
```

## Non-goals

- **No third wire shape**, now or later. That is the locked contract and the trigger to move the call
  into Python instead.
- **No selection UI and no fallback chain.** The catalogue is the vocabulary this plan establishes;
  choosing from it and falling through it is plan 03.
- **No image or audio calls from the hook.** Rows declare `kinds` because Python needs the field;
  the hook resolves `text` and nothing else. Cloudflare's image models need multipart, which is
  reason enough on its own.
- **No LiteLLM here.** It is a Python library and the hook is not Python. LiteLLM enters in plan 04
  and reads the same catalogue.
- **No streaming, no tool use, no conversation state.** Capture is two one-shot calls and stays that.
- **No retirement of `config/image-providers.example.yaml` yet.** It is superseded by this catalogue
  but is deleted in plan 05, where its `fallback_order` idea actually lands.
