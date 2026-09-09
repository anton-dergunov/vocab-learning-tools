# Model providers — remaining-work roadmap

Acervo generates text, images and audio. Each of those reached a model through a different,
unrelated mechanism, and the layer that looked like the abstraction was dead code. These plans
replace all of it with one catalogue of providers, one Python package that calls them, and one place
in Settings where the owner chooses which one answers.

The roadmap started as provider work and grew a foundation underneath it. Plan 01 fixed a broken
capture — a Vertex provider configured against a key that was probably never minted, with a working
Gemini key made dead weight because `llm.env` outranks `secrets.env`. Writing plan 02 then surfaced
the real obstacle: the model call lived in a goja hook, and every constraint the provider design was
bending around came from that sandbox rather than from the problem. **[Plan 08](08-the-python-server.md)
removes the sandbox**, and the provider work follows it rather than working around it.

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
| [01 · Unbreak capture and make the provider legible](01-unbreak-capture-and-make-the-provider-legible.md) | Complete | — | Words can be added again, and a misconfigured model is visible before the button is pressed rather than after |

### Stage 2 · The foundation

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [08 · The Python server](08-the-python-server.md) | **Complete** | — | PocketBase and `pb_hooks/` are deleted; one FastAPI service serves the same wire contract, the client did not change, and every job writes the graph through one client |

### Stage 3 · One provider model

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [02 · One wire shape and one catalogue](02-one-wire-shape-and-one-catalogue.md) | **Superseded** by 08 | — | Kept for its diagnosis and provider research. Its surviving content moved into 04 |
| [04 · One Python provider package](04-one-python-provider-package.md) | **Complete** | 08 phase 2 | `src/acervo/models/` is the single way to call a model, for the request path and batch alike, over LiteLLM |
| [03 · The owner chooses a model](03-the-owner-chooses-a-model.md) | **Complete** | 04 | Settings ▸ Models picks the provider chain per kind; it takes effect on the next capture with no restart |

### Stage 4 · The other two kinds

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [05 · Images through the catalogue](05-images-through-the-catalogue.md) | Planned, **unblocked** | 04 | The sense-image pipeline stops hardcoding Vertex; Cloudflare FLUX.2 Klein becomes the steady-state row |
| [06 · Audio through the catalogue](06-audio-through-the-catalogue.md) | Planned, **unblocked** | 04 | Expressive and plain pronunciation are two distinct jobs with their own providers, and the graph has somewhere to put audio |

### Stage 5 · Where local models could run

| Plan | Status | Depends on | Outcome |
|---|---|---|---|
| [07 · The NAS → MacBook job queue](07-nas-to-mac-job-queue.md) | Planned (sketch only) | 04 | The shape of an answer to "the always-on machine has no GPU and the GPU machine is not always on", deliberately not designed further |

## Locked cross-plan contracts

These are decided. A plan may not quietly change one; changing one is its own change, applied to
every plan that names it.

> **The contested contract is settled.** "The hook carries two wire shapes, and only two" assumed the
> hook keeps calling models. It does not: [plan 08](08-the-python-server.md) deletes `pb_hooks/`
> entirely, so there is no hook to carry a wire shape and no goja constraint to accommodate. The
> obstacle the earlier note named — that `acervo-worker` is a one-shot container and a synchronous
> capture route needs an always-on Python service — is answered by making the always-on Python
> service *the server*, rather than a second process behind a proxy. Plan 01 was implemented as
> written and deliberately did not touch this; plan 02 is superseded and plans 03 and 04 are re-aimed.

**A provider is a row, not a class.** `models/catalogue.json` is tracked, ships the *list* and never
a secret, and is the only place a provider's endpoint and model id are written down. It is read by
Python and **described once**. This was the one place the dictionary artifact's described-twice
arrangement was going to be copied without its justification: `container.py` and `dictionary.ts`
describe the format twice because one of them runs in a browser and there is no way around it. The
catalogue had no such reason once the reader is a single language.

**One wire shape, plus whatever a library already knows.** `openai` covers the Gemini Developer API,
Cloudflare Workers AI, OpenAI, OpenRouter, Groq, Ollama and any local OpenAI-compatible server, and
is the shape a new row is expected to use. Vertex no longer needs a hand-written second builder: its
OpenAI-compatible endpoint authenticates with a Bearer OAuth token, and minting one is ordinary work
in Python where it was impossible in goja. A provider that fits neither is a reason to lean on
LiteLLM rather than to grow a switch.

**Python is where everything lives.** There is no second server language. Anything asynchronous or
batched — every image, every audio clip, every bulk ingest — runs in `acervo-worker`; anything that
must answer inside a request runs in the service. Both import the same `src/acervo/models/`.

**A provider the server holds no credential for may still be ordered.** *(Amended by
[03](03-the-owner-chooses-a-model.md), 9 Sep 2026 — it previously said such a provider could not be
ordered into a chain.)* A chain is an owner preference; a credential is a deployment fact, and one
must not silently destroy the other. Refusing the write meant a rotated key locked the owner out of
reordering that kind at all, and threw away an ordering they had chosen. The pair is stored, keeps
its place, is skipped when the chain is walked, and is honoured again when the key returns; `GET
/models` marks it and Settings ▸ Models shows why. A pair naming a model the *catalogue* does not
offer is still refused, at the write and at the walk.

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
| Gemini free tier for text — the daily driver, 500 free calls | 01, 04 |
| Vertex for text, when speed matters and credits last | 01 (diagnose), 04 (OAuth is ordinary in Python) |
| Cloudflare Workers AI for text | 04 |
| OpenAI for text | 04 |
| Self-hosted and local text models (Ollama, on-device) | 04 (the row), 07 (where it runs) |
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
| A server that can carry the rest of the roadmap | 08 |
| A queue that offloads GPU work from the NAS to the MacBook | 07 |

Deliberately out of scope, and why:

- **Whisper and speech-to-text of any kind.** Named in the request as out of topic. It would be a
  fourth kind with its own record shape and no consumer; when it is wanted it gets its own plan.
- **Importing the ~2,000 images already generated under Vertex.** A real job and a wanted one, but it
  is a data-import task, not a provider task. Plan 05 says where those images land so that the import
  has a target; it does not do the import.
- **Streaming, caching, tool use, conversation state.** Nothing asks for them.
