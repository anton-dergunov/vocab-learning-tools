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

## Run 2: the shipped code, and the photographic question

After run 1 the design went into the application:
- the labeller as a separate call, `prompts/acervo_story_continuity.md`, with option 2 dropped;
- at most **two** references;
- a picture-first prompt, `prompts/acervo_story_reference.md`;
- `photographic: true` on four styles in the style table: cinematic-photoreal, golden-hour,
  film-noir and neon-cyberpunk;
- a three-way setting that leaves those styles out by default.

Run 2 checks that decision on 12 fresh stories the owner has not seen, 7 of them in the cinematic
style. `run.py` now imports the application's own labeller, reference choice, wording and
`call.image(references=…)` rather than keeping copies, so it measures what ships. It draws every
style with references, photographic ones included, so the default can be checked rather than
assumed.

The positional sets and the v2 sets of run 1 are gone from the apparatus. The v2 prompt is kept in
`prompts/` as the record of what was tried.

```bash
OUT=experiments/story-picture-reference/out-2
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT fetch --newest 12 \
  --server-url https://acervo.example.com --email learner@account.example.com
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT prepare   # free
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT draw
.venv/bin/python experiments/story-picture-reference/review.py --out $OUT --host "$(tailscale ip -4)" --port 8765
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT report
```

`report` now also splits the result by artwork vs photographic, and style by style.

## Run 2 results

The owner rated run 2 blind: references won **9 of 12** and tied 3, and never lost:

| | continuity | no difference |
| --- | --- | --- |
| Photographic styles (10) | **7** | 3 |
| … of which cinematic-photoreal (8) | **5** | 3 |
| Drawn and painted (2) | **2** | 0 |

With the picture-first prompt, the photoreal loss of run 1 did not come back, so references became
the default in every style. The owner also saw a new failure. Each part anchored a returning person
to the *latest* picture of them, so a slightly different profile in part 2 became the truth for
part 3 and was pushed further in part 4: the face drifted part by part.

## Run 3: which picture a returning character is drawn from

The application now draws a returning character from the **first** picture that showed them, and a
returning place from its **last** (`continuity.references(characters="first")`). Run 3 checks that
on five fresh cinematic stories. It has two sets and no `original` in the comparison:
- `continuity`: the character's latest picture, as in run 2;
- `continuity-first`: the character's first picture.

A part whose references are the same in both sets, backed by byte-identical pictures, is drawn once
and copied, so the sets differ only where the anchor does.

```bash
OUT=experiments/story-picture-reference/out-3
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT fetch --newest 5 \
  --server-url https://acervo.example.com --email learner@account.example.com
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT prepare
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT draw
.venv/bin/python experiments/story-picture-reference/review.py --out $OUT --sets continuity,continuity-first \
  --host "$(tailscale ip -4)" --port 8765
.venv/bin/python experiments/story-picture-reference/run.py --out $OUT report
```

## Running it (run 1)

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

**Run 1, 24 Sep 2026: 19 stories, 52 pictures, $1.77.** Nearly every picture hit Vertex's 429 at
least once and drew after a rest. The median draw time was 5 s.

Two stories had nothing recurring, so every part kept its stored picture, and they were not shown.
One is the real *La invención del Post-it*: Spencer in the lab, Art Fry in the church, an office
worker in an office, a desk. That is the case the positional first version would have got wrong.

The owner rated the other 17 blind:

| | continuity | original | no difference |
| --- | --- | --- | --- |
| All 17 | **10** | 4 | 3 |
| Drawn, painted or made styles (10) | **8** | 0 | 2 |
| Photographic styles: cinematic-photoreal, film-noir, golden-hour (7) | 2 | **4** | 1 |
| … of which cinematic-photoreal (4) | 0 | **4** | 0 |

Flags were rare: "too alike" once on continuity, and "characters change" once on original.

**Reading.** References work: the same people and places come back. Outside photographic styles
they won 8 to 0 (a sign test gives p ≈ 0.008). In the photoreal style they lost 4 to 0. The owner's
account is that a conditioned picture serves two masters — draw a good picture, and match the
reference — and in a photograph the second visibly costs the first. In *La fuga de Harry Houdini*
the conditioned guards are recognisably the same men, but they turn into grimacing, near-identical
caricatures, where the unconditioned ones are plainer and more natural. A painted style tolerates
the compromise. A photograph shows it.

**The v2 story** (*La leyenda de la laguna*, folk-naive) ranked `continuity` best of four, above
`original`, `v2` and `v2+continuity`. That says less about the ids than it seems:
- The v2 briefs were written by `gemini-3.1-flash-lite`, the free tier's fallback.
- They stopped restating the hero's description. Part 2 says only "a young man in simple linen
  robes". Parts 3 and 4 give his name and nothing else.
- So `v2` drew three different young men, and references in `v2+continuity` repaired only part of
  it.

The labeller, reading the stored briefs, kept them intact. The risk this shows is real: asking the
brief writer for ids as well dilutes its most important rule.
