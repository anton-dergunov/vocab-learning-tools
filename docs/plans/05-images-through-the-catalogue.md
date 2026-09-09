# Plan 05: Images through the catalogue

**Status:** Planned.
**Depends on:** [04](04-one-python-provider-package.md). Reads the chain from
[03](03-the-owner-chooses-a-model.md) if that is done, and a command-line chain otherwise.

## Outcome

The sense-image pipeline stops constructing its own Vertex client and hardcoding its own model list.
Which provider draws a picture becomes a catalogue row and a chain, so Cloudflare FLUX.2 Klein — free
inside its daily allocation — can carry the steady state while Vertex carries a bulk import, and
running out of one falls through to the other instead of stopping the sweep.

## Current state

`scripts/generate_images.py` is the live entry point and it hardcodes everything:

```python
BRIEF_MODEL = "gemini-3.8-flash"                       # :57
IMAGE_MODELS = ("gemini-3.1-flash-lite-image",)        # :58
IMAGE_COST_USD = {"gemini-3.1-flash-lite-image": 0.0336,
                  "gemini-3.1-flash-image": 0.067,
                  "gemini-3-pro-image": 0.134}         # :60-67
```

and constructs one client, shared by the text call and the image call, at `:90-101`:

```python
def make_client(project: str, location: str):
    return genai.Client(vertexai=True, project=project, location=location,
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(
            attempts=4, initial_delay=10.0, max_delay=60.0, exp_base=2.0, jitter=1.0,
            http_status_codes=[408, 429, 500, 502, 503, 504])))
```

`BriefWriter` (`images/brief.py:136`) and `Renderer` (`images/render.py:32`) each take that client in
their constructor, so neither can be pointed anywhere else. Credentials come from ADC — 
`images/preflight.py:37` shells out to `gcloud auth application-default print-access-token` and
verifies it against Google's tokeninfo endpoint to name the account that will be billed, and
`generate_images.py:70` asks "Bill this account? [y/N]". That is a **laptop-only** path: there is no
`gcloud` in the server image.

Separately, `scripts/image_benchmark_runner.py` holds eleven backends behind a registry at `:657` —
`mock`, `icon-scene`, `openverse`, `diffusers`, `mflux`, `mflux-z-image`, `drawthings`, `cloudflare`,
`bfl`, `gemini`, `starvector` — each a function taking a JSON request and writing a JSON result, with
SDKs imported inside the function so the process can be launched under `uv run --with …`. It is the
only place in the repository that already talks to Cloudflare and Black Forest Labs, and the only
Gemini caller that handles both the API-key and Vertex client shapes (`:559-572`).

`docs/image-generation-research.md` settled the provider question and its conclusion has never been
implemented. The chosen hierarchy at `:6-25` is: emoji fallback, then a deterministic icon scene,
then **Cloudflare FLUX.2 Klein for the steady state**, then Gemini 3.1 Flash Lite Image for the
initial bulk import while Vertex credits last, and no local diffusion default. The finalist scores in
`docs/image-benchmark-finalist-results.md`: Flash Lite 4.81, Flash 4.75, **Cloudflare Klein 4.54**,
Gemini Pro 4.21 with one rejection in twelve and the highest price. Cost per thousand images:
Cloudflare $0 inside the free allocation of roughly 383 512-pixel outputs a day — a hard stop, no
silent billing — or about $0.287 paid; Flash Lite about $33.60; Pro about $134.

Two known defects recorded and not fixed:

- **Configured width and height are not passed into the pipeline** (`image-generation-research.md:37-41`),
  so it generates at the pipeline default and then resizes to 384. The research also concludes the
  right approach is to generate at 512 and downsample rather than requesting a small size directly.
- **Nothing records a failure** (`docs/acervo-sense-images.md:139`) — a refusal leaves no trace that a
  sweep can act on.

`docs/acervo-sense-images.md:512-517` states the position plainly: "No local diffusion fallback yet.
§09's provider chain stands as the plan; Phase A hardcodes Vertex."

## Decisions

### Cloudflare becomes a production row, because the research already chose it

This is not a new evaluation. `docs/image-generation-research.md` and the finalist results picked
Cloudflare FLUX.2 Klein as the steady state on the grounds that it scores within half a point of the
best hosted model, costs nothing inside a daily allocation that stops rather than bills, and needs no
GPU. Implementing that conclusion is most of this plan's value.

Vertex stays as the row in front of it for bulk work while the credits last, which is exactly what a
chain is for.

### Hosted providers go through the package; local ones stay in the benchmark

The eleven benchmark backends are not equally worth unifying. The three hosted ones — `gemini`,
`cloudflare`, `bfl` — become catalogue rows and route through `src/acervo/models/`, so there is one
place a hosted image call is made and one place its cost is recorded. The local ones — `mflux`,
`diffusers`, `drawthings`, `openverse`, `icon-scene`, `starvector` — stay exactly where they are, as
benchmark-only backends.

The reason is subprocess isolation, and it is a real requirement rather than an accident: the research
at `:186-215` specifies one image per child process precisely so unified memory is returned after
each, and MFLUX peaks at 5.65 GiB while Sana reaches 8–10 GiB RSS. A local model that must run in its
own short-lived process does not fit behind an in-process function call, and pretending otherwise
would drag that isolation machinery into the shared package for no caller that needs it.

If a local model is ever wanted in production, it arrives as a row whose transport is "spawn a
subprocess" — and that is plan 07's territory, because the machine with the GPU is not the machine
that is always on.

### Credentials: an API key on the server, ADC on the laptop

`images/preflight.py`'s ADC path and its "Bill this account?" prompt are good for a laptop run and
impossible on the server. Both must work, so the row decides: a Vertex row reached from the server
uses the restricted API key from the key file, and the same row reached from a laptop may use ADC.
Keep the preflight confirmation for the ADC path only — it exists because a misconfigured `gcloud`
once pointed at a work account, and that hazard is specific to ADC.

### Fix the size defect while the call sites are open

Generating at the pipeline default and resizing is wasted money and worse pictures, and the fix is a
parameter that plan 04's `image()` already takes. Generate at 512 and downsample to the stored master,
per the research's own conclusion.

### The record names what drew it

`images/run.py:277` already writes `modelId` (the brief model) and `imageModelId`. With a chain,
`imageModelId` must be the row that answered — the locked provenance contract — and the two fields
stay distinct, because the brief and the picture are genuinely two calls to possibly different
providers.

### The 2,000 existing images are named here and imported elsewhere

There are roughly 2,000 images already generated under Vertex, and they should end up in the
vocabulary. That is a data-import job: match each file to its sense, mint or update the
`image_prompt` record, and write the media. It needs this plan's record shape to exist and nothing
else from it.

Saying where they land is in scope. Doing it is not — mixing a one-off backfill into a provider
refactor makes both harder to verify, and the backfill is a script that runs once.

## Implementation work

1. **Add the image rows** to `models/catalogue.json`: `vertex` and `gemini-free` gain image models
   and per-image costs from `IMAGE_COST_USD`; `cloudflare` gains
   `@cf/black-forest-labs/flux-2-klein-4b` with its free-allocation note; `bfl` is added if it is
   still wanted after the finalist results (it scored below Cloudflare and costs from $14 per
   thousand, so probably as a listed-but-unenabled row).

   Cloudflare's image models need `multipart/form-data` even for a text-only prompt
   (`docs/cloudflare-workers-ai.md:81-83`), which is why plan 04 has a hand-written adapter for them
   and why the row's `capabilities` must say so.

2. **`BriefWriter` and `Renderer` stop taking a client.** `images/brief.py:136` and
   `images/render.py:32` take a chain instead and call `models.text()` and `models.image()`.
   `brief.py`'s `response_mime_type="application/json"` becomes plan 04's `schema=`, which also
   replaces `parse_reply`'s hand-rolled validation at `:89`. Delete `make_client` from
   `scripts/generate_images.py:90-101`.

3. **The hardcoded constants move into rows.** `BRIEF_MODEL`, `IMAGE_MODELS` and `IMAGE_COST_USD`
   (`:57-67`) are deleted; `--brief-model` and `--image-models` become `--brief-chain` and
   `--image-chain`, defaulting to the owner's chain from plan 03's route when the server is reachable
   and to the catalogue's default order when it is not.

4. **`ModelPool` becomes the chain's pacing.** `images/pacing.py:89`'s per-model quota buckets moved
   into `models/pacing.py` in plan 04; here, `run.py:143`'s construction of it from
   `renderer.models` becomes construction from the chain, with each row's rate limit read from the
   catalogue rather than from `--rate-limit`.

5. **Fix the size defect.** Pass the configured width and height into the call, generate at 512, and
   downsample to the stored master. `render.py:82`'s `_save_webp` and `WEBP_QUALITY = 88` are
   unchanged.

6. **Record a refusal.** `images/render.py:21`'s `RenderRefused` is terminal and currently vanishes;
   write it into the store beside `refusals/` so a re-run can see it and a sweep can report it. This
   closes the gap `docs/acervo-sense-images.md:139` names.

7. **Retire the benchmark's hosted backends.** `run_gemini` (`:542-599`), `run_cloudflare`
   (`:443-499`) and `run_bfl` (`:501-540`) become one `run_catalogue` backend that calls
   `models.image()`. The local backends and the whole subprocess contract
   (`contract_version: 1`, JSON in / JSON out) are untouched. `config/image-benchmark.yaml`'s hosted
   candidates change their `provider` to `catalogue` and name a row id.

8. **Delete `config/image-providers.example.yaml`.** Its `default_provider` / `providers` / 
   `fallback_order` sketch is what the catalogue and chains became. It has never been loaded by
   anything.

9. **Write down where the backfill lands**, in `docs/acervo-sense-images.md`: which `image_prompt`
   fields an imported image sets, how a file is matched to a sense, and that `imageModelId` records
   the Vertex model that actually drew it rather than whatever the chain says today. Then stop.

## Public interfaces and data

Catalogue rows gain an image section:

```jsonc
{
  "id": "cloudflare",
  "kinds": ["text", "image", "audio"],
  "defaultModel": {
    "text":  "@cf/meta/llama-4-scout-17b",
    "image": "@cf/black-forest-labs/flux-2-klein-4b"
  },
  "litellm": { "text": "cloudflare/@cf/meta/llama-4-scout-17b" },
  "capabilities": {
    "image": { "transport": "multipart", "seed": "native", "size": "native", "steps": "fixed-4" }
  },
  "cost": { "image": { "usd_per_1000": 0.287,
                       "free_note": "10,000 neurons a day, about 383 512px images; hard stop" } }
}
```

`"transport": "multipart"` is why this row needs plan 04's hand-written adapter rather than LiteLLM,
and `"steps": "fixed-4"` records that FLUX.2 Klein's inference step count is not negotiable — the
kind of fact that is otherwise rediscovered through a 400.

The stored image record, unchanged in shape but with one field's meaning tightened:

```jsonc
{
  "modelId": "gemini-3.8-flash",              // wrote the brief
  "imageModelId": "@cf/black-forest-labs/flux-2-klein-4b",  // DREW it — the row that answered
  "promptVersion": "…template digest + style digest…",
  "seed": 17
}
```

## Acceptance tests and verification

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/generate_images.py check
```

Unit cases:

- a brief is requested through a chain and the result names the row that answered
- an image chain whose first row is rate limited draws from the second, and `imageModelId` names the
  second
- a `multipart` row is called through the hand-written adapter, not through LiteLLM
- the configured width and height reach the call — the specific defect at
  `image-generation-research.md:37-41`, so assert on the request, not on the output size
- a refusal is written to the store and a re-run sees it rather than retrying blindly
- `config/image-benchmark.yaml`'s catalogue candidates resolve to real rows

Live:

```bash
# one sense image per provider, same sense, same seed — and look at them side by side
.venv/bin/python scripts/generate_images.py run --image-chain vertex     --limit 1
.venv/bin/python scripts/generate_images.py run --image-chain cloudflare --limit 1
#  · both produce a 1024² WebP master
#  · each record's imageModelId names the provider that drew it
#  · the Cloudflare one costs nothing and the neuron allocation moves

# the chain, for real
.venv/bin/python scripts/generate_images.py run --image-chain cloudflare,vertex --limit 500
#  · when Cloudflare's daily allocation stops, the sweep continues on Vertex
#  · it does NOT continue past a bad key — that refuses and stops

# idempotence, which is what makes a sweep safe to re-run
#  · run twice with no --reset: the second run draws nothing and reports why
```

## Non-goals

- **No local diffusion in production.** The research concluded against a local default, and the
  isolation a local model needs belongs to plan 07.
- **No import of the ~2,000 existing images.** Named, given a target, and left to its own script.
- **No change to the subprocess benchmark contract.** `contract_version: 1`, JSON in and out, one
  process per job. The local backends do not move.
- **No video.** Deferred in the research because Anki syncs media to every client.
- **No low-information rejection gate** — the luminance, entropy and edge-density checks with
  seed-retry described in the research. It is a quality gate, not a provider concern, and it deserves
  its own plan once more than one provider is in use and there is something to compare.
- **No emoji or icon-scene fallback wiring.** The research's full hierarchy ends in a deterministic
  icon scene and then an emoji; both exist as benchmark backends. Promoting them is a separate
  decision about what an entry shows when nothing drew it.
