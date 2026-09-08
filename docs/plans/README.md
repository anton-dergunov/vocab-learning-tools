# Model providers — remaining-work roadmap

Acervo generates text, images and audio. Today each of those reaches a model through a different,
unrelated mechanism, and the layer that looks like the abstraction is dead code. These plans replace
all of it with one catalogue of providers, one Python package that calls them, and one place in
Settings where the owner chooses which one answers.

The immediate reason this exists is that capture is broken: a Vertex provider was configured, the
Vertex key was probably never successfully minted, and because `llm.env` outranks `secrets.env` the
working Gemini key became dead weight. Plan 01 fixes that on its own, before any of the redesign.

## How to use these plans

1. Take the first plan marked `Planned` whose dependencies are all `Complete`. Do not work ahead:
   later plans assume the contracts earlier ones lock.
2. Re-read the current implementation before starting. These documents were written on 2026-09-08
   and every file reference in them is a claim about that day, not a guarantee about today.
3. Implement the whole acceptance boundary of one plan. A plan that is half done is worse than one
   not started, because the next plan will build on a contract that does not hold.
4. Run the plan's own `## Acceptance tests and verification` section, then update both the plan's
   `**Status:**` line and this index's table in the same change.
5. Append an `## Implementation and verification record` to the plan when it is finished, saying what
   was actually built and what the verification actually printed.

## Pragmatism rule

Build the smallest thing that satisfies the plan. No speculative abstraction: a provider is a row of
data until something proves it needs to be code. A library named in a plan is a researched starting
point with its coverage and cost noted, not a commitment — if it turns out not to fit, say so in the
implementation record and write the twenty lines instead.

The specific temptation to resist here is a provider framework. The call Acervo makes is "pass text,
get output", sometimes constrained to a JSON schema. There is no caching, no streaming, no
conversation state, no tool use. Anything grander than that is not being paid for by a requirement.

## Ordered plans

### Stage 1 · Get working again, and make the configuration legible

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [01 · Unbreak capture and make the provider legible](01-unbreak-capture-and-make-the-provider-legible.md) | Planned | — | Words can be added again, and a misconfigured model is visible before the button is pressed rather than after |

### Stage 2 · One provider model

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [02 · One wire shape and one catalogue](02-one-wire-shape-and-one-catalogue.md) | Planned | 01 | A text provider is a row in `models/catalogue.json`; the hook carries two request builders instead of a growing switch |
| [03 · The owner chooses a model](03-the-owner-chooses-a-model.md) | Planned | 02 | Settings ▸ Models picks the provider chain per kind; it takes effect on the next capture with no restart |
| [04 · One Python provider package](04-one-python-provider-package.md) | Planned | 02 | `src/vocabgen/models/` is the single Python way to call a model, over LiteLLM; the dead layer is deleted |

### Stage 3 · The other two kinds

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [05 · Images through the catalogue](05-images-through-the-catalogue.md) | Planned | 04 | The sense-image pipeline stops hardcoding Vertex; Cloudflare FLUX.2 Klein becomes the steady-state row |
| [06 · Audio through the catalogue](06-audio-through-the-catalogue.md) | Planned | 04 | Expressive and plain pronunciation are two distinct jobs with their own providers, and the graph has somewhere to put audio |

### Stage 4 · Where local models could run

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [07 · The NAS → MacBook job queue](07-nas-to-mac-job-queue.md) | Planned (sketch only) | 04 | The shape of an answer to "the always-on machine has no GPU and the GPU machine is not always on", deliberately not designed further |

## Locked cross-plan contracts

These are decided. A plan may not quietly change one; changing one is its own change, applied to
every plan that names it.

**A provider is a row, not a class.** `models/catalogue.json` is tracked, ships the *list* and never
a secret, and is the only place a provider's endpoint and model id are written down. It is read by
both `pb_hooks/acervo.js` and Python, so **the catalogue schema is described twice** — exactly as the
dictionary artifact format is described in `container.py` and `dictionary.ts`, and with the same
consequence: a change to either description is a change to both, and the paired tests exist to catch
the day they disagree.

**The hook carries two wire shapes, and only two.** `openai` covers the Gemini Developer API,
Cloudflare Workers AI, OpenAI, OpenRouter, Groq, Ollama and any local OpenAI-compatible server.
`google` covers Vertex's native `generateContent`, which is kept because Vertex's OpenAI-compatible
endpoint authenticates with a Bearer OAuth access token rather than an API key, and minting one in
goja means RS256-signing a JWT. **Needing a third shape is the signal to move the model call out of
the hook into Python behind a route, not to add a third branch.**

**Python is where breadth lives.** Anything asynchronous or batched — every image, every audio clip,
every bulk ingest — is Python in `acervo-worker`. Only work that must answer inside a request is
JavaScript in a hook.

**A chain falls through on 429 and 5xx, and never on anything else.** An authentication failure or a
rejected configuration is a mistake to fix, not a condition to route around; falling through on it
hides the mistake and spends money elsewhere. Fall-through is per kind, in the owner's stated order.

**The model that answered is recorded, not the model that was asked.** Provenance is modelled, never
flagged: whatever provider actually produced an example is what lands in `modelId`. A fall-through
that leaves `modelId` naming the first choice is a bug.

**Ids stay 15 lowercase alphanumerics**, minted client-side, unchanged everywhere. Nothing in this
work introduces a second id format, and a catalogue row id is not a record id.

**Secrets never enter a tracked file, a client response, or a command argument.** Keys live in the
mode-600 key file on the server. `GET /api/acervo/v1/models` returns what the server is credentialed
*for*, never the credential, and never a base URL with a key embedded in it.

## Original-request coverage

Every provider and capability named in the request that started this work, and where it is answered.

| Asked for | Plan |
|---|---|
| Gemini free tier for text — the daily driver, 500 free calls | 01, 02 |
| Vertex for text, when speed matters and credits last | 01 (diagnose), 02 (keep the native path) |
| Cloudflare Workers AI for text | 02 |
| OpenAI for text | 02 |
| Self-hosted and local text models (Ollama, on-device) | 02 (the row), 07 (where it runs) |
| Vertex and Gemini for images — the ones that worked well | 05 |
| Cloudflare for images, for when the Vertex credits run out | 05 |
| Other image providers (OpenAI and the popular ones) | 05 |
| Gemini for audio, because it follows the intonation | 06 |
| Cloudflare for audio | 06 |
| Local models for plain pronunciation | 06 |
| Choosing the model from the interface | 03 |
| Swapping provider without restarting the server | 03 |
| Using an existing provider-agnostic package rather than writing one | 04 (LiteLLM, with its coverage gaps stated) |
| Fixing capture, which is broken right now | 01 |
| A queue that offloads GPU work from the NAS to the MacBook | 07 |

Deliberately out of scope, and why:

- **Whisper and speech-to-text of any kind.** Named in the request as out of topic. It would be a
  fourth kind with its own record shape and no consumer; when it is wanted it gets its own plan.
- **Importing the ~2,000 images already generated under Vertex.** A real job and a wanted one, but it
  is a data-import task, not a provider task. Plan 05 says where those images land so that the import
  has a target; it does not do the import.
- **Streaming, caching, tool use, conversation state.** Nothing asks for them.
