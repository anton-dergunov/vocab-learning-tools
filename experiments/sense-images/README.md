# Experiment · sense image briefs

Iteration on the brief-writing prompt behind [`docs/features/sense-images.md`](../../docs/features/sense-images.md).
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
| [4](results/round-4.md) | 2026-09-05 | 100 | 126 of 127 kept | Gender must be written into the brief; commit to a concrete situation before writing; take the joke; every style needs to say what it is for |
| [5](results/round-5.md) | 2026-09-05 | 100 | 97 of 100 kept | The style hints backfired — stop sending them; text is banned only where it gives the answer away; draw the word, not only the sentence |
| [6](results/round-6.md) | 2026-09-06 | ~100 | 98 of 100 kept | The original-language definition outranks the English gloss; check the situation back before drawing it; a metaphor's vehicle must not read as something else |
| [7](results/round-7.md) | 2026-09-06 | 84 | 83 of 84 kept | Sampled hints work — keep both modes as a setting; keep the cast small so a bystander cannot outrank the subject; the style must not be doing the explaining |
| [8](results/round-8-english.md) | 2026-09-07 | 20 + 848 (English) | 17 of 20, then **50 of 50** | The qualifier separating a sense must be in the frame; a quality of speech lives in the listener, never as vapour from a mouth; concrete-but-hard-to-draw is not abstract. **Iteration closed.** |

## Outcome

Closed on 2026-09-07 with **2,285 images** — 1,437 Spanish senses and 848 of 851 English — and a
final review of 50 that rejected none. Twenty numbered failures were found and fixed across eight
rounds; the last three rounds went 83/84, 98/100 and 50/50.

The reject rate is the summary: 7 of 14 in round 1, none in 50 at the end. Everything that changed
in between is a prompt or a style-table edit, never a different image model.

## Method

One round is a `run --limit N` against real entries in the learner's own vocabulary, reviewed on the
contact sheet. Spanish runs live in `output/images/`, English in `output/images-en/` — separate
directories because they are separate review cycles, and the vocabularies differ in difficulty as
much as in language. Rejection is deleting the file; the rejects are copied to `output/images/round-N-rejected/`
first, so a later round can be compared against them on the same senses. Regenerating a rejected
sense writes a fresh brief and draws with a new seed, so a round is a genuine A/B on the same word
rather than a fresh sample of different words.

Judged on three axes, in this order, because they fail independently:

1. **Meaning** — would this picture help recall *this word* rather than its neighbours?
2. **Fidelity** — does the scene match the example sentence it was given?
3. **Craft** — is it a good picture?

Craft has never been the problem. It is listed third because a round that fixes 1 and 2 while
losing 3 would still be an improvement.
