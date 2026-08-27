# Image generation for vocabulary cards

Research snapshot: 2026-08-27. Prices, quotas, availability, and licenses can
change; verify the linked primary source before a large run.

## Recommendation

The scored finalist benchmark now supports this operating hierarchy:

1. The existing emoji as the zero-cost guaranteed fallback.
2. A deterministic icon scene: an LLM selects a few pinned icons, colors, and
   relationships; a low-power machine renders a safe 384px asset.
3. Cloudflare FLUX.2 Klein 4B for low-cost steady-state generation.
4. Gemini 3.1 Flash Lite Image for the initial bulk import while temporary
   Vertex credit/access remains available.
5. No local diffusion default yet. DreamShaper is the most interesting artistic
   option if low-information failures can later be detected and retried.

The full scores, rejection-aware and accepted-only rankings, measured resource
pressure, and current Cloudflare alternatives are recorded in
[the finalist benchmark report](image-benchmark-finalist-results.md).

The target is not photographic fidelity. It is an attractive, unambiguous
visual anchor that survives unattended generation and remains legible at
approximately 192–384 pixels.

## Current implementation

`config/defaults.yaml` selects `dreamlike-art/dreamlike-photoreal-2.0`. The
tracked line was added in October 2025, but the model is a Stable Diffusion 1.5
fine-tune from the earlier generation of diffusion models. Its model card says
it was trained at 768×768 and adds hosting/inference restrictions to modified
OpenRAIL terms. Those restrictions matter if this later becomes a shared
service, even though private personal output use is a much smaller concern. The
card also warns about NSFW propensity.
[Dreamlike model card and license](https://huggingface.co/dreamlike-art/dreamlike-photoreal-2.0)

The current adapter does not pass configured width and height into the
pipeline. It generates at the pipeline default and only then resizes to
384×384. The benchmark therefore records generation and normalized output
dimensions separately.

## Local candidate matrix

These are candidates, not quality conclusions. Download sizes are planning
ranges because model revisions, precision, safety checkers, and conversion
caches materially change them.

| Candidate | Test configuration | Planning download | M1 16 GB outlook |
|---|---|---:|---|
| FLUX.2 Klein 4B / MFLUX Q4 | 4 steps, 512px, guidance 1 | 5–12 GB including caches | Best proven local candidate |
| FLUX.2 Klein / Draw Things Q6P | Same model through native runtime | 6–12 GB | Strong runtime comparison |
| SDXL Turbo | 1 step, 512px | 7–14 GB | Fast but older and relatively large |
| LCM DreamShaper v7 | 4 steps, 512px | 3–5 GB | Likely practical |
| TinySD | 20-step compact baseline | 1–2 GB | Compact; quality may be too weak |
| Segmind Vega | Distilled 0.7B SDXL alternative | 3–6 GB | Worth a smoke test |
| Sana Sprint 0.6B | Modern 1–4-step model | 2–5 GB | MPS path is experimental |
| Z-Image Turbo / Diffusers | Full checkpoint; 9 steps, 512px | 18 GB download / about 33 GB reconstructed | Not viable on the 16 GB M1 |
| Z-Image Turbo / MFLUX Q4 | Pre-quantized 4-bit; 9 steps, 512px | 5.91 GB | Memory-tight smoke candidate, not a default |
| StarVector 1B | Experimental text-to-SVG | Several GB | Upstream text path is fragile |

FLUX.2 Klein 4B is a four-step distilled Apache-2.0 model whose official
requirements describe consumer operation around 13 GB VRAM at larger
resolutions. Although the model accepts small dimensions, direct generation at
128–200 pixels discards useful capacity and is more prone to malformed
concepts. Generate at 512px and downsample. The attached MFLUX experiment
already demonstrates useful 512px output. [BFL overview](https://docs.bfl.ai/flux_2/flux2_overview),
[model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B), and
[MFLUX](https://github.com/filipstrand/mflux).

Draw Things provides a native CLI and explicitly documents FLUX.2 Klein. The
benchmark uses one-shot processes so unified memory is returned after each
image. [Draw Things CLI](https://github.com/drawthingsai/draw-things-community)

Other primary model sources:

- [SDXL Turbo](https://huggingface.co/stabilityai/sdxl-turbo)
- [LCM DreamShaper v7](https://huggingface.co/SimianLuo/LCM_Dreamshaper_v7)
- [TinySD](https://huggingface.co/segmind/tiny-sd)
- [Segmind Vega](https://huggingface.co/segmind/Segmind-Vega)
- [Sana Sprint](https://github.com/NVlabs/Sana)
- [Z-Image Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)
- [MFLUX Z-Image Turbo 4-bit](https://huggingface.co/filipstrand/Z-Image-Turbo-mflux-4bit)
- [StarVector 1B](https://huggingface.co/starvector/starvector-1b-im2svg)

The pre-quantized Z-Image checkpoint is a reasonable one-time smoke test. It is
a 6B, nine-step model and therefore heavier than four-step FLUX.2 Klein 4B.
Community reports put normal MFLUX generation around 9–10 GB with a potentially
larger decode-time spike, so a 16 GB Mac may still encounter memory pressure.
Its potential quality gain is unlikely to justify making it the unattended
default for 384px vocabulary anchors unless blind review scores it materially
higher than Klein.

StarVector is intentionally experimental. Its 1B checkpoint is named `im2svg`;
the model card claims text-to-SVG, while upstream examples focus on image-to-SVG
and open issues document missing/broken text generation. Its runner records
this as one model failure rather than aborting the benchmark.

## Hosted and free-resource economics

| Route | Approximate 1,000-image cost | 10–20/day | Assessment |
|---|---:|---|---|
| Cloudflare FLUX.2 Klein | $0 within sufficient daily quota; about $0.287 at listed paid inference price | Excellent | Strongest hosted candidate |
| BFL direct FLUX.2 Klein | From $14 | Good | Simple paid fallback |
| Gemini 3.1 Flash Lite Image | About $33.60 standard; lower in batch | Good while credits last | Temporary bulk route |
| Gemini 3.1 Flash Image | About $67 standard | Good while credits last | Use only if Lite is insufficient |
| Gemini 3 Pro Image (Nano Banana Pro) | About $134 standard for 1K/2K | Best credit-backed quality candidate | Difficult meanings and premium bulk run |
| Hugging Face ZeroGPU free | Time allocation, not a stable image quota | Poor | Demo/experiment only |
| Modal Starter | Potentially covered by monthly credit | Viable | More deployment work |

Cloudflare currently grants 10,000 Workers AI neurons daily. FLUX.2 Klein is
listed at 26.05 neurons and $0.000287 per 512×512 output tile, implying about
383 text-only 512px outputs inside the daily allocation if nothing else consumes
it. Free accounts hard-stop at quota rather than silently billing.
[Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
and [model API](https://developers.cloudflare.com/workers-ai/models/flux-2-klein-4b/)

BFL lists FLUX.2 Klein 4B from $0.014 per image.
[BFL pricing](https://docs.bfl.ai/quick_start/pricing)

The ordinary Gemini Developer API free tier does not make image models a
dependable free backend; Vertex credit-backed access is separate. At the
research date, published standard 1024px output prices are approximately
$0.0336 for Gemini 3.1 Flash Lite Image and $0.067 for Gemini 3.1 Flash Image;
batch pricing is lower. [Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation)
and [pricing](https://ai.google.dev/gemini-api/docs/pricing)

Gemini 3.1 Flash Image is the model currently branded Nano Banana 2. Gemini 3
Pro Image is Nano Banana Pro and is Google's highest-quality option for complex
image generation and editing. The premium benchmark requests 2K because Pro's
current listed output charge is the same for 1K and 2K and the successful Vim
Mastery workflow used 2K. The final Anki artifact is still normalized to 384px;
the main expected gain comes from Pro's reasoning plus a concrete art-directed
mnemonic brief, not from retaining a larger final file.

Hugging Face ZeroGPU gives a free account five GPU minutes daily and uses
shared scheduled capacity. Inference Providers give free users only a small
monthly credit. [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu) and
[Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing)

Modal advertises $30/month Starter compute credit and no idle container
billing, but adds container lifecycle, cold-start, storage, and model-download
engineering that Cloudflare avoids. [Modal pricing](https://modal.com/pricing)

Community services such as AI Horde or ad-supported endpoints may suit manual
experiments, but their latency, availability, privacy, and model stability are
not dependable enough for the automatic default.

## The middle tier: icons, SVG, and retrieval

The icon scene uses a constrained schema rather than arbitrary LLM-authored
SVG. A future planner selects one to three whitelisted icons, colors, layout,
and a relation such as an arrow. The deterministic renderer can run on a NAS or
Raspberry Pi, represents phrases better than one emoji, and is safe to cache.

The benchmark begins with original geometric primitives. A production version
can pin permissive assets from [Material Symbols](https://developers.google.com/fonts/docs/material_symbols),
[Noto Emoji](https://github.com/googlefonts/noto-emoji), and an explicit
license allowlist discovered through [Iconify](https://iconify.design/docs/api/).
Individual Iconify collections must not be accepted blindly because their
licenses differ.

Openverse retrieval is restricted to CC0/public-domain-marked results,
downloads a small candidate set, and ranks it locally with CLIP. It stores
source and license metadata. Openverse warns that it cannot guarantee upstream
license accuracy, so results remain marked for verification.
[Openverse documentation](https://docs.openverse.org/api/reference/made_with_ov.html)

Pexels is free and aesthetically strong, but its API asks clients to link to
Pexels and credit photographers where possible. That creates attribution work
inside cached Anki media, so it is documented but excluded from phase 1.
[Pexels API guidelines](https://www.pexels.com/api/documentation/)

## Anki media and video

Use static 384px WebP images by default. Anki supports video and MP4 is the most
portable choice, but associated media is synchronized to clients; mobile Anki
does not selectively omit video for one subdeck. [Anki media](https://docs.ankiweb.net/media.html),
[file limits](https://faqs.ankiweb.net/are-there-limits-on-file-sizes-on-ankiweb.html),
and [sync behavior](https://faqs.ankiweb.net/media-files-may-take-time-to-sync.html)

If motion is evaluated later, restrict it to a curated set of difficult actions
or idioms, use short low-resolution clips without audio, and measure collection
growth before scaling it. It should not be part of the automatic first pass.

## macOS idle-worker design

`tools/macos_idle_probe.swift` validates public signals without scheduling or
launching work. The later LaunchAgent defaults are:

- Five minutes since keyboard or pointing-device input.
- AC power only; Low Power Mode off.
- Nominal thermal state and normal memory availability.
- No active Core Audio input device and no camera in use.
- Two quiet minutes after microphone or camera capture ends.
- One image per child process, with gates rechecked every second.
- Terminate and requeue on activity; never suspend a model while retaining
  unified memory; fail closed when a gate is unavailable.

Apple exposes thermal/Low Power Mode through [`ProcessInfo`](https://developer.apple.com/documentation/foundation/processinfo),
power source through [`IOPSGetProvidingPowerSourceType`](https://developer.apple.com/documentation/iokit/iopowersources_h/1810316-iopsgetprovidingpowersourcetype),
input activity through [`kAudioDevicePropertyDeviceIsRunningSomewhere`](https://developer.apple.com/documentation/coreaudio/kaudiodevicepropertydeviceisrunningsomewhere),
and camera use through [`AVCaptureDevice.isInUseByAnotherApplication`](https://developer.apple.com/documentation/avfoundation/avcapturedevice/isinusebyanotherapplication).

Any microphone capture is deliberately a hard stop. This catches Zoom/Meet,
audio calls, and local dictation without classifying the application, and it
does not confuse ordinary speaker output with input.

There is no dependable public aggregate API saying another application is
sharing the screen. ScreenCaptureKit manages an app's own streams; it does not
expose other apps' streams. Deprecated `CGDisplayIsCaptured` describes
exclusive display capture, not modern browser/meeting presentation. A muted,
camera-off presentation therefore needs a future manual pause control.
[ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit)
and [Quartz display capture](https://developer.apple.com/documentation/coregraphics/quartz-display-services)

## Deferred until blind review

- Production `vocabgen.vision` providers and `config/defaults.yaml` changes.
- Media-cache provenance migration and automatic fallback orchestration.
- NAS/Raspberry Pi queue service and the Mac LaunchAgent.
- Video generation.

The exported ratings determine which production changes should be designed
next.
