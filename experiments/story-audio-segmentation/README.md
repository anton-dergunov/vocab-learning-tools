# Story narration: can a model cut a part into passages without changing a word?

Serves the story-audio work (`prompts/acervo_story_narrate.md`, `src/acervo/stories/narrate.py`).

## The question

A story part is read aloud by a voice that takes a direction. Asking a voice to read a whole paragraph
in one mood is what a clear voice does; a directed one is worth having only if each passage gets its
own reading. So a text model is asked to return the part cut into passages, each with a direction,
and each passage becomes one call to the voice. The recording is those calls joined.

The risk is the one that makes every model-in-the-middle design fragile: the model is copying, and a
model that is copying with judgement sometimes "fixes" what it copies. If it does, the voice reads a
sentence the story does not contain. So: **how often do the returned passages, joined, equal the
part?** and, if it is not always, can the pipeline absorb the difference?

## Method

`run.py`. The five stories the owner generated (four Spanish, one English; four parts each) are read
from `stories_audio_followup.txt`. A run takes one part of each story, rotating through the parts, so
5 runs × 5 stories = 25 calls covers every part of every story about equally. The model is the free
Gemini text row of the catalogue (`gemini-free`, `gemini-3.5-flash-lite` when this ran), asked in JSON
mode with temperature 0.2, through `acervo.models.call.text` — the same call the pipeline makes.

Each reply is checked three ways: **strict** (the passages joined with one space equal the part
exactly), **loose** (equal once whitespace is normalised), and by what `narrate.tile` had to repair:
`dropped` is a returned passage that is not in the text, `filled` is a stretch of the text no passage
covered. `tile` is what the pipeline actually uses, and it guarantees the tiles join to the part
whatever the model did — so `dropped` and `filled` measure how much of the model's work was lost, not
whether the story survives.

## Results

Draft prompt (`results-v1.json`), 25 calls, run 20 Sep 2026:

| | |
|---|---|
| Calls / errors | 25 / 0 |
| Strict match | **25 / 25** |
| Loose match | 25 / 25 |
| Clean tile (nothing dropped, nothing filled) | 25 / 25 |
| Passages per part | 3 → 15 parts, 4 → 10 parts (about one per sentence) |
| Mean words per passage | 18.1 |
| Every passage carries a direction | 85 / 85 |
| Distinct directions | 84 of 85 |
| Latency, median | 1.1 s (a few calls took 5–17 s) |

No second iteration was needed, so the draft prompt shipped as written. Two smoke calls before it
(2 / 2 strict) are not counted.

What the directions look like: "Formal and historical, setting the scene with a steady pace." /
"Skeptical and dismissive, with a touch of irony at the end." / "Brighter and faster, introducing a
fresh contrast." They vary within a part, which is the point; some are written about the passage
("emphasizing the guards' certainty") more than to the voice, and an instruction-following voice copes
with either.

**What this does not show.** The sample has little dialogue (two parts of one story have quoted
speech) and no part longer than four sentences, and the free row is one model. A stronger row later in
an owner's chain will do at least as well; a weaker one may not, which is why the pipeline does not
trust the output: `tile` makes the failure an undirected stretch rather than a wrong sentence, and a
reply that is not even the right shape is passed to the next model in the chain.

## Voice limits, from the provider's documentation

Read on 20 Sep 2026 (`docs.cloud.google.com/text-to-speech/docs/gemini-tts`, `…/quotas`):

- A Gemini voice takes at most **4,000 bytes** of text and 4,000 bytes of prompt per request. Bytes,
  not characters, so accented and CJK text costs more. A story part is a few hundred characters and a
  passage is a sentence, far inside both.
- Output audio is capped at about 655 seconds, and the documentation warns that quality and
  consistency **drift on outputs longer than a few minutes**. That is an argument for short calls even
  where one long call would fit.
- Nothing in the documentation compares one paragraph against one sentence at a time. What decides it
  here is not quality but control: one call has one direction and returns no times, so it can neither
  vary its reading nor say where a sentence starts. One call per passage does both, and the
  recording's own lengths are the alignment — no forced aligner is needed.
- A Gemini voice performs each call afresh (`experiments/pronunciation-encoding/README.md`), so two
  passages of one part differ in delivery even with the same voice. That is why the pair *and the
  voice* are fixed for a whole story: it holds the timbre, not the performance.
