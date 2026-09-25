# Learning modes · what to do with a word once it is held

**Status:** ideas, ranked, not specified. Loops and stories are the two built so far
([`../features/loops.md`](../features/loops.md), [`../features/stories.md`](../features/stories.md));
closing the Anki loop is its own plan ([`anki-loop.md`](anki-loop.md)).

> **Do not write a spaced-repetition scheduler.** Anki with FSRS beats anything worth building here,
> and every mode below should *report into* it rather than compete with it. The one thing worth
> building is the queue that decides *which mode* a due word gets today.

## Six ways to learn a word, ranked by what they return

1. **Production with model grading.** Recognition — "does *desmayarse* mean to faint?" — is far easier
   than production, and recognition is most of what a default card tests. A model grader judges
   *meaning*, accepts valid alternatives an exact match would reject, and flags "grammatical, but no
   native says this". It must emit an Anki-compatible rating and feed it back, or it is a toy
   disconnected from the scheduler.
2. **Narrow reading — short texts using due words.** Text-only, so cheap; it teaches collocation and
   register, exactly where isolated cards fail. Stories are the built half of this; they take the words
   on screen or the ones marked by hand, and choosing *due* words is what is missing.
3. **Audio-first review.** Due words in sentences for walking or commuting. Loops are the built half;
   again, what is missing is choosing due words.
4. **Clip review as a session.** "Ten clips of your due words" as a review mode in its own right — the
   only mode that shows real register, real speed and real regional variation.
5. **Comics and illustrated stories, gated on difficulty.** Bizarre imagery is well supported as a
   mnemonic for *stubborn* items, and it is the most expensive per word. Gate it on FSRS difficulty
   and it is excellent; run it across the whole deck and it is a bill.
6. **Collocations over synonym clusters.** When exploring outward from a word, prefer the words that
   appear *with* it over the words that mean the same: teaching close synonyms together risks
   interference. `desmayarse` + `mareo` + `perder el conocimiento` in one scene is good; five
   near-identical words for "sad" in one session is not.

## Reveal order, per language

Whether the target-language definition or the native gloss comes first is a per-language choice, not a
global one: definition first forces processing in the language being learned while keeping the gloss
one tap away, and on a card it splits front from back; for a language with no shared background — Chinese
for this owner — withholding the gloss buys nothing. It would be a field on the `vocabularies` record.

## "Which words here are new to me?"

Asking a model for "the interesting words" in an article fails: it estimates the *average* learner's
gaps, and the missing information is not in the article. Once the vocabulary holds a couple of
thousand words, plus what was suppressed, plus FSRS difficulty, the question becomes a set difference
against the owner's own store rather than a guess. It is the payoff that makes a curated store worth
keeping, and it pairs with the discovery work in
[`../research/similar-projects.md`](../research/similar-projects.md), "The vocabulary is seen one way at
a time".
