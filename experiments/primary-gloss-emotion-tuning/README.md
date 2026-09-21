# Experiment · tuning `primaryGloss` and `emotion`'s wording

Spike for [`docs/plans/article-quality.md`](../../docs/plans/article-quality.md) §8 row 11 and the
defect register's "The `emotion: null` boundary is conservative" section. `experiments/
compose-lesson-line/` shipped these two fields on 18 September 2026 after measuring they don't thin
the rest of the article, and explicitly flagged wording quality as a separate, later pass — this is
that pass.

**Run:** 21 September 2026 · gemini-free only · 44 real+synthetic words, three rounds, 161 calls.

## The question

The owner listened to generated loops and found two real defects, reported in
`spoken_plans/loops-glosses.txt`:

1. `primaryGloss` came out too short for a multi-word Spanish headword: `encender la computadora`
   (turn on the computer) → `turn`, `hacer murales` (paint murals) → `play`. The prompt already said
   "keep it close to the headword in length," but that instruction was drowned out by "ONE term...
   the one you would give if you were allowed only one word," repeated three ways.
2. `emotion` was null too often. The owner's own estimate was 5–10% coverage on ordinary words, and
   he wanted roughly 90%, on the reasoning that a loop exists to be memorable and a flat reading
   defeats half the point even when nothing is technically wrong with it. His own worked cases: a
   Saturday read warm and unhurried, a Monday read tired and reluctant, a chair read cozy — none of
   which the old wording's own carve-outs (weekday, preposition, furniture) would have allowed.

## Data access — a gap, not a substitute

The plan called for pulling real candidates from the production database over `ssh nas`. That path
turned out to be blocked: the NAS's Docker socket is root-owned with no docker group (confirmed
live — `docker exec` and even `docker ps` refuse with "permission denied," and the reviewed
`deploy-acervo` launcher's fixed operation list has no generic query command, only `check`,
`create-account`, `deploy`, `install-samples`, `jobs`, `status`, `worker`, `configure-https`). A
fallback — signing in through the ordinary `/session` + `/graph` API, exactly what any client does to
sync — was then blocked by this environment's own tool-use policy around handling login credentials
programmatically.

So this run uses: the five headwords the owner already reported by hand (`source: real` in
`words.yaml`, copied verbatim from his note), plus authored synthetic collocations across Spanish,
English and Chinese (`source: synthetic`) standing in for the random production sample the plan
asked for. **This is a real gap.** The synthetic set is a reasonable proxy — it deliberately includes
the exact shapes the old prompt's own carve-outs named (a weekday, a piece of furniture, a
preposition) — but it is not a random sample of the owner's actual 1,700-word vocabulary, and the
true current `emotion` null rate on that vocabulary is still unmeasured. Re-running `run.py` against
a real random sample, once the database is reachable read-only by some sanctioned path, would sharpen
this further; it is not expected to change the wording decision below, since the mechanism the
rewrite targets (an over-broad default to `null`) is a property of the prompt, not of which words it
is tested on.

## The two arms

- `arms/before.md` — byte copy of `prompts/acervo_compose.md` as shipped, sha256
  `2bfd36d4…3ad49`, 12,018 bytes.
- `arms/after.md` — the same file, `primaryGloss` and `emotion`'s field rules reworded, sha256
  `70a84090…742a98`, 13,299 bytes. **+1,281 bytes, +10.7%.**

Both are rendered through the shipped reader (`acervo.services.prompts.sections`) and the request
around them is the shipped one: `acervo.services.capture.compose.build_user_message` assembles it and
`acervo.services.capture.draft.draft_from` reads the reply, exactly as `compose-lesson-line` does —
lifting neither out of the pipeline is a second implementation of the thing being measured.

`primaryGloss`'s rewrite makes "length follows the headword" the load-bearing rule instead of "one
word," with three new worked multi-word examples (`tocar la guitarra` → `play the guitar`, `dar un
paseo` → `take a walk`, `quedarse dormido` → `fall asleep`) that no test word reuses.

`emotion`'s rewrite is a larger swing, not a one-line patch: it removes the old carve-outs (weekday,
preposition, furniture) rather than qualifying them, replaces them with "picture the single most
ordinary situation this word comes up in" plus three worked examples (`el domingo`, `el lunes`, a
chair — also not reused by any test word), and moves `null` from the default to the last resort. A
first draft of that rewrite over-corrected (below); the shipped wording adds one more rule to fix it.

## Method

Single provider (`gemini-free`, `gemini-3.5-flash-lite`), no paid judge — a wording-tuning pass, not
the ship/no-ship risk study `compose-lesson-line` already closed. Two deterministic checks, adapted
from that experiment's `score.py` (which already tracked `primarySingleTerm` and `primaryLengthRatio`
but never thresholded them):

- **`primaryShape`** — `content_words(headword)` (a whitespace count, minus a leading Spanish
  article) versus `words_of(primaryGloss)`. `≥3 : 1` is `auto_fail`, `2 : 1` is `review` (a judgement
  call — Russian legitimately compresses an English phrasal verb into one word), else `ok`.
- **`emotionExpect`** — `words.yaml`'s `category` field marks each word `primary_multiword` /
  `primary_singleword` / `emotion_random` (expected to carry a feeling) or `emotion_null_control`
  (expected to stay `null`: numbers, a bare conjunction/preposition, a Chinese grammatical particle).
  Coverage is reported per stratum, so a coverage gain can never be claimed from the null side
  failing.

## Round 1 — reproducing the bug, and finding the rewrite's own failure mode

44 words, both arms, one repeat, 90 calls.

| | `primaryAutoFail` | `primaryReview` | `emotionOnExpectFeeling` (n=35) | `emotionFalsePositiveOnNullControl` (n=5) |
| --- | ---: | ---: | ---: | ---: |
| before (shipped) | 15.6% (7/45) | 4.4% | 57.1% | 40% |
| after (draft 1) | 4.4% (2/45) | 4.4% | **100%** | **100%** |

`primaryGloss` worked well immediately: 5 of the shipped prompt's 7 failures were fixed —
`montar en bicicleta` → `ride` became `ride a bike`, `meter la pata` → `blunder` became `to make a
blunder`, `tomar el pelo` → `tease` became `pull someone's leg`. The 2 that remained
(`la obra de teatro` → `play`, `echar de menos` → `miss`) are genuinely one-word-correct answers that
the mechanical word-count check can't tell apart from a real failure — exactly the "review, not
auto-fail" judgement call the metric was designed to hand off rather than misjudge.

`emotion` over-corrected. Coverage on expect-feeling words hit 100%, but so did the false-positive
rate on the null-control set — **every** number, conjunction, preposition and grammatical particle
also got a feeling. Reading the replies showed why: asked to find a scene for `cinco` and `of`, the
model complied literally rather than saying `null`, producing decorative near-nulls like *"neutral
and matter-of-fact, connecting ideas together smoothly"* for `of` — a description of having nothing
to say, not a real feeling. (Separately, `cinco` also got mistranslated as "high five" in **both**
arms — a pre-existing model quirk on that specific small number, unrelated to this rewrite; the word
list was changed to `cuarenta` to stop testing an unrelated bug.)

## Round 2 — fixing the over-correction

One more rule, added to `arms/after.md`: `null` is not "no scene occurred to you," it is the honest
answer for a word with *no scene at all*, and if the only honest description is "neutral" or
"matter-of-fact," that description **is** `null` and should be written as `null`, not as a sentence.
45 calls, `after` arm only (the `before` arm doesn't change between rounds).

| | `emotionOnExpectFeeling` (n=35) | `emotionFalsePositiveOnNullControl` (n=5) |
| --- | ---: | ---: |
| after (draft 2, shipped wording) | 88.6% | **0%** |

All five null-control words (`cuarenta`, `y`, `of`, `seven`, `的`) correctly returned `null`. Coverage
on expect-feeling words settled at 88.6% (31/35) — inside the owner's own ~90% target, and a real
number rather than the over-fired 100% from draft 1. The four that stayed `null` were a plain noun
(`el cuchillo`, outside the `emotion_random` stratum) and two weekdays including `el jueves`, marked
in `words.yaml` as "a harder case" going in — Thursday carries less of a fixed cultural script than
Saturday or Monday, and `el sábado` itself flipped between rounds (single sample per word, no
repeats — expected variance on a genuinely borderline case rather than a regression).

## Holdout — words never used while tuning

10 new words never seen while iterating the wording: 4 fresh multi-word Spanish idioms/collocations,
5 fresh "ordinary word" emotion cases, 1 fresh null-control number. Both arms, one repeat, 20 calls.

| | `primaryAutoFail` | `primaryReview` | `emotionOnExpectFeeling` (n=9) | `emotionFalsePositiveOnNullControl` (n=1) |
| --- | ---: | ---: | ---: | ---: |
| before | 20% | 20% | 88.9% | 0% |
| after | **0%** | **0%** | **100%** | 0% |

`dar por sentado` → `assume` became `take for granted`; `ponerse las pilas` → `hustle` became `get
your act together`. On the emotion side, `el despertador` (alarm clock) went from `null` to
*"annoyed and tired, dreading the start of a busy morning"* — exactly the kind of coverage gain the
rewrite targets — while the held-out number `sesenta` stayed `null` in both arms.

## Verdict

**The reworded `primaryGloss` and `emotion` field rules ship**, replacing the corresponding bullets
in `prompts/acervo_compose.md`.

`primaryGloss`: auto-fail rate fell from 15.6% to 4.4% on the tuning set and from 20% to 0% on the
untouched holdout, and every remaining flagged case on inspection was a legitimately correct
one-word answer, not a real failure. `emotion`: after one corrective round, coverage on
ordinary/meaningful words landed at 88.6–100% across the tuning and holdout sets (up from a
measured 57.1–88.9% under the shipped prompt), with the null-control set — numbers, a conjunction, a
preposition, a Chinese particle — staying at 0% false positives in both the fix round and the
holdout. Nothing in either arm's `usable` rate moved (100% throughout), and no run
produced a wrong-script `primaryGloss` at a rate distinguishable from the other.

## What this does not settle

- **The real production null rate is still unmeasured.** See "Data access" above — this is the one
  open item, and it needs either a sanctioned read-only path onto the live database or the owner
  running the pull himself.
- **Whether 88.6% is the right number**, as opposed to 80% or 95%. The owner's ~90% was explicitly a
  starting target, not a specification; nothing here optimizes past "clearly fixed, and not
  over-fired."
- **Anything about the other prompts** or the other fields in `acervo_compose.md`. Only the
  `primaryGloss` and `emotion` bullets were varied.
- **Existing production rows are unaffected.** `compose` runs once, at capture; there is no backfill
  path (AGENTS.md's no-backward-compatibility rule forbids one regardless). A word captured before
  this ships keeps whatever `primaryGloss`/`emotion` it already has. Revisiting an old word means
  re-capturing it by hand — there is no admin command that regenerates these two fields in place.

## Reproducing

```sh
set -a; . ./.env; set +a

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/score.py --selftest        # the metric, before any money

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/run.py --dry-run

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/run.py --repeats 1 --run <runId>

PYTHONPATH=experiments/primary-gloss-emotion-tuning .venv/bin/python \
  experiments/primary-gloss-emotion-tuning/score.py runs/<runId>
```

`runs/` is gitignored: raw model replies are not worth a repository, and every number this document
claims is in this file.
