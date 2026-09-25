# The expressive order offers voices that cannot take a direction

**Status:** open. Found 20 Sep 2026 while adding story narration; a story-shaped guard is already in
`services/story_audio.py`, and the general fix below is not done.

## The problem

`audioExpressive` is *the voice that takes a direction*. Nothing holds it to that. A row that
declares `style: none` can sit anywhere in it, including first — and when it answers, the direction
is dropped and the clip is recorded as though no emotion had been asked for. Nothing fails, nothing
is logged as wrong, and the only trace is an `emotion` field that is empty on the stored row.

**It happened.** On the owner's deployment the stored order was

    audioExpressive   source: owner
      1. gemini-free  gemini/gemini-3.1-flash-tts-preview    style: none
      2. google-tts   gemini-3.1-flash-tts-preview           style: instruction
      3. google-tts   gemini-2.5-flash-tts                   style: instruction
      4. google-tts   wavenet                                style: none

saved from Settings ▸ Providers, which offers every audio pair for either order. Every expressive
clip recorded after that went to the free row and lost its direction. The thirteen clips that *do*
carry one were all made by `google-tts` before it; the `gemini-free` and `vertex` rows have never
produced a clip that carries a direction at all.

It surfaced through stories only because a story spends a model call per passage *to place the
directions*, so the waste was four calls a part for nothing — and the free row's daily allowance then
ran out mid-story. Example sentences and loops have been degrading quietly the whole time.

**Why those rows cannot carry one.** It is the route, not the model. `gemini-free` and `vertex` reach
Gemini TTS through LiteLLM, and `litellm/llms/vertex_ai/text_to_speech/transformation.py` has no
field for a prompt or an instruction — the direction is dropped before the request is built.
`google-tts` reaches the same models through `models/google_tts.py`, which puts it in `input.prompt`.
So `style: none` on those rows is an honest statement about the path, and the same model is
expressive through the other one.

## What should change

- **Retire the `gemini-free` audio capability from the catalogue.** It is a speech row that cannot do
  the one thing the expressive order exists for, on a free tier of about ten requests a day. Removing
  the capability removes the pair from both orders and from Settings ▸ Providers. (Its text
  capability stays: that is a different thing and it works.) `vertex`'s audio row is the same case and
  should be looked at with it.
- **The expressive order lists only pairs that declare `style: instruction`.** Settings ▸ Providers
  should not offer any other pair there, and the readout should say so. **The shipped default breaks this
  rule itself**: `defaultChains.audioExpressive` ends with `google-tts/wavenet`, which is `style: none`.
  That entry goes, and the fall-back-to-plain rule below takes its place.
- **Not enforced — backfilled.** A saved order is a preference and must not be refused or rewritten.
  When no expressive pair can be reached, the caller falls back to the **plain** order (`audioPlain`)
  and records without a direction, rather than failing. That is the one place a clear voice may read
  something the owner asked to be read expressively, and it should be logged as such.

## What is already done

`services/story_audio.py` filters the expressive order to `style: instruction` pairs for a story, and
falls back to reading the part whole and plainly when none answers. That is the same rule, applied in
one caller. When the general fix lands, that guard becomes redundant and should be deleted rather
than left as a second implementation of the same idea.

## Also worth deciding

Whether to give `gemini-free` a direct adapter to the AI Studio audio API, the way `google_tts.py` is
a direct adapter, so the free tier could carry a direction after all. That is new provider work and
the daily allowance would still be about ten requests, so it buys little for a story; it is written
down here so the option is not lost.
