# Image benchmark finalist results

Evaluation date: 2026-08-27. This report records one reviewer's ratings of 96
images: eight candidates, twelve vocabulary meanings, one art-directed style,
and seed 17. Every job succeeded and every image was rated.

The comparison uses mnemonic relevance (45%), visual appeal (30%), artifact
freedom (20%), and small-size legibility (5%). It reports two complementary
rankings:

- **Rejected-as-zero** measures unattended reliability. A rejected output
  contributes zero rather than disappearing from the result.
- **Accepted-only** describes the quality and style of usable outputs. Rejected
  outputs are excluded from metric averages, but their count and rate stay
  visible and must be considered separately.

This is a directional personal benchmark, not a general model leaderboard. A
single seed and compact prompt set cannot measure output variance.

## Results

| Zero rank | Candidate | Reject = 0 | Accepted-only | Accepted | Mean time | Configured cost / 1,000 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Gemini 3.1 Flash Lite Image | 4.81 | **4.81** | 12/12 | 16.3 s | $33.60 |
| 2 | Gemini 3.1 Flash Image | 4.75 | **4.75** | 12/12 | 20.3 s | $67.00 |
| 3 | Cloudflare FLUX.2 Klein 4B | 4.54 | **4.54** | 12/12 | 22.9 s | $0.287 |
| 4 | Gemini 3 Pro Image | 4.21 | **4.60** | 11/12 | 39.6 s | $134.00 |
| 5 | Sana Sprint 0.6B | 3.81 | **3.81** | 12/12 | 33.2 s | $0 local |
| 6 | Draw Things FLUX.2 Klein Q6P | 3.34 | **3.34** | 12/12 | 35.4 s | $0 local |
| 7 | LCM DreamShaper | 3.09 | **4.12** | 9/12 | 16.5 s | $0 local |
| 8 | MFLUX FLUX.2 Klein Q4 | 3.00 | **3.60** | 10/12 | 49.3 s | $0 local |

Accepted-only ranking is Flash Lite, Flash, Gemini Pro, Cloudflare,
DreamShaper, Sana, MFLUX, then Draw Things. Rejected-as-zero ranking remains
the safer basis for fully unattended generation.

### Accepted-only metric averages

| Candidate | Relevance | Legibility | Appeal | Artifact freedom | Rejected |
|---|---:|---:|---:|---:|---:|
| Gemini Flash Lite | 4.67 | 4.58 | **5.00** | **4.92** | 0/12 |
| Gemini Flash | 4.67 | **4.67** | 4.83 | 4.83 | 0/12 |
| Gemini Pro | 4.55 | 4.45 | 4.55 | 4.82 | 1/12 |
| Cloudflare FLUX.2 Klein 4B | 4.67 | **4.67** | 4.25 | 4.67 | 0/12 |
| LCM DreamShaper | 3.78 | 3.67 | 4.56 | 4.33 | 3/12 |
| Sana Sprint | 3.83 | 4.00 | 3.67 | 3.92 | 0/12 |
| MFLUX FLUX.2 Klein Q4 | 3.70 | 4.00 | 3.30 | 3.70 | 2/12 |
| Draw Things FLUX.2 Klein Q6P | 3.42 | 3.92 | 2.92 | 3.67 | 0/12 |

The accepted-only view supports the reviewer's qualitative observations:

- DreamShaper's accepted images have a distinctive artistic style and the
  strongest local visual-appeal score. Its problem is reliability: three of
  twelve outputs were rejected, including near-single-tone failures and images
  unrelated to the intended meaning.
- Draw Things produced no outright rejects, but its 2.92 appeal score is the
  lowest in the finalist set. Its schematic, visually plain style is not a good
  fit for this reviewer even though it is operationally predictable.
- Gemini Pro's accepted work ranks third, but one output represented the
  meaning with an inappropriate concept. It was also slower and more expensive
  than both Flash variants, so the benchmark does not justify it as a default.

## Local resource pressure

| Candidate | Mean process RSS | Max process RSS | Accelerator measurement | Mean time |
|---|---:|---:|---|---:|
| Sana Sprint | 8.13 GiB | 10.08 GiB | about 10.00 GiB MPS post-generation allocation | 33.2 s |
| LCM DreamShaper | 4.58 GiB | 5.38 GiB | 3.86 GiB MPS post-generation allocation | 16.5 s |
| MFLUX FLUX.2 Klein Q4 | 2.51 GiB | 2.69 GiB | 5.65 GiB MLX framework peak | 49.3 s |
| Draw Things FLUX.2 Klein Q6P | 1.39 GiB | 1.49 GiB | unavailable; process RSS is a lower bound | 35.4 s |

Process RSS and accelerator figures must not be added: Apple GPU allocations
use unified memory and may overlap process accounting. Sana is too heavy for a
16 GiB background worker. MFLUX combines the longest runtime with substantial
MLX pressure, matching the observed interactive slowdown. DreamShaper is fast
enough to remain an interesting future artistic fallback if failures can be
detected and retried.

A future automatic rejection gate could cheaply detect the near-single-tone
DreamShaper failures before semantic review. Useful signals include luminance
and color variance, entropy, edge density, and the dominant-color share. A
low-information test should combine several signals rather than reject every
minimal illustration; on failure, retry with a new seed. Semantic mismatch and
inappropriate concepts still require a vision-model check or a provider retry.
No such production gate was implemented in this phase.

## Operational decision

1. Use Gemini 3.1 Flash Lite Image for the temporary credit-backed bulk build.
2. Use Cloudflare FLUX.2 Klein 4B for ongoing generation after those credits
   expire. At the configured price, 1,000 outputs cost about $0.287 before the
   daily free allocation, and a few images per day are comfortably within it.
3. Do not select a local diffusion default yet. Keep DreamShaper as the most
   interesting artistic local option for a future retry/detection experiment.
4. Keep deterministic icon/emoji composition as the guaranteed final fallback.

## Cloudflare image choices and tuning

FLUX.2 Klein 4B is not Cloudflare's only image model. The current Workers AI
catalog includes these relevant alternatives:

| Model | Why it may be interesting | Main trade-off |
|---|---|---|
| `@cf/black-forest-labs/flux-2-klein-9b` | Enhanced-quality Klein variant | Fixed four steps; $0.015 for the first output megapixel, far more quota than 4B |
| `@cf/black-forest-labs/flux-2-dev` | More powerful, high-fidelity FLUX.2; configurable steps and guidance | Slower; $0.00041 per output 512px tile **per step** |
| `@cf/leonardo/lucid-origin` | Strong prompt response and broad stylized aesthetics | Much higher tile and step cost |
| `@cf/leonardo/phoenix-1.0` | Prompt adherence and coherent text; configurable guidance and 1–50 steps | Higher cost; text rendering is not valuable for these cards |
| `@cf/lykon/dreamshaper-8-lcm` | Cloud-hosted route to the artistic DreamShaper family | Older model; reliability must be measured |
| `@cf/bytedance/stable-diffusion-xl-lightning` | Fast SDXL with configurable prompt, guidance, and up to 20 steps | Beta and older than the FLUX.2 options |
| `@cf/black-forest-labs/flux-1-schnell` | Cheap, configurable from four to eight steps | Older generation than the tested FLUX.2 model |
| `@cf/stabilityai/stable-diffusion-xl-base-1.0` | General SDXL baseline | Beta, older, and not optimized for this workflow |

Sources: [Workers AI model catalog](https://developers.cloudflare.com/workers-ai/models/),
[current image pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/),
[Klein 9B launch and controls](https://developers.cloudflare.com/changelog/post/2026-01-28-flux-2-klein-9b-workers-ai/),
[FLUX.2 dev controls](https://developers.cloudflare.com/changelog/post/2025-11-25-flux-2-dev-workers-ai/),
[Lucid Origin](https://developers.cloudflare.com/workers-ai/models/lucid-origin/),
[Phoenix 1.0](https://developers.cloudflare.com/workers-ai/models/phoenix-1.0/),
and [DreamShaper 8 LCM](https://developers.cloudflare.com/ai/models/%40cf/lykon/dreamshaper-8-lcm/).

Cloudflare's Klein 4B deployment is fixed at four inference steps, so “running
it longer” is not available. Klein 9B is also fixed at four steps. The useful
Klein levers are seed, guidance, dimensions, prompt wording, and optional
reference images. The benchmark currently uses guidance `1.0`; higher guidance
is documented as following the prompt more closely, although excessive values
can reduce naturalness and should be tested rather than assumed.

The benchmark prompt itself says that “silhouettes” should remain readable.
That wording may encourage literal silhouette-only people. A later prompt
revision can instead request “clear forms and poses at small size, with fully
rendered subjects and no silhouette-only figures.” This is a more direct first
lever than increasing computation. For an actual longer-running Cloudflare
experiment, use FLUX.2 dev, whose `steps` parameter is configurable, or try the
enhanced Klein 9B model; neither is needed for the current production choice.

## Reproducing the aggregate report

```bash
uv run python scripts/benchmark_image_models.py aggregate-ratings \
  ~/Downloads/image-benchmark-finalist_efficient-ratings.json
```

The generated HTML and JSON are written under
`output/image-benchmark/ratings/`. The HTML initially ranks all models by
accepted-only weighted quality and also shows rejected-as-zero and raw scores,
rejection rates, runtime, memory pressure, and cost.
