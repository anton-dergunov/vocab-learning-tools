# Plan 04: One Python provider package

**Status:** Planned.
**Depends on:** [02](02-one-wire-shape-and-one-catalogue.md) for the catalogue schema. Independent of
[03](03-the-owner-chooses-a-model.md) — they can be built in either order.

## Outcome

One way to call a model from Python: `src/vocabgen/models/`, reading the same
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

1. **Create `src/vocabgen/models/`** with a real `__init__.py` — the existing `provider/`, `llm/`,
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

2. **Map a catalogue row to a LiteLLM model string.** Rows carry `wire` and `baseUrl` for the hook;
   Python additionally needs LiteLLM's `provider/model` form (`gemini/…`, `vertex_ai/…`,
   `cloudflare/…`, `openai/…`, `ollama/…`). Add a `litellm` field to the row rather than deriving it
   — derivation is a second source of truth that will drift — and assert in the paired tests that
   every row has one.

3. **JSON-constrained text.** `response_format=<PydanticModel>` where the row says `native`;
   `litellm.enable_json_schema_validation = True` plus prompt-side instruction where it says
   `prompt`. Keep `unfenced()`'s equivalent: models wrap JSON in fences regardless.

4. **Delete the superseded layer**, and update every reference:
   - `src/vocabgen/provider/factory.py`, `provider/rate_limiter.py`
   - `src/vocabgen/llm/{base,gemini,openai,ollama}.py`
   - `src/vocabgen/vision/{base,stable_diffusion}.py`
   - `src/vocabgen/tts/base.py` — and `tts/kokoro.py` with `tts/helpers.py` **only if** plan 06
     decides against a local voice; otherwise they become a `models/` local backend
   - `provider/retry.py` — only if LiteLLM's `num_retries` replaces it, which it should
   - the tests: `tests/unit/provider/`, `tests/unit/llm/`, the Kokoro and Stable Diffusion
     integration tests, `tests/manual/test_llm_manual.py`, `tests/manual/test_media_gen_manual.py`
   - the `llm`, `tts` and `image` sections of `config/defaults.yaml`, and `select_llm_provider` in
     `src/vocabgen/config.py:53-69` — the catalogue replaces both
   - `config/image-providers.example.yaml`, superseded and never loaded
   - the empty `src/vocabgen/anki/` and `src/vocabgen/data/` directories, which hold nothing but
     `__pycache__`
   - `AGENTS.md` and `PROJECT_SUMMARY.md`, which plan 01 corrected and this plan makes accurate

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
# src/vocabgen/models/__init__.py

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
- `catalogue.py` and `tests/hooks/catalogue.test.mjs` agree — this is the pair that guards the
  twice-described schema, so it fails loudly when only one side is changed
- every row has a `litellm` field and a `wire` that is one of the two permitted values

Deletion checks, which are the part most likely to be left half done:

```bash
# nothing imports the deleted layer any more
grep -rn "vocabgen.provider\|vocabgen\.llm\|vocabgen\.vision\|vocabgen\.tts\|create_provider\|select_llm_provider" \
  --include='*.py' . | grep -v '/models/'
# expect: no output

# and the directories are gone, not emptied
ls src/vocabgen/ | grep -E '^(provider|llm|vision)$'
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
