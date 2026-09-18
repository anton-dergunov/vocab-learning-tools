# Experiments

Spikes, benchmarks and measured iterations, one directory each. Every directory holds its apparatus
and its write-up: the question, the method and the numbers. The design document or plan it serves
keeps only the decision, with a link back here.

Nothing here ships or is imported by the service (`tests/unit/server/test_layering.py`). An
experiment with heavy dependencies keeps them in its own environment, never in `requirements/`.

| Experiment | Question | Status | Serves |
| --- | --- | --- | --- |
| [`external-dictionaries/`](external-dictionaries/README.md) | Which container should an installed dictionary use, and is mapping a source onto Acervo's article model worth it over sanitised HTML? | Measured; Stage 1 built | [`docs/acervo-external-dictionaries.md`](../docs/acervo-external-dictionaries.md) |
| [`sense-images/`](sense-images/README.md) | What must the brief-writing prompt say for per-sense pictures to be kept? Eight review rounds. | Closed 7 Sep 2026, 2,285 images | [`docs/acervo-sense-images.md`](../docs/acervo-sense-images.md) |
| [`image_benchmark/`](../docs/image-benchmark.md) | Which image-generation model or route should draw vocabulary pictures: local diffusion, Mac-only models or cloud providers? | Tooling; results in the benchmark documents | [`docs/image-benchmark.md`](../docs/image-benchmark.md), [`docs/image-generation-research.md`](../docs/image-generation-research.md) |
| [`clip-translation/`](clip-translation/README.md) | Does the clip selector translate the *whole* passage it picked, and does demanding it in the prompt change what models do? | Measured 16 Sep 2026: severe truncation 8 → 0, full coverage 81% → 91%, McNemar p = 0.004. Prompt shipped. | [`docs/plans/spoken-clips.md`](../docs/plans/spoken-clips.md), [`docs/plans/translation-completeness-check.md`](../docs/plans/translation-completeness-check.md) |
| [`photo-capture/`](photo-capture/README.md) | Can you photograph a page, tap a word and see its meaning in context fast and accurately enough? Which OCR, which sentence splitter, which model? | Spanish spike run 15 Sep 2026: Cloud Vision yes, RapidOCR on the NAS no | [`docs/plans/photo-capture.md`](../docs/plans/photo-capture.md) |
| [`pronunciation-encoding/`](pronunciation-encoding/README.md) | A stored pronunciation sounds metallic — is that the bitrate Cloud TTS is asked for, or the model? Which encoding should a replicated clip be in? | Blind listening, 15 Sep 2026 | [`docs/plans/pronunciation-and-audio.md`](../docs/plans/pronunciation-and-audio.md) |
| [`compose-lesson-line/`](compose-lesson-line/README.md) | Does adding `primaryGloss` and `emotion` to the compose prompt thin the rest of the article? | Measured 18 Sep 2026: no degradation — all ten substance metrics move less than their own run-to-run noise, and the blind read found a **50% false-positive rate on same-arm controls** (κ = −0.10 against a Pro judge), so there is nothing to see. Fields shipped, prompt not split | [`docs/plans/lexibeat-integration.md`](../docs/plans/lexibeat-integration.md) |

`image_benchmark/` is a Python package rather than a hyphenated directory, because its tests and
its command line import it: `python -m experiments.image_benchmark.benchmark_image_models list`.
