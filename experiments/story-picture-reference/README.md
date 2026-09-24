# Story pictures drawn with earlier pictures of the same people and places

## Question

A story's four pictures are drawn by four independent, text-only calls. The only thing that keeps a
person looking the same is prose: the brief writer (`prompts/acervo_story_brief.md`) describes the
cast once and copies that description into every brief. That already works fairly well. The pictures
share a style and mostly share a cast, but faces, clothes and rooms drift.

The Gemini image models accept reference images, and a reference costs about 1% of a picture. **Can
references move a story's pictures slightly closer together** — the same people recognisable, a
place that recurs recognisably the same place — **without reaching the other extreme**, where every
picture repeats the last?

A first version of this spike gave every part the first and the previous picture. The owner's story
*La invención del Post-it* shows why that is wrong. Part 1 is Spencer Silver in a laboratory; part 2
is years later and a *different* man, Art Fry, in a church. A positional reference would hand Art Fry
Spencer's face and pull the lab into the church. The references must follow **who and where**, not
position.

## Method

**Who and where.** A text model labels every picture with ids:
- the characters visible in it (`spencer_silver`, `art_fry`);
- the one scene it is set in (`laboratory`, `church`);
- a short `change`: what differs since they were last drawn, such as "years later, Spencer is
  greyer", or "the lab is covered in yellow notes".

The rule the prompts stress is **one id per individual**: a second scientist is a new id, not the
first one again.

**Which pictures a part is given** (`plan_references` in `run.py`):
- for each character in part k who appeared before, the last earlier picture showing them;
- for its scene, if it appeared before, the last earlier picture set there;
- each picture is sent once, at most 3, the most recent kept.

A part with nothing recurring gets **no references and is not redrawn**: the set keeps its base
picture. So Post-it part 2 is the stored picture in both sets.

**How each reference is explained.** The prompt names every reference and gives it a job:
- who in it to keep ("the same face, build and features");
- whether its setting is this moment's (keep layout, materials and light, from a new viewpoint) or
  not (do not reuse it);
- who else is in it who must not be drawn.

What changed since is stated, and it beats the reference where they disagree. Then comes the rule
against copying — a new composition, camera angle, pose and expression, and never a near-copy of a
reference. Clothing follows the brief. The fixed text is
[`reference_preamble.md`](reference_preamble.md); the lines for each reference are built in `run.py`.

**The two prompts, for review:**
- [`prompts/continuity.md`](prompts/continuity.md) labels a story's **stored** briefs without
  changing them. It is used for the main comparison, so references are the only thing that differs.
- [`prompts/story_brief_v2.md`](prompts/story_brief_v2.md) is the production candidate: the current
  brief prompt, with `cast`/`world` replaced by the same ids, which it writes alongside the briefs.
  Against the current prompt: `git diff --no-index prompts/acervo_story_brief.md
  experiments/story-picture-reference/prompts/story_brief_v2.md`.

`prepare` writes every prompt it would send, filled in with the story, to
`out/prompts/<story id>/`:
- `labels-request.md` and `brief-v2-request.md` are the text calls;
- `<set>-part-N.md` is each picture's full prompt, reference lines included.

**Sets:**

| Set | Briefs | Ids from | A part with no references keeps | Stories |
| --- | --- | --- | --- | --- |
| `original` | stored | — | — (the stored pictures) | all |
| `continuity` | stored | `continuity.md` | the `original` picture | all |
| `v2` | v2 | — | — (every part drawn, text-only) | one |
| `v2+continuity` | v2 | the v2 reply | the `v2` picture | the same one |

**Models:**
- Pictures: Vertex `gemini-3.1-flash-lite-image`, the model the stored stories were drawn with.
- Labels and the v2 briefs: the free Gemini tier, the catalogue row `gemini-free`, with
  `GEMINI_API_KEY` read from `.env`.

**Review.** `review.py` shows each story's sets blind, as 2×2 grids under shuffled letters:
- oldest story first, with its date; the five newest are marked "recent", having been briefed under
  the current prompt;
- a set identical to another is hidden, so a story where nothing recurs is not shown at all;
- the labels: the set that reads best as one story (or no difference), three flags per set
  ("characters change", "wrong person reused", "too alike"), and a note.

`run.py report` unblinds them.

**Confounds, stated rather than controlled:**
- Each redrawn picture is one sample, and Vertex ignores `seed`, so a small preference is noise.
- Older stories were briefed under earlier prompts.
- The v2 comparison is one story.

## Prompt development

On a made-up four-part Post-it story on the free tier:
- 1: Spencer in the lab;
- 2: Art Fry in the church;
- 3: both men in the lab;
- 4: Spencer, years later, in the lab now covered in notes.

What the labeller did:
- The labeller split the two men and kept one lab from the first run.
- The plan came out as intended:
  - 1 and 2 have no references;
  - 3 takes part 1 for Spencer and the lab, and part 2 for Art Fry;
  - 4 takes part 3, and says Art Fry must not be drawn.

What the v2 brief prompt did:
- It at first named the heavily changed lab of part 4 as a **new** scene in two runs of three
  (`laboratory_later`, `old_laboratory`), which would throw away the lab reference.
- One reply also used an id it never declared.
- It was rejected by the parser and fell through to the next model.

The fix:
- an explicit rule ("before you give a part a new scene id, check whether an earlier part is
  already set there");
- the example extended with a place that recurs with a change.

After the fix, three runs of three kept one lab, like the labeller, whose example already had one.

## Running it

All on the laptop. The output goes to `out/`, which is ignored: it holds the owner's stories.

```bash
export ACERVO_VERTEX_PROJECT=<the Vertex project>   # GEMINI_API_KEY comes from .env
.venv/bin/python -m acervo.admin providers           # which Google account Vertex bills

.venv/bin/python experiments/story-picture-reference/run.py probe     # one picture, ~$0.03
.venv/bin/python experiments/story-picture-reference/run.py fetch \
  --server-url https://acervo.example.com --email learner@account.example.com
.venv/bin/python experiments/story-picture-reference/run.py prepare   # free; prints the plan
.venv/bin/python experiments/story-picture-reference/run.py draw      # safe to stop and rerun
.venv/bin/python experiments/story-picture-reference/review.py --host "$(tailscale ip -4)" --port 8765
.venv/bin/python experiments/story-picture-reference/run.py report
```

`prepare` has two options:
- `--v2-story ID` picks the story for the v2 sets (the default is the newest; `fetch` prints ids);
- `--force` asks the text model again.

`draw --limit N` stops after N pictures. On a Mac without the CLI on the path, `tailscale` is
`/Applications/Tailscale.app/Contents/MacOS/Tailscale`.

**Cost.** A picture is $0.0336 and a reference about $0.00028 (from LiteLLM's price table, not yet
checked against billing):
- `continuity` redraws only the parts that have something recurring: at most 54 pictures for 18
  four-part stories, and fewer in practice;
- the v2 story adds about 6.

`prepare` prints the exact count, and `draws.jsonl` records LiteLLM's cost for every call.

## Results

Not yet run.
