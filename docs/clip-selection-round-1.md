# Clip selection · round 1

**Status:** a first reading, not a measurement. Three runs of the real pipeline against the real
corpus and a real provider, read by eye. The method `docs/plans/clip-selection-experiment.md` calls
for — 25–40 lexemes, a labelled rubric, precision and recall with stated denominators — has **not**
been carried out. What is here is the smaller thing worth doing before it: does v1 of the prompt
work at all, and is anything obviously broken.

| | |
| --- | --- |
| Prompt | `prompts/acervo_clip_select.txt`, v1 (rounds 1) and v1 + the cut-quality section (rounds 2–3) |
| Model | `gemini/gemini-3.1-flash-lite`, through `acervo.models` on the chain `gemini-free` |
| Corpus | spoken-usage-retrieval 0.2.0, Spanish, 251 videos / 60,704 segments, index built 11 Sep 2026 |
| Candidates | 20, `match_mode=auto`, `order=ranked` — the shipped configuration, unvaried |
| Words | 8 Spanish lexemes, 14 senses, chosen for polysemy and for colloquial register |
| Run directory | scratch only; the runner and its JSON are not tracked |

## What the numbers were

| Run | Prompt | Senses filled | Hallucinated ids | Median |
| --- | --- | --- | --- | --- |
| 1 | v1 | 11 / 14 | 0 | 2.6 s |
| 2 | v1 + cut-quality | 10 / 14 | 0 | 1.5 s |
| 3 | v1 + cut-quality | 9 / 14 | 0 | 5.2 s |

**Nothing hallucinated a segment id in any run.** That is the one number the drop-and-count path
exists to surface, and at this scale it is zero — which is worth knowing before deciding whether the
counter is load-bearing or merely cheap insurance.

## The one failure worth changing the prompt for

Round 1 selected two passages that were **cut badly** rather than wrongly chosen. The sense was
right and the word was used properly; the passage simply did not begin or end at a sentence
boundary:

> *"era un castillo un poco pijo, pero sí, trabajaba de camarera en un castillo que celebraba bodas.
> Y en el castillo nos daban un traje que picaba mucho, picaba mucho y era de color gris con"*

Chosen for *picar* = "to itch", and the clause in the middle is a perfect example of it. But the
passage starts mid-thought and trails off mid-phrase, and the learner is shown the whole of it.

The same shape appeared for *quedar* = "to remain":

> *"enfermedades posibles, literal, la puertita, estaba así el flaco y me dice, «Usted, este tipo se
> tiene que quedar acá 48 horas mínimo en reposo.»"*

v1 did tell the model to reject these — but in one bullet, fourth in a list, competing with
"the word is doing real work in it". The diagnosis is that **the model was judging the best clause
inside the passage rather than the passage it was choosing.**

The change was to make that check first, name it as the most common failure, give it a concrete
three-part test (does it begin where a sentence begins, does it end where one ends, is it one
thing), quote both real failures back, and say plainly: *you are choosing the passage, not editing
it.* Rounds 2 and 3 produced **no ragged passages at all**, and *picar* = "to itch" — whose only
good use in this corpus is inside that ragged castle passage — is now correctly refused.

## What did not need changing

- **Sense discrimination is good.** *pillar* was told apart as "to catch" and "to grasp" in every
  run; *quedar* as "to remain" and "to arrange to meet"; *bronca* as "anger" and "a row". This is
  the judgement the whole design spends a frontier call on, and it is the part that works.
- **The translations are usable as they stand**, and `matchedTranslationForm` held verbatim in
  every case — *itchy*, *bit*, *arrange to meet*, *worked hard*, *grasping*.
- **Refusing is being used.** Three to five senses per run got nothing, without prompting.

## Variance, and why it is the right kind

Rounds 2 and 3 share a prompt and disagree on three of eight words. Every disagreement is at the
borderline — *currar*'s single candidate taken in one run and refused in the other, *bronca*'s
second sense filled in one and not the other — and no run produced something plainly bad. Variance
concentrated at the margin is what a well-calibrated threshold looks like; variance in the middle
would not be.

The fill rate drifting 11 → 10 → 9 is therefore **not** evidence that the prompt got stricter twice.
Round 3 is the same prompt as round 2.

## What this does not tell you

- Whether precision is *high enough*. Eight words read by one person is an impression.
- Anything about recall. Nobody read the declined candidates to ask whether a good one was passed
  over, which is half of what the experiment document asks for.
- Anything about the knobs. Candidate count, what a candidate carries, what a sense carries and how
  refusal is framed were all held at their shipped values; the experiment document names them in
  the order to vary them.
- Anything about a second language. The corpus indexes only Spanish.

## What to do next

Carry out the real loop in `docs/plans/clip-selection-experiment.md` — 25–40 saved lexemes, labels
on both selections *and* refusals, and one knob at a time starting with candidate count. This round
supplies the starting point and one fix, not a baseline to stop at.
