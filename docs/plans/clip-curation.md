# Plan · curating clips

**Status:** Planned, unstarted. Depends on nothing; wanted once there are enough clips to be annoyed
by the ones that are wrong.

`docs/spoken-clips.md` shipped the pipeline: a word is searched once, a model picks at most one
passage per sense, and the only control afterwards is a remove button. That is the right first shape
— most words get nothing, and most of what they get is fine. This plan is the two things reading the
first real output made obvious.

## 1 · The selection prompt should be the owner's

`selfContainedOnly` was the first setting that is really a matter of **taste** rather than of
correctness. It exists because two learners disagree about the same passage: one wants speech tidy
enough to follow cold, the other wants it exactly as messy as a real room, because walking in on a
conversation already under way is the thing being practised.

A growing list of booleans is the wrong shape for that. "Advanced and authentic" versus "clear and
simple" is one question, and every future answer to it would be another checkbox that interacts with
the others in ways nobody can predict from the labels.

> **Proposed: an owner-scoped selection prompt, with the shipped one as its starting text.**

What that has to settle:

- **The shipped prompt stays the default and stays tracked.** A custom one is an override, not a
  replacement for the file; an owner who has never opened the screen gets the repository's wording,
  and "reset to the default" is always available.
- **The contract is not negotiable.** Whatever the wording, the reply is still `{senses: [{senseId,
  segmentId, translation, matchedTranslationForm}]}`, ids still come from the offered set, and the
  passage is still quoted verbatim (§2.6). So the shape block and the id rule are appended by the
  server rather than typed by the owner — the same split `acervo_image_brief` already has between
  what the writer decides and what the frame enforces.
- **A custom prompt is not replicated.** It is owner-scoped server state like `clip_settings` and
  `model_selection`, for the same reason: the searching happens on the server.
- `selfContainedOnly` then becomes a section of the default text rather than a column, and
  `services/prompts.py`'s markers are how it survives the move.

Do not build this before there is a second taste knob asking for it. One is a setting; three are a
prompt.

## 2 · A dialog for the clips a word already has

Today a clip can be removed and nothing else. The picture pipeline learned the same lesson and has
`ImageDialog.tsx`: read what produced this, change it, ask again, or rule the sense out. Clips want
the same surface — *this one is wrong, show me the others you were offered*.

Shaped on that dialog, it would offer:

- the passage, its channel and its caption kind, as the article shows them;
- **the other candidates from the same search**, so replacing one costs no model call at all;
- search again, which does;
- remove, which it already has.

**What has to land first, and it is not optional.** Removal is currently an ordinary tombstone, and
a clip example's id is derived from `(senseId, clipRef)`. A re-search that chose the same segment
would write at the tombstone's id and bring the clip back — and nothing would fail. That is exactly
the failure `imagePrompt.suppressed` exists to prevent, and the same answer applies: **a suppression
field has to exist before anything re-searches.** `docs/spoken-clips.md` §2.4a says so in as
many words; this is the feature that makes it due.

Showing the other candidates also implies keeping them, which the pipeline currently does not: the
search result is used and dropped. Either the dialog re-searches to populate itself — cheap, since a
corpus search costs no model call — or the run keeps its candidate set somewhere. Re-searching is
almost certainly right: it is one HTTP call to a service on the same network, and storing a
candidate set means storing text the owner never chose.

## 3 · Not here

**Passage boundaries.** Half of what looks like a bad clip is a good passage cut badly, and the fix
is upstream: `spoken-usage-retrieval`'s own experiment on where a shown passage should start and end.
Nothing in this plan should compensate for that by trimming text — §2.6 is what stops the corpus's
own measurements from being invalidated, and it holds however tempting the trimming looks.

**Tuning the default prompt.** `docs/plans/clip-selection-experiment.md`, with
`docs/clip-selection-rounds.md` as its starting point.
