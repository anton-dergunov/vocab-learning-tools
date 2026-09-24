# Story pictures drawn with the earlier pictures as reference

## Question

A story's four pictures are drawn by four independent, text-only calls. The only thing that keeps
the characters the same is prose: the brief writer (`prompts/acervo_story_brief.md`) decides a
`cast` once and copies it into every brief. That works fairly well, and it still drifts. A face
changes, a jacket changes colour, a street becomes another street.

The Gemini image models accept reference images as input, and they cost about 1% of a picture each.
**Does giving each later part the earlier pictures make a story read as one story? And does it do
that without making the pictures repeat each other?** The second half is the real risk. The point
is to keep the characters and the atmosphere, not to draw the same frame four times.

## Method

Part 1 is never redrawn: it is the stored picture in every set. Parts 2…n are redrawn with:
- the same stored brief (`imagePrompt`);
- the story's style text;
- `illustrate.FRAME`, through `illustrate.compose`;
- the same model the stories were drawn with, `vertex_ai/gemini-3.1-flash-lite-image`;
- one or two reference images, and [`reference_preamble.md`](reference_preamble.md) in front of
  the brief.

The preamble says what the references are for: identity (face, age, build, hair), art style and
the feel of the place. It also says what they are not for. Composition, pose, expression and the
part of the setting must all be new, and clothing follows the brief. It closes with the rule that a
picture that could be mistaken for an earlier one is wrong.

| Set | References for part k | Stories |
| --- | --- | --- |
| `original` | none: the stored pictures | all |
| `first+prev` | the stored part 1 and the new part k−1 (part 2: part 1 once) | all |
| `prev` | the new part k−1 only (strict chaining) | one (newest by default) |
| `first` | the stored part 1 only | the same one |

`review.py` shows every story's sets blind, each as a 2×2 grid under a shuffled letter:
- oldest story first, with its date;
- the five newest stories marked "recent", because only they were drawn under the current brief
  prompt;
- labels for each story: the set that reads best as one story (or no difference), a
  "characters change" and a "too alike" flag on each set, and an optional note.

`run.py report` unblinds the labels.

**Confounds, stated rather than controlled:**
- Each set is one sample, and Vertex ignores `seed`. A redraw with no reference would also
  differ, so a small preference is noise.
- Older stories were drawn under earlier brief prompts and possibly an earlier style text. The
  conditioned sets use the stored brief and today's style text.
- The chat path is not `call.image`. The fixed resolution travels in `imageConfig`, and `probe`
  checks that it arrives.

**Cost.** A picture is $0.0336 and a reference about $0.00028 (from LiteLLM's price table, not yet
checked against billing). For 18 four-part stories:
- the main set is 54 pictures, about $1.84;
- the two variants add about $0.20.

`draws.jsonl` records LiteLLM's own cost figure for every call.

## Running it

All on the laptop. The output goes to `out/`, which is ignored, because it holds the owner's stories.

```bash
# The Google login Vertex bills. If it has expired: gcloud auth application-default login
export ACERVO_VERTEX_PROJECT=<the Vertex project>
.venv/bin/python -m acervo.admin providers

# One picture from a synthetic reference (~$0.03): checks the call path before the hour is spent.
.venv/bin/python experiments/story-picture-reference/run.py probe

# The stories and their stored pictures. Asks for the password; skips a story still being drawn.
.venv/bin/python experiments/story-picture-reference/run.py fetch \
  --server-url https://acervo.example.com --email learner@account.example.com

# About an hour. One picture at a time, resting on a rate limit; stop and rerun freely.
.venv/bin/python experiments/story-picture-reference/run.py draw

# The review page, reachable from the tablet over Tailscale. Labels are saved on every tap.
.venv/bin/python experiments/story-picture-reference/review.py --host "$(tailscale ip -4)" --port 8765

.venv/bin/python experiments/story-picture-reference/run.py report
```

`draw` takes `--variants-story ID` to choose which story gets the two extra sets, `--no-variants`
to skip them, and `--limit N` to stop after N pictures. On a Mac without the CLI on the path,
`tailscale` is `/Applications/Tailscale.app/Contents/MacOS/Tailscale`.

## Results

Not yet run.
