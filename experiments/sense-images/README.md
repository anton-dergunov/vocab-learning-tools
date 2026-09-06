# Experiment · sense image briefs

Iteration on the brief-writing prompt behind [`docs/acervo-sense-images.md`](../../docs/acervo-sense-images.md).
The apparatus is `scripts/generate_images.py`; this directory holds the review of each round and the
prompt change it argued for. Findings that survive get written back into the design document.

The thing being iterated is **not** the image model. Gemini 3.1 Flash Lite Image is doing an
exceptional job — the reviewer's word — and every failure below is a failure of the text we hand it.
That separation is the whole reason the pipeline has two calls.

## Rounds

| Round | Date | n | Verdict | Change it argued for |
|---|---|---:|---|---|
| [1](results/round-1.md) | 2026-09-05 | 14 | 7 rejected | The style must stop authoring the scene; the example sentence must be honoured; the meaning must be *depicted*, not implied |
| [2](results/round-2.md) | 2026-09-05 | 14 redrawn + 3 | 16 of 17 kept | Exaggerate by adding to the subject, never by diminishing the scene; give aspect and modality a human situation; stop passing the owner's topics |
| [3](results/round-3.md) | 2026-09-05 | 11 new | all 11 kept | Drama belongs to the rendering, not the stakes — match the sentence's register and let a light sentence be funny; a change of state needs both states in frame |
| [4](results/round-4.md) | 2026-09-05 | 100 | in progress | — |

## Method

One round is a `run --limit N` against real entries in the learner's own vocabulary, reviewed on the
contact sheet. Rejection is deleting the file; the rejects are copied to `output/images/round-N-rejected/`
first, so a later round can be compared against them on the same senses. Regenerating a rejected
sense writes a fresh brief and draws with a new seed, so a round is a genuine A/B on the same word
rather than a fresh sample of different words.

Judged on three axes, in this order, because they fail independently:

1. **Meaning** — would this picture help recall *this word* rather than its neighbours?
2. **Fidelity** — does the scene match the example sentence it was given?
3. **Craft** — is it a good picture?

Craft has never been the problem. It is listed third because a round that fixes 1 and 2 while
losing 3 would still be an improvement.
