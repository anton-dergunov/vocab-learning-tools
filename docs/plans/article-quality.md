# Article composition quality

**Status:** An open register, not a plan. One section per defect, with evidence and what would
settle it. It is populated as things are found, and nothing here blocks anything.

`prompts/acervo_compose.md` writes every article Acervo holds, and the parts of it a learner trusts
most — a transcription, a register, a tone mark — are the parts they are least able to check. This
file is where those defects are collected so they are argued once rather than rediscovered.

## Why this is separate from the compose experiment

[`experiments/compose-lesson-line/`](../../experiments/compose-lesson-line/README.md) compared two
versions of the prompt on the same words. That design answers *did this change anything* and is
structurally blind to *is it right*: a defect both arms share cancels exactly, and a pairwise "which
is better" screen cannot see it at all. Both arms of that run wrote `/ˈaska/` for `el asco`, and
every instrument in it — ten metrics, a Pro-model judge, twenty-five blind human screens — reported
no difference, correctly.

So quality needs its own experiment, **against ground truth rather than against another article**:
a word list with known transcriptions, known registers and known tones, scored per field. That is
not built. The issues below are what it would aim at.

## Open issues

### 1 · A wrong IPA vowel, reproducibly, from the model that writes the articles

`el asco` → `/ˈaska/`. Spanish has **no vowel reduction**: an unstressed final `o` is `/o/` and never
`[a]`. The answer is `/ˈasko/`.

**Evidence** (compose-lesson-line, 18 Sep 2026, 20 words × 3 repeats × 2 arms):

| pair | what it wrote for `el asco` |
| --- | --- |
| `gemini-free` / `gemini-3.5-flash-lite` | `/ˈaska/` — **6 of 6 calls**, both arms, all three repeats |
| `cloudflare` / `llama-3.3-70b` | `/ˈasko/` — correct, every call |
| `vertex` / `gemini-3.8-flash` | `/ˈasko/` and `/ˈas.ko/` — correct, every call |

Two things make this worth a section rather than a shrug. It is **deterministic** on that pair, so it
is a systematic error and not sampling noise — and that pair is the one currently first in the text
chain, so it is the model writing real articles. And it was the **only** wrong Spanish final vowel in
315 calls, so this is not a general weakness in transcription; it is this word on this model, which
is the harder kind of bug to find by sampling.

**What would settle it:** a ground-truth list of thirty Spanish words with published IPA, scored per
pair. **Candidate fixes, in increasing order of cost:** one sentence in the prompt stating that
Spanish never reduces unstressed vowels (cheap, and testable on the same list); demoting `ipa` to
null for languages whose orthography already determines it; or validating the field against a
dictionary at save time, which is the only option that actually closes it.

### 2 · The `emotion: null` boundary is conservative, and may be too conservative for a loop

`emotion` on a lexeme exists so a rhythmic loop can be read with feeling
([`lexibeat-integration.md`](lexibeat-integration.md) §2.8). The prompt tells the model that most
words carry no feeling of their own and that a forced one is worse than none — deliberately the
opposite default from an example's `emotion`, where most sentences do carry one.

The rule works, and the pattern it produces is coherent. Nulls cluster where you would want them:

| word | nulls | reads as |
| --- | --- | --- |
| `el miércoles`, `magazine` | 8 of 8 | right — a weekday and a periodical |
| `la casa` | 7 of 8 | probably right |
| `el atasco`, `hoax`, `ponerse malo` | 2–4 | arguable |
| `picar`, `currar`, `desmayarse` | 1–3 | **probably wrong for a loop** |

Words with a real charge — `asco`, `dar bronca`, `тоска`, `加油`, `turmoil` — were never null.

**The open question is not whether the rule fires correctly but where the line should sit.** A loop
repeats one word six times over a beat, and *irritated, scratching at it* would serve `picar` better
than a flat reading. But a direction invented for `la casa` would be worse than none, which is what
the current wording protects. This is a tuning pass on one paragraph, measurable on a fixed list by
asking whether each word's direction is one a speaker would recognise — and it should happen before
the field is used to record clips in bulk, because a clip carries the words that were spoken and
re-recording is the only fix.

### 3 · A pinyin tone error, not reproducibly

`麻烦` is `máfan` — second tone then neutral. `gemini-free` wrote `máfán` once in six calls, two
second tones. Cloudflare and Vertex were correct every time, and so was gemini in its other five.

Low frequency, but `reading` is **required** for Chinese and is the field a learner leans on hardest,
since the characters give them nothing. It belongs in the same ground-truth list as issue 1 — tones
are exactly the kind of thing a sampled comparison misses and a checked list catches.

## What is already good, so it is not re-litigated

From the same 315 calls, the prompt's structural rules held on every pair:

- `dialect` — `che` → `es-AR` on all three pairs; nothing else was marked regional.
- `register` — `currar` → colloquial or slang everywhere, never neutral.
- `pos` — `ничего` → expression on all three.
- `reading` present for every Chinese entry; its absence is a hard refusal and never fired.
- Gloss-language completeness **100% in both arms on every pair**: every requested language present.
- `shortGloss` never degenerated, and `primaryGloss` was a single term in all 158 usable replies.

The one structural rule that did fail is the gloss **language**, and only on `llama-3.3-70b`, which
answered in English 28% of the time for vocabularies that gloss into Russian first. That is recorded
in the experiment rather than here, because it is a fact about one model rather than about the prompt.

## How to measure any of this

Not with a pairwise comparison — see the top of this file, and
[`compose-lesson-line`](../../experiments/compose-lesson-line/README.md)'s verdict, where a 50%
false-positive rate on same-arm controls showed that reading two articles side by side cannot resolve
anything at this scale.

The shape that would work: a tracked list of words with **known** answers per field, one call per
word per pair, scored field by field against the list, reported per pair. Field-level accuracy against
truth, rather than preference between two articles. The apparatus in `compose-lesson-line` is most of
it — `dataset.py`, the direct per-pair calls, the manifest and the cost gate all transfer; what
changes is that `score.py` compares against expectations instead of against the other arm.
