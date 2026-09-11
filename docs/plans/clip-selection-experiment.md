# Experiment · the clip-selection prompt

**Status:** Unstarted. Step 3 of [`spoken-clips.md`](spoken-clips.md) has shipped the first version
of the prompt this experiment tunes, and a first reading of it — three runs over eight words, read
by eye — is [`clip-selection-round-1.md`](../clip-selection-round-1.md). That was enough to find one
real failure and fix it; it is **not** this experiment, which nobody has run. Its starting point is
the prompt as that round left it.

## The question

Given one lexeme's senses and a bounded set of caption segments retrieved for it, **which segment —
if any — is a good example of which sense?**

This is the one place in the clip pipeline where a frontier model earns its cost. The corpus finds
occurrences with traditional IR because it has millions of segments and cannot afford a model call
per candidate. Acervo spends exactly one call per word, at the very top of the funnel, on the
judgement a feature cannot make: is this messy fragment really an instance of *this* meaning, and is
it worth a learner's attention?

## What "good" means, and why that is the hard part

There is no ground truth to appeal to, so the rubric has to be written down before anything is
measured. A first attempt, to be revised once real output has been read:

| | A clip is good when | It is not good when |
|---|---|---|
| **Sense** | it is unmistakably *this* sense, not a neighbouring one | it fits the headword but not the sense, or the sense is unrecoverable from the fragment |
| **Completeness** | the sentence stands on its own | it starts or ends mid-clause, or its subject is two turns back |
| **Naturalness** | a speaker said it the way speakers say it | it is a definition, a title read aloud, a list, or a lesson explaining the word |
| **Usefulness** | a learner would be glad it is there | it is technically correct and adds nothing over the generated example above it |
| **Cleanliness** | it needs no apology | proper nouns dominate, the register is wrong for the word, the caption is garbled |

**Refusing is a success, not a miss.** The corpus is small and will stay small for a long time. The
prompt's failure mode to hunt is not "found nothing" — it is "found something mediocre and presented
it as evidence". Precision over recall, deliberately and by a wide margin.

## The cheapest useful method first

The direct loop, run by hand:

1. Take 25–40 saved lexemes with real senses, weighted toward the polysemous ones — those are where
   sense confusion shows up at all, and a monosemous word tells you almost nothing.
2. Run the search and the selection call, keeping **every** intermediate artifact: the query sent,
   the full candidate set with ranks and scores, the raw model output, the parsed selections, the
   validation outcome, and which candidates were dropped.
3. Read the output against the rubric. Label each selection `good` / `borderline` / `bad`, and each
   *refusal* `right` / `missed` by reading the candidates it declined.
4. Change one thing in the prompt. Re-run the same set. Compare.

Keep the artifacts on disk under a run directory, the way the image runs already do, so a later run
can be compared against an earlier one rather than remembered.

The two numbers that matter, with their denominators stated: **of the clips selected, how many are
good** (precision — the one to optimise) and **of the words where a good candidate existed, how
often was it found** (recall — the one to watch for collapse). A third worth tracking because it is
free: how often the model returned an id it was not offered.

An LLM judge calibrated against these labels is worth building **only if** the hand loop becomes the
bottleneck. It probably will not at this scale, and the labels collected here are what would
calibrate one anyway. Do not start there.

## What to vary

In roughly this order, one at a time:

- **Candidate count.** 10 / 20 / 40. Too few and the good clip is never offered; too many and the
  prompt drowns and precision falls. This is the cheapest knob and it may matter more than any
  wording.
- **What a candidate carries.** Sentence alone, versus sentence plus channel, speech style, regional
  variety, caption kind (authored or automatic), and the boundary reason the segment closed on. The
  corpus retains all of it precisely because it should be able to inform a judgement — but each
  field is prompt weight, so each has to earn its place.
- **What a sense carries.** Definition alone, versus definition plus glosses, versus plus the
  existing examples. **Suspect the glosses.** The image brief writer was burned by exactly this: an
  English gloss is a rough handle chosen for closeness, and its metaphors are not the word's — it
  drew *ground* for *estar fundado*. The definition in the language being learned is likely the
  authority here too, and that is a hypothesis to test rather than assume.
- **How refusal is framed.** Whether the prompt says "select the best" or "select only if a learner
  would be glad it is there, and otherwise select nothing". Expect this to be the largest single
  effect on precision.
- **Whether the model explains itself.** A one-line reason per selection costs tokens and may
  improve the judgement; it certainly makes the labelling pass faster. Decide on evidence, and note
  that a reason that is never stored is still worth having during tuning.

## Constraints the prompt may not break

These are not tuning parameters. They come from [`spoken-clips.md`](spoken-clips.md) §2 and hold
whatever the measurements say:

- The selected text is the corpus's sentence **verbatim**. No trimming, joining or rewriting.
- At most one clip per sense, and none is a valid answer for every sense.
- Only ids from the request's candidate set. Anything else is dropped and counted.
- One call per lexeme, covering all of its senses at once — the batching is what lets the model tell
  two senses of one word apart, which is the whole reason for per-sense clips.

## What to write down

A report under `docs/`, in the shape the other repository's `AGENTS.md` asks for and for the same
reason: the evidence has to be auditable rather than asserted. The hypothesis and its success
criterion; the exact model, prompt version and candidate configuration for every run; the language
and the word set with its selection method; per-example diagnostics kept, not just averages; the
rubric as actually applied, with successful, borderline and failed examples quoted; and the run
directory the numbers came from.

Record a negative result the same way. "Adding speech style changed nothing" is worth a line, and
saves the next session from trying it.

## When to stop

When precision on the labelled set is high enough that reading a random article does not make you
wince, and refusals look right when you check the candidates they declined. That is a judgement call
and it is the correct kind of judgement call — the feature exists so that articles are better to
read, and the person reading them is the measure.

Anything beyond that belongs to the retrieval repository: better candidates make this prompt's job
easier, and that is where the ranking work lives.
