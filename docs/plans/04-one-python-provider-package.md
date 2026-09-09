# Plan 04: One Python provider package

> **RE-AIMED by [08 · The Python server](08-the-python-server.md), 8 Sep 2026.**
>
> This is now *the* provider plan, and it grew: with the server in Python, `src/acervo/models/` serves
> the synchronous request path — capture, and article chat after it — as well as batch. It absorbs
> what survived [02](02-one-wire-shape-and-one-catalogue.md): the catalogue as tracked rows, the row
> schema and its capability declaration, and the deployment work. The catalogue is now described
> **once**; the paired hook/Python tests 02 called for are unnecessary.
>
> One thing gets stricter. `text()` must map provider errors onto the existing `llm_*` codes, because
> the file ingestion retries on exactly `llm_rate_limited`, `llm_unavailable` and `llm_unreachable`.
> If LiteLLM's exception hierarchy replaces that mapping, the retry behaviour changes without the
> retry code changing — so the mapping is part of this plan's acceptance boundary, not an afterthought.

**Status:** Complete, 9 Sep 2026.
**Depends on:** [08](08-the-python-server.md) phase 2 — the service must exist before the request
path can call into this package. Carries 02's catalogue schema. Independent of
[03](03-the-owner-chooses-a-model.md) — they can be built in either order.

## Outcome

One way to call a model from Python: `src/acervo/models/`, reading the same
`models/catalogue.json` the hook reads, over LiteLLM, with a chain that falls through on 429 and 5xx.
Text, images and audio go through it. The dead abstraction layer is deleted rather than kept beside
it, and every call site that constructs a client itself stops doing so.

## Current state

Four unrelated layers, one of which is dead:

| Layer | Where | Live? |
|---|---|---|
| The ABC factory | `provider/factory.py`, `llm/`, `tts/`, `vision/` | **No** — the only non-test importer of anything under `provider/` is `scripts/ingest_vocabulary_file.py:36`, and it imports `RateLimiter` alone |
| The sense-image pipeline | `images/`, `scripts/generate_images.py` | Yes |
| The image benchmark | `image_benchmark/`, `scripts/image_benchmark_runner.py` | Yes, for research |
| The capture hook | `pb_hooks/acervo.js` | Yes, and not Python |

`provider/factory.py` is 25 lines of `importlib` dispatch: `type` names the package, `provider` names
the module, and the class is snake-to-camel plus `Provider`. The interfaces it dispatches to cannot
express what the live pipeline needs:

```python
class LLMProvider(ABC):
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...

class ImageProvider(ABC):
    def synthesize(self, text: str, output_path: str) -> None: ...

class TTSProvider(ABC):
    def synthesize(self, text: str, output_path: str) -> None: ...
```

`generate` has nowhere to put a JSON schema, a seed or usage metadata. `synthesize` returns `None`,
so the cost that `images/run.py:272-274` records and the `IMAGE_COST_USD` table at
`scripts/generate_images.py:57-67` have nowhere to come from. That is why the live pipeline bypassed
this layer entirely rather than extending it.

Consequences of the bypass, all of which this plan collapses:

- **Three disagreeing client constructions.** `llm/gemini.py:21` is `genai.Client()` with no retry
  options; `scripts/generate_images.py:90-101` is `genai.Client(vertexai=True, …)` with
  `HttpRetryOptions`; `scripts/image_benchmark_runner.py:559-572` branches on a
  `settings["vertexai"]` flag and is the only one that handles both.
- **Two rate limiters.** `provider/rate_limiter.py:10` is not thread-safe;
  `images/pacing.py:25,89` is a thread-safe fork with a per-model quota pool, and `pacing.py:11-13`
  documents why the fork exists.
- **Two retry mechanisms plus a third.** `provider/retry.py:13` decorates on bare `Exception`;
  the SDK's `HttpRetryOptions`; and `brief.py:145-161` loops on `is_quota_error()`
  (`pacing.py:84`), which is a string match for `429`, `RESOURCE_EXHAUSTED` or `quota`.

No provider-agnostic library is used anywhere. `pyproject.toml` carries `google-genai`, `openai` and
`ollama` as three direct SDKs.

## Decisions

### LiteLLM is the transport, with its gaps stated rather than discovered

Verified coverage as of 2026-09:

| Kind | LiteLLM covers | It does not cover |
|---|---|---|
| Text | Everything Acervo wants, including Gemini, Vertex, Cloudflare, OpenAI, OpenRouter, Ollama, Groq | — |
| JSON schema | Native on Gemini, Vertex, OpenAI, Ollama, Groq, Anthropic, Bedrock, plus `litellm.enable_json_schema_validation` as a client-side check elsewhere | — |
| Image | Google AI Studio, Vertex, OpenAI, Bedrock, Black Forest Labs, fal, OpenRouter | **Cloudflare Workers AI** |
| Audio | OpenAI, Azure, Vertex, Gemini, AWS Polly, ElevenLabs, MiniMax | **Cloudflare Workers AI** |

So **exactly one adapter is hand-written**: Cloudflare's image and audio REST calls. That is not a
guess — `run_cloudflare` at `scripts/image_benchmark_runner.py:443-499` already does the image half
and works, including the awkward part (FLUX.2 Klein requires `multipart/form-data` even for a
text-only prompt, documented at `docs/cloudflare-workers-ai.md:81-83`). Lift it; do not rewrite it.

A LiteLLM proxy container was considered and rejected. It would put an always-on third-party service
with a Postgres dependency on a NAS in order to solve a problem — provider breadth in Python — that
the library solves in-process. The gateway's real advantage is being reachable from a non-Python
caller, and the only such caller is the hook, which plan 02 handles with two request builders.

### Three functions, and each returns what it did

```python
def text(prompt, *, kind_chain, schema=None, system=None) -> TextResult
def image(prompt, *, kind_chain, seed=None, size=None) -> ImageResult
def speech(text, *, kind_chain, voice=None, style=None) -> AudioResult
```

Every result names the provider and model that answered, the wall time, the estimated cost and any
warnings. This is the specific defect in `synthesize(…) -> None` that made the live pipeline bypass
the old layer, and it is also what the locked provenance contract requires: the entry records the
model that answered, so the caller has to be told which one that was.

### A provider declares its controls; it does not implement them

Borrowed from `BackendCapabilities` in `earworms_generator`'s `lexibeat/voice.py`, and borrowed as an
*idea* rather than as a class: a row states whether it supports a control `native`ly, by
`instruction`, by `post-process`, or not at all, and the package adapts once at the call boundary.
`earworms_generator`'s own table records things like "Cloudflare's melotts deployment rejects Spanish
(AiError 8002)" — that kind of fact belongs written down in the catalogue, not rediscovered.

Also worth lifting outright: `_redact_provider_text()`, which strips key and account-id values out of
any provider error text before it is logged or surfaced. Errors from providers routinely echo request
context, and this repository is public.

### Deleted, not deprecated

Backward compatibility is prohibited. The old layer is not kept behind a shim, not aliased, and not
left in place "until callers migrate" — its only callers are tests, so there is nothing to migrate.
Deleting it is what makes `AGENTS.md`'s architecture description true again.

### One rate limiter and one retry policy survive

`images/pacing.py`'s `Pace` and `ModelPool` are the thread-safe implementations with a per-model
quota bucket, written because the other one was not good enough. They move into the package and
`provider/rate_limiter.py` is deleted, along with `scripts/ingest_vocabulary_file.py:36`'s import of
it. `is_quota_error`'s string matching is replaced by LiteLLM's typed `RateLimitError`.

### Designed so `earworms_generator` can use it

That project is intended to fold into this one, and its provider usage refactored the same way. Its
strength is audio, which is Acervo's weakest kind, so plan 06 will want its Gemini free-tier interval
table and its Cloudflare response normalization. Keep the package importable without any Acervo
graph, PocketBase or config-file dependency: it takes a catalogue path and a chain, and nothing else.

## Implementation work

1. **Create `src/acervo/models/`** with a real `__init__.py` — the existing `provider/`, `llm/`,
   `tts/` and `vision/` are implicit namespace packages that only import because `src` is on
   `sys.path`, and that is not worth reproducing.

   - `catalogue.py` — load and validate `models/catalogue.json`; the Python half of the
     twice-described schema
   - `chain.py` — walk a chain, falling through on `RateLimitError` and 5xx only, never on
     authentication or a bad request; carry which row answered into the result
   - `call.py` — `text()`, `image()`, `speech()` over `litellm.completion`,
     `litellm.image_generation` and `litellm.speech`
   - `cloudflare.py` — the one hand-written adapter, for Cloudflare image and audio; lifted from
     `scripts/image_benchmark_runner.py:443-499`, multipart included
   - `pacing.py` — moved from `images/pacing.py`, unchanged
   - `redact.py` — lifted from `earworms_generator`'s `_redact_provider_text`

2. **Map a catalogue row to a LiteLLM model string.** Rows carry `wire` and `baseUrl`;
   Python needs LiteLLM's `provider/model` form (`gemini/…`, `vertex_ai/…`,
   `cloudflare/…`, `openai/…`, `ollama/…`). Add a `litellm` field to the row rather than deriving it
   — derivation is a second source of truth that will drift — and assert in the paired tests that
   every row has one.

3. **JSON-constrained text.** `response_format=<PydanticModel>` where the row says `native`;
   `litellm.enable_json_schema_validation = True` plus prompt-side instruction where it says
   `prompt`. Keep `unfenced()`'s equivalent: models wrap JSON in fences regardless.

4. ~~**Delete the superseded layer**~~ — **done in [08](08-the-python-server.md) phase 0**, ahead of
   this plan, because the port needed the tree honest before it started. `provider/`, `llm/`, `tts/`,
   `vision/`, `config.py`, their 798 lines of tests, `config/defaults.yaml`,
   `config/image-providers.example.yaml`, the empty `anki/` and `data/` directories and
   `PROJECT_SUMMARY.md` are all gone; `AGENTS.md` is re-aimed. Two things to know:
   - **`tts/kokoro.py` and `tts/helpers.py` went too.** This plan left them conditional on plan 06
     choosing a local voice. If 06 chooses one, they are recovered from git or rewritten as a
     `models/` backend — they were 51 lines over an inference library, not an asset.
   - **`provider/rate_limiter.py` is gone and `pacing.py` replaced it**, moved up out of `images/`.
     It is thread-safe, which the one it replaced was not, and it is now the single rate limiter.

5. **Dependencies.** `litellm` into `requirements/core.txt` and `pyproject.toml`. Drop `openai` and
   `ollama` as direct dependencies — LiteLLM reaches both. Keep `google-genai` only if plan 05 still
   needs the native client for something LiteLLM cannot express; if not, drop it too. The server
   image (`deploy/acervo/Dockerfile:11-16`) currently installs none of these and will need `litellm`
   once `acervo-worker` generates anything.

6. **Do not touch `images/` or the benchmark here.** This plan builds the package and deletes the dead
   one; plans 05 and 06 move the live callers onto it. Keeping those separate means this plan can be
   verified on its own.

## Public interfaces and data

```python
# src/acervo/models/__init__.py

@dataclass(frozen=True)
class Answer:
    """What every call returns beside its payload.

    The old ImageProvider.synthesize returned None, which is why cost and model
    provenance had nowhere to go and the live pipeline bypassed the layer.
    """
    provider_id: str          # the catalogue row that answered, not the one asked first
    model: str
    seconds: float
    cost_usd: float | None
    warnings: tuple[str, ...]
    attempts: tuple[str, ...] # provider ids tried and fallen through, oldest first


@dataclass(frozen=True)
class TextResult:
    text: str
    parsed: Any | None        # set when a schema was supplied
    answer: Answer

@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime: str
    answer: Answer

@dataclass(frozen=True)
class AudioResult:
    data: bytes
    mime: str
    answer: Answer


def text(prompt: str, *, chain: Sequence[str], system: str | None = None,
         schema: type[BaseModel] | None = None,
         catalogue: Catalogue | None = None) -> TextResult: ...

def image(prompt: str, *, chain: Sequence[str], seed: int | None = None,
          size: tuple[int, int] | None = None,
          catalogue: Catalogue | None = None) -> ImageResult: ...

def speech(words: str, *, chain: Sequence[str], voice: str | None = None,
           style: str | None = None,
           catalogue: Catalogue | None = None) -> AudioResult: ...
```

Errors, and the distinction that carries the locked fall-through rule:

```python
class ProviderRefused(Exception):
    """Terminal for this row and for the chain: auth, a bad request, an unknown model.
    Never fallen through — it is a mistake to fix, not a condition to route around."""

class ProviderUnavailable(Exception):
    """Retryable at the next row: 429, 5xx, a timeout, a connection failure."""

class ChainExhausted(Exception):
    """Every row was unavailable. Carries the last error, because that is the actionable one."""
```

The catalogue row gains one field for this plan:

```jsonc
{ "id": "cloudflare", "litellm": "cloudflare/@cf/meta/llama-4-scout-17b" }
```

## Acceptance tests and verification

```bash
uv pip install -r requirements/dev.txt
.venv/bin/python -m pytest
```

Unit cases, all offline against a stubbed `litellm`:

- a chain whose first row raises `RateLimitError` → the second answers, and
  `answer.provider_id` names the second while `answer.attempts` names both
- a chain whose first row raises an authentication error → `ProviderRefused`, and **the second row is
  never called** (assert the stub's call count, not just the exception)
- every row unavailable → `ChainExhausted`, carrying the last error
- a `native` row sends `response_format`; a `prompt` row does not, and its reply is validated after
  parsing
- an error message containing a key value is redacted before it reaches the exception text
- every row has a `litellm` field and a `wire` the loader recognises. There is no second description
  of the catalogue to keep in step: 02 called for paired hook/Python tests, and with the hook gone
  the schema is described once

Deletion checks, which are the part most likely to be left half done:

```bash
# nothing imports the deleted layer any more (already true after 08 phase 0)
grep -rn "acervo\.\(provider\|llm\|vision\|tts\)\|create_provider\|select_llm_provider" \
  --include='*.py' . | grep -v '/models/'
# expect: no output

# and the directories are gone, not emptied
ls src/acervo/ | grep -E '^(provider|llm|vision|tts)$'
```

Live, one call per kind against two providers each — this needs real keys and is the only part that
costs money:

```bash
.venv/bin/python -m pytest tests/integration/test_models_live.py   # gated, like the existing ones
#  · text:   gemini-free and cloudflare, both with a JSON schema
#  · image:  vertex and cloudflare, one 512px image each
#  · speech: gemini-free and cloudflare, one word each
#  · every result names the provider that answered and a non-zero duration
```

## Non-goals

- **No adapter, shim or alias for the deleted layer.** Its only callers were tests.
- **No LiteLLM proxy container.** The library is in-process; the one non-Python caller is handled by
  plan 02.
- **No caching.** Nothing asks for it, and generated media is already cached on the filesystem by
  `images/run.py`'s store.
- **No streaming.** Every call Acervo makes is one-shot.
- **No cost enforcement.** `cost_usd` is recorded because provenance is cheap; no budget is checked.
- **No call-site migration.** `images/`, the benchmark and `scripts/generate_images.py` keep working
  exactly as they do today; plans 05 and 06 move them.
- **No speech-to-text.** Not a kind. Whisper is out of scope for this whole roadmap.

---

## Implementation and verification record

Built as specified, with the corrections below. `src/acervo/models/` is the one way to call a model;
`services/llm.py` is deleted and capture goes through the package.

### What LiteLLM turned out to be, against what this plan assumed

Verified against litellm 1.100.0 rather than from documentation, because two of these change
behaviour rather than shape.

- **`Timeout` carries status 408 and `APIConnectionError` carries 500.** A mapping written on
  `status_code` alone sends a timeout to `llm_failed`, which the file ingestion does **not** retry —
  the exact silent regression this plan's re-aim note warns about. `classify()` reads type before
  number, and both cases are pinned in `tests/unit/models/test_call.py` and in `test_capture.py`.
- **There is no Vertex express-key path** ([BerriAI/litellm#21036](https://github.com/BerriAI/litellm/issues/21036)),
  so `VERTEX_API_KEY` no longer means anything and is gone. The row authenticates by ADC. Before
  deleting it, `GET /health` on the live server was checked: it reported `provider: gemini`, so
  nothing that was working was removed. On a server, Vertex now needs a service-account JSON and
  `GOOGLE_APPLICATION_CREDENTIALS` — a deployment change, not a code change, and not made here.
- **Both retry mechanisms have to be switched off**, not one: `num_retries` is LiteLLM's own loop
  and `max_retries` is the provider SDK's, which LiteLLM sets to 2 unless told otherwise.
- **`litellm` is +304 MB on the server image** (414 MB → 718 MB), measured. The plan expected
  `boto3` to be most of it and it is not: `litellm` itself is 116 MB, `botocore` 30 MB. Dropping
  boto3 with `--no-deps` would buy 32 MB in exchange for a dependency list to maintain by hand, so
  it was not done. The worker image does **not** install LiteLLM — no job calls a model until plan
  05 — and `call.py` imports it lazily so `acervo.models.pacing` still works there. A test asserts
  that reading the catalogue does not pull LiteLLM in, because a stray module-level import would
  break the worker and nothing else.

### Corrections to the plan's own design

- **`litellm` is a per-kind map, not a scalar.** A row declaring three `kinds` cannot name three
  models with one string. The loader's invariant is that every declared kind has either a
  `litellm[kind]` or an `adapter[kind]`, never both and never neither.
- **The `llm_*` mapping lives in `services/models.py`, not in `text()`.** The plan asks both for
  that mapping and for a package importable without Acervo, which only fit if the split is at the
  vocabulary rather than at the raise: `models/` produces a closed seven-value `Reason`, the binding
  layer turns it into an `ApiError`. `test_layering.py` gained a rule enforcing the package's
  independence, because one `from acervo.errors import ApiError` would collapse it invisibly.
- **`compose()` returns the model that answered.** `capture.py` read `modelId` from `Settings`
  before the call, which under a chain names the row that was asked rather than the one that
  answered — a live violation of the locked provenance contract, fixed here rather than deferred.
- **Rows gained `passes` and two capability entries**, each because a live call failed without them.
  A provider fact belongs in the row, not in a branch: Vertex needs its project as a call argument
  and refuses `response_format`; Gemini rejects OpenAI's voice names; Cloudflare's Deepgram Aura
  takes `text` where melotts took `prompt`.
- **`ACERVO_TEXT_CHAIN` replaces `ACERVO_LLM_PROVIDER`/`ACERVO_LLM_MODEL`**, and `--configure-llm`
  became `--llm-chain` / `--llm-set NAME=VALUE` / `--llm-key NAME`. The `gemini|vertex` whitelist and
  the known-wrong-model check are gone: the installer now validates a variable name against the
  catalogue it was shipped, so adding a provider is a catalogue edit and nothing else.
- **The interface changed after all.** `CaptureHealth.provider` and `.model` are nullable: when no
  row has its credentials there is no model to name, so the two "It is set to … with the model …"
  sentences became the reason alone, which is the actionable part.

### What the live run found, which is why it was worth running

`RUN_LIVE_MODEL_TESTS=true` against real providers caught four things no stub could:
the Cloudflare image model id was wrong (`flux-2-klein`, not `flux-2-klein-4b`); no Imagen model is
reachable in this Vertex project, so the row uses the Gemini image model the sense-image pipeline
already uses, at `global` rather than a named region; Gemini refuses `alloy`; and Cloudflare's
melotts answers Spanish with AiError 8002 and a plain English word with a 500, so the audio model is
Deepgram Aura instead.

One thing is worth knowing for plan 06: `gemini-2.5-flash-preview-tts` out of free quota answers
with *no candidates*, and LiteLLM's speech bridge raises `IndexError` on that rather than reporting
the refusal — which would reach a chain as terminal rather than as rate limiting. The row uses the
`pro` model, which reports a proper `RateLimitError`. The live speech test treats a typed rate limit
as "reached, and out of quota", because a 429 proves both things that test exists to check.

### Verification

```
.venv/bin/python -m pytest                    751 passed, 16 skipped
npm --prefix web run test                     266 passed
npm --prefix web run build                    clean
RUN_DOCKER_INTEGRATION_TESTS=true …           6 passed
RUN_LIVE_MODEL_TESTS=true …                   7 passed, 1 skipped (gemini speech, out of free quota)
```

Live, per kind: text on `gemini-free` and `cloudflare`; image on `vertex` (79 KB) and `cloudflare`
(48 KB); speech on `cloudflare` (4 KB). A deliberately wrong key was refused rather than routed
around, and the key did not appear in the error text.

Deployed to the Synology and healthy. `GET /health` reports
`{"available": true, "provider": "gemini-free", "model": "gemini/gemini-3.1-flash-lite"}` — a
catalogue row id and a LiteLLM model string, so the new code is what is running. `llm.env` carries
the chain and the Cloudflare credentials, and the installer accepted every variable name against the
shipped catalogue, which is the check that replaced the provider whitelist. A capture through the
interface needs an account password and was left to the owner.

### Second pass: a row names several models, and says where to read the bill

After the first deployment, the owner's own free-tier readout settled several things this plan had
guessed at, and one of them changed the shape of the catalogue.

**A kind names a list of models, not one.** Gemini's free tier meters *per model*: 500 requests a
day to `gemini-3.1-flash-lite` and another 500 to `gemini-3.5-flash-lite`, in separate buckets. One
model per row would have thrown half the free allowance away. So `litellm` and `models` take lists,
the chain walks (provider, model) pairs — provider by provider, and inside each, model by model —
and `Answer.attempts` records pairs. Falling through to a second model of the *same* provider is the
common case now; falling through to the next provider happens when a row is out of models. A
terminal refusal still stops everything, including the row's own remaining models: a rejected key is
not fixed by asking the same provider for a different model.

**Every row says where to read its usage.** No provider Acervo speaks to serves a usage figure over
its API, so `usageUrl` is a link, and plan 03's Settings pane renders it. It is a template filled in
from the environment under the same rule as `baseUrl` — a `requires` name, never a key — because the
owner's real links carry a project id and a billing account id and this repository is public.
Cloudflare's is the one that comes out fully formed, the account id already being a `requires`.

**What the free tier actually allows, which is not what the plan assumed.** Every image model on it,
Nano Banana included, is allowed **zero** requests, so `gemini-free` no longer declares an `image`
kind at all — a row that can only 429 is slower and more confusing than a row that is not there.
Vertex is the only provider that can make an image today. Speech is one model at 10 a day: the tier
allows a second, `gemini-2.5-flash-preview-tts`, and it is deliberately unlisted because it answers
a short word with generated *text* often enough to be useless, Gemini refuses that with a 400, and
LiteLLM's speech bridge surfaces it as `IndexError` rather than as a refusal — which the chain would
read as terminal and stop on. That is a real hazard for plan 06 and is written into the row.

**Vertex's models are project-specific.** `gemini-3-flash` and `gemini-3.1-flash` both 404 in this
project, as every Imagen id does. The row now names what the owner's own overnight sense-image run
used and what a live call confirms: `gemini-3.8-flash` for text and `gemini-3.1-flash-lite-image`
for images. `reasoning_effort` is gone too — LiteLLM refuses the parameter for these models, where
the REST call this replaced sent `thinkingLevel: MEDIUM`.

**Audio is labelled by what it is.** Gemini answers WAV and Cloudflare's Aura answers MP3, so the
hardcoded `audio/mpeg` was wrong for one of them. `audio_mime()` sniffs the bytes; a clip stored
under the wrong container is a file nothing plays, found much later than the call that made it.

The live test now parametrizes over **every pair in the catalogue** rather than a hand-picked few,
which is what caught all of the above. It is also the only thing that can: a model id the provider
has retired, or allows zero requests of, is indistinguishable from a working one until something
asks. Eleven pairs pass, five skip for want of credentials on this machine.
