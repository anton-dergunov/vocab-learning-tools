# Image benchmark guide

This is research tooling. It never changes the configured Anki image provider
or media cache.

## Install and inspect

```bash
uv sync
uv run python --version
uv run python scripts/benchmark_image_models.py list
```

The repository pins Python 3.12 in `.python-version` and constrains the uv
project to `>=3.12,<3.13`. Use `uv run` for benchmark commands so a newer
Homebrew `python` cannot accidentally select an incompatible environment.

Only `icon_scene` is enabled by default because it has no model download or
network call. Every heavyweight and remote candidate must be named explicitly.

## Offline smoke path

```bash
uv run python scripts/benchmark_image_models.py run \
  --stage smoke \
  --models icon_scene

uv run python scripts/benchmark_image_models.py render-review --stage smoke
```

Open `output/image-benchmark/smoke/review.html`. The self-contained gallery
stores in-progress ratings in browser local storage and downloads portable
JSON. Identities remain blind until **Reveal model identities** is used.

Use `resume` to skip jobs whose manifest and native/normalized output are
complete:

```bash
uv run python scripts/benchmark_image_models.py resume \
  --stage finalist \
  --models icon_scene mflux_flux2_klein_q4
```

## Prepare local models

Preparation is explicit and downloads only named candidates:

```bash
uv run python scripts/benchmark_image_models.py prepare \
  --models mflux_flux2_klein_q4 sdxl_turbo
```

The practical Z-Image profile for a 16 GB Apple Silicon machine uses the
pre-quantized 5.91 GB MFLUX checkpoint, not the roughly 33 GB reconstructed
Diffusers checkpoint:

```bash
uv run python scripts/benchmark_image_models.py prepare \
  --models mflux_z_image_turbo_q4

uv run python scripts/benchmark_image_models.py resume \
  --stage smoke \
  --models mflux_z_image_turbo_q4
```

It generates at 512×512 using nine steps, then follows the same 384px WebP
normalization path as every other candidate. It is a memory-tight comparison,
not the provisional default; avoid other memory-heavy applications while its
smoke run is active.

`uv` creates isolated environments and may install the requested Python on
first use. Weights remain in the normal Hugging Face cache. Individual models
can consume roughly 1–14 GB; preparing much of the catalog can exceed 30–50 GB.

Install Draw Things separately when testing it:

```bash
brew install drawthingsai/draw-things/draw-things-cli
draw-things-cli --help
```

Its model directory normally follows the Draw Things application. Override
`models_dir` in a local benchmark YAML when needed.

## Remote safety

Remote jobs require both `--execute-remote` and `--max-cost-usd`. The harness
checks the configured paid list-price projection before starting any runner:

Credential creation, safe shell configuration, verification, and
troubleshooting are documented in
[Cloudflare Workers AI setup](cloudflare-workers-ai.md).

```bash
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_API_TOKEN="..."
uv run python scripts/benchmark_image_models.py run \
  --stage smoke \
  --models cloudflare_flux2_klein \
  --execute-remote \
  --max-cost-usd 0.01
```

For Vertex AI Gemini, reuse Application Default Credentials:

```bash
gcloud auth application-default login
gcloud config set project "your-project-id"
gcloud auth application-default set-quota-project "your-project-id"
gcloud services enable aiplatform.googleapis.com --project="your-project-id"
export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
export GOOGLE_CLOUD_LOCATION="global"
```

Then select `gemini_flash_lite_image` or `gemini_flash_image`. The CLI ceiling
is not a provider billing budget; verify quotas and billing independently.

## Result contract

Each job directory contains:

- `request.json`: stable runner input.
- `runner-result.json`: backend result, versions, and provenance.
- `native.*`: untouched provider output.
- `native.sanitized.svg`: allowlisted SVG, where applicable.
- `normalized.webp`: 384×384 review/Anki-sized artifact.
- `resource-usage.txt`: macOS `/usr/bin/time -l` output when available.
- `manifest.json`: settings, timing, RSS, dimensions, sizes, cost, logs, and
  status.

Job IDs hash prompt, style, seed, candidate model/settings, and stage. A config
change therefore creates a distinct result instead of silently reusing media.

## macOS signal probe

Compile and run the diagnostic without installing a LaunchAgent:

```bash
swiftc tools/macos_idle_probe.swift -o /tmp/vocabgen-macos-idle-probe
/tmp/vocabgen-macos-idle-probe
/tmp/vocabgen-macos-idle-probe --watch --interval 1
```

If a restricted environment prevents Swift from writing its module cache, set
`CLANG_MODULE_CACHE_PATH` and `SWIFT_MODULECACHE_PATH` to temporary directories.
Validate while typing, using dictation, in Zoom/Meet, with camera on/off, and
while changing AC power. The probe never starts image generation.
