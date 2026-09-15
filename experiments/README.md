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
| [`photo-capture/`](photo-capture/README.md) | Can you photograph a page, tap a word and see its meaning in context fast and accurately enough? Which OCR, which sentence splitter, which model? | Spanish spike run 15 Sep 2026: Cloud Vision yes, RapidOCR on the NAS no | [`docs/plans/photo-capture.md`](../docs/plans/photo-capture.md) |

`image_benchmark/` is a Python package rather than a hyphenated directory, because its tests and
its command line import it: `python -m experiments.image_benchmark.benchmark_image_models list`.
