# Experiment · does adding two fields to the compose prompt thin the article?

Spike for [`docs/plans/lexibeat-integration.md`](../../docs/plans/lexibeat-integration.md) §2.8. The
plan keeps the decision; this document holds the question, the method and every number.

**Run:** 18 September 2026 · 20 words · four languages · three (provider, model) pairs · three
repeats · two arms.

## The question

A loop needs one term to speak and one direction for how the word sounds, so
`docs/plans/lexibeat-integration.md` puts `primaryGloss` and `emotion` on the lexeme and has the
**existing** compose prompt write them, rather than adding a second model call.

The risk is not that the two fields come out wrong. It is that a longer prompt **thins everything
else** — fewer senses, shorter notes, a `primaryGloss` that is only `shortGloss` again — and that
this would be invisible until a thousand articles had been written that way.

So: measure the rest of the article, paired, on the same words, through both prompts.

If it degrades, the answer is **not** to carve two fields into their own call — that is too small a
piece to justify a second prompt. It is to split `acervo_compose.md` into comparable parts,
considered whole, as its own task.

## The two arms

- `arms/before.md` — a byte copy of `prompts/acervo_compose.md` as it stood, sha256
  `7ca2c954…0151`, 10,603 bytes. Frozen before anything was edited.
- `arms/after.md` — the same file plus two keys in the shape block and two bullets in `Field rules:`,
  sha256 `2bfd36d4…ad49`, 12,018 bytes. **+1,415 bytes, +13.3%.** Prompt growth is reported, not
  bounded.

Both are rendered through the shipped reader, `acervo.services.prompts.sections`, and the request
around them is the shipped one: `acervo.services.capture.compose.build_user_message` assembles it and
`draft_from` reads the reply, so an arm is measured against the pipeline rather than against a copy
of it. Lifting `build_user_message` out of `compose()` is the only change this experiment made to
shipped code.

The resolve call is deliberately not made. `words.yaml` states the resolution, because resolve is a
separate prompt this experiment does not vary, and calling it would double the spend and add a second
source of variance to a paired comparison.

## Method

Three layers, and only one of them costs human attention.

| Layer | Covers | Answers |
| --- | --- | --- |
| 1 · deterministic metrics | all 360 calls | did the article get **thinner** |
| 2 · an LLM judge, blind and position-swapped | all pairs, ×2 orderings | did it get **duller** |
| 3 · 25 stratified human screens | a calibration set | **is layer 2 worth anything** |

Layer 3 does not produce the verdict. It produces a κ that says how far layer 2's verdict can be
trusted — and that number is reusable by every later prompt experiment, which is why the attention is
spent there rather than on reading 180 pairs.

### Layer 1

Everything about the article is read from the draft `draft_from` builds, so the numbers describe what
Acervo would actually have stored. The two new fields are read from the **raw reply**, because the
shipped parser silently ignores keys it does not know — which is exactly what lets the enlarged
prompt be measured before any schema exists for it. `draft_from` is a measurement here, never allowed
to abort a row: what the shipped path would refuse is one of the things being compared.

**The yardstick is the baseline's own variance.** Three repeats make it measurable: for each metric,
the mean absolute difference between two repeats of the *same* arm is compared with the mean
difference *between* arms. A between-arm gap no larger than the within-arm noise is not an effect.

### Layer 2

One call per pair per ordering, both articles as YAML with **the new fields stripped from the after
side** so the arm cannot be identified. Where the two orderings disagree the pair counts as *no
difference*, and the flip rate is reported: it is the instrument's own noise.

The judge is `vertex_ai/gemini-3.1-pro-preview` — a Pro model, and deliberately **not one of the
arms**, because grading a model's own output is the strong documented self-preference case and
`vertex_ai/gemini-3.8-flash` is an arm. Family preference may remain; every comparison is within one
arm-model, both sides from the same one, so it largely cancels.

### Layer 3

| n | stratum | what it buys |
| ---: | --- | --- |
| 8 | judge confident, both orderings agree | whether its confidence means anything |
| 5 | judge flipped between orderings | its weakest calls, checked |
| 5 | judge and the counts disagree | the "complete but duller" case, directly |
| 3 | uniform random | an unbiased anchor against the stratification |
| 4 | **control: two repeats of the same arm** | the reader's own false-positive rate |

Nothing on screen says which four are controls.

## Pre-registered thresholds

Written down before the measured run, and scored against afterwards.

| metric | bar |
| --- | --- |
| usable-answer rate | after ≥ before − 2 points |
| senses per word | paired median delta = 0, mean ≥ before − 0.15 |
| examples per sense | mean ≥ before − 0.15 |
| note characters | ≥ 90% of before |
| gloss completeness | 100% in both arms |
| `primaryGloss` present / a single term | ≥ 95% / ≥ 90% |
| `primaryGloss` copied a multi-meaning `shortGloss` | ≤ 10% |
| `primaryGloss` in the wrong script for the first gloss language | ≤ 5% |
| `emotion` identical to one of the article's example emotions | ≤ 10% |
| judge win rate for *before* | ≤ 55% |
| judge flip rate between orderings | ≤ 25%, else layer 2 is discarded |
| control false-positive rate | reported, not bounded — it calibrates everything else |
| median latency | ≤ before + 1.0 s |

## What the pilot changed, before the measured run

A 16-call pilot on the free tier found three things, and all three were fixed before spending the
night. Recording them because two were faults in the instrument rather than in the candidate:

1. **The candidate prompt was contaminated.** Its illustration of `emotion` used `asco`, which is in
   `words.yaml`, and the model returned the prompt's own phrase verbatim. An example drawn from the
   test set is an advantage only one arm has. The illustration now uses the entry already in the
   shape block.
2. **A metric was wrong.** `primaryGloss` equal to `shortGloss` was counted as a conflation failure,
   but for a word with one meaning the two *should* agree — `el miércoles` → `Wednesday` was flagged
   when it was correct. The failure is copying a **multi-meaning** `shortGloss`, and that is what is
   now measured.
3. **A real rule violation.** `麻烦` produced `troublesome`, in English, for a vocabulary that glosses
   into Russian first. The rule was restated in the candidate and a script check added to the scorer;
   the re-run produced `хлопотный` and `давай`.

## Results

Pending — the measured run was in flight when this was written.

## Reproducing

```sh
set -a; . ./.env; set +a
export ACERVO_VERTEX_PROJECT=…                      # the row needs it; ACERVO_VERTEX_ACCOUNT must stay unset

PYTHONPATH=experiments/compose-lesson-line .venv/bin/python \
  experiments/compose-lesson-line/score.py --selftest      # the metric, before any money
.venv/bin/python experiments/compose-lesson-line/run.py --dry-run

caffeinate -is ./experiments/compose-lesson-line/overnight.sh <runId>

cd experiments/compose-lesson-line/runs/<runId>/review && python3 -m http.server 8765
PYTHONPATH=experiments/compose-lesson-line .venv/bin/python \
  experiments/compose-lesson-line/review.py score experiments/compose-lesson-line/runs/<runId>
```

`runs/` is gitignored: 360 raw model replies per run are not worth a repository, re-scoring an
existing run is free, and every number this experiment claims is in this file.

## What this does not settle

- **Whether the two fields are well worded.** This run asks whether they can be added without cost,
  not whether they are as good as they could be. The pilot already suggested one tuning question:
  `picar` returned `emotion: null`, where something like *irritated, scratching at it* would serve a
  loop better. Where the `null` boundary should sit, and how vivid a word-level direction should be,
  is a separate tuning pass — and one worth doing before the fields ship, not instead of this.
- **Whether a model is right about a word.** `la sobremesa` → *after-dinner conversation* is a
  judgement call, and nothing here checks lexicography.
- **Anything about the other prompts.** Only `acervo_compose.md` is varied.
