# Pictures · what is still to do

**Status:** open. The design as built is [`../features/sense-images.md`](../features/sense-images.md).

## 1 · Land the pictures drawn on the laptop

About 2,285 pictures sit in `output/images/` and `output/images-en/`, drawn by the first full laptop
run. Their `senseId`s name senses nobody holds any more — the vocabulary has since been exported and
re-imported, and import re-mints every id — and because `image_prompt_id` is derived from `senseId`,
every filename is wrong for the current database too. `verify` cannot see this, since a run directory
is internally consistent either way; `publish` does, and refuses the whole run.

`scripts/rekey_image_runs.py` is the matching step, a throwaway outside the pipeline. It keys on what
survives an export and re-import — language, headword, and the sense's order within the word — and uses
the definition as a **check** on that key rather than part of it, because a picture landing on the
wrong sense of the right word is the quiet failure worth spending a comparison on. It re-derives every
id, filename and `imageRef` (the reference from the bytes it copies), writes a new run directory and
never edits the one it read, and refuses a word it cannot match rather than guessing. `imageModelId`
keeps the model that actually drew each picture.

**Do it against the final database**: re-keying against anything a later rebuild replaces is work
thrown away. Then `publish`, and delete the script once the backlog is in.

## 2 · How pictures are presented

Deliberately plain today. Several things about the article are due to change at once, and picture
layout should be decided with them rather than ahead of them.

## 3 · Do abstract senses work as mnemonics?

The briefs read well and the pictures are beautiful; whether a glowing knot of woven threads recalls
*abundar en un tema* specifically, or merely recalls "convergence", is a judgement only use answers —
and a question for [`learning-modes.md`](learning-modes.md) once review state comes back from Anki.

## 4 · An automatic quality gate, if a less reliable model draws

Luminance and colour variance, entropy, edge density, dominant-colour share — sketched in the image
benchmark report. Gemini's 0-in-12 rejection rate does not justify it; a cheaper image model might.
