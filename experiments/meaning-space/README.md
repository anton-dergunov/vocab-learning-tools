# Meaning space: a real vocabulary, laid out by meaning

Serves the meaning map ([`docs/server.md`](../../docs/server.md), "The meaning map"): it built the
prototype's data, and is where encoders and labels are compared before the server adopts one.

## The question

The design says: embed each sense, lay one language out in two dimensions, find regions on the
layout, and name them. Before any of it goes into the server, what does that look like on the
owner's own words? Specifically:

- does the layout make a map worth looking at — islands and regions, rather than a uniform cloud;
- do the regions read as the owner's topics, and which way of naming them reads best;
- how far does the map move when a few words are added, with a fixed seed;
- does the small encoder the design chose do as well as the obvious alternative?

## Method

`build.py` reads an export bundle (the 19 Sep 2026 one: 1,718 words), embeds every sense with the
design's template — `{headword} ({pos}) — {definition} — {gloss terms}` — lays each language out
with UMAP (cosine, seed 42), cuts one Ward tree over the layout at 8 regions and 30
neighbourhoods, labels each two ways without a model, traces density contours, and writes the
prototype's fixture. `label_model.py` then names every region once with a model (the free Gemini
text row, one JSON-mode call per language, all 38 groups in it) so the prototype can show all three
label sources side by side.

Two measurements need no labelling:

- **Topic agreement @10**: how often a sense's ten nearest senses (of other words) share one of
  its word's topics, against ten drawn at random. The owner's topics are free labels.
- **Stability**: lay the language out again with about 2% of its words removed, same seed, and
  measure how far each remaining point moved, on a map 1,000 units across — raw, and after a
  Procrustes alignment (rotation, reflection, scale and shift onto the previous layout).

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python build.py --bundle path/to/acervo-all.zip --pictures --sample \
  --compare sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# Model-written names, in the application's environment, then build again to merge them.
set -a; . ../../.env; set +a
../../.venv/bin/python label_model.py
.venv/bin/python build.py --bundle path/to/acervo-all.zip --pictures --sample
```

The full map goes to `design/ui-prototype/map-data.local.js` and the pictures to
`design/ui-prototype/map-local/`, both git-ignored; `--sample` also writes the committed
`map-data.js`. Model names are keyed by region id, so each file carries a fingerprint of which
senses each region holds, and a build against a different layout refuses to merge them rather than
naming the wrong regions.

## Results

### The data

1,443 Spanish senses (922 words), 857 English (568), one Chinese. **The export carried 227 English
words twice** — `burgeon.yaml` and `burgeon-2.yaml`, with identical senses — so the build drops a
word whose senses say exactly what an earlier one's do. Those look like duplicates in the account
itself, and are worth cleaning up there.

### Encoders

| | Spanish | English |
|---|---|---|
| `intfloat/multilingual-e5-small` | 0.430 | 0.473 |
| `paraphrase-multilingual-MiniLM-L12-v2` | 0.443 | 0.490 |
| random neighbours | 0.182 | 0.244 |

Both are more than twice chance, and they are within two points of each other. This metric does
not separate them; the design's choice stands until the discovery experiment's held-out recall
gives a sharper one. Embedding every Spanish sense took 5.7 s on an Apple-silicon laptop.

### The layout

`min_dist` decides whether there is a map at all. At 0.35 the senses spread into one even disc and
the contours are noise; at **0.1** (with 12 neighbours) related senses clump, and with the coast
drawn at 16% of peak density the vocabulary reads as land with inlets and islands — strikingly so in
English. The cost is stability:

| median shift / 1,000 | `min_dist` 0.35 | `min_dist` 0.1 |
|---|---|---|
| Spanish, raw | 50 | 163 |
| Spanish, aligned | 34 | 101 (p90 254) |
| English, raw | 64 | 477 |
| English, aligned | 39 | 48 (p90 106) |

Two findings. **A fixed seed does not keep a map in place**: English at 0.1 came back mirrored (a
raw median of 477, half the map), which UMAP is free to do. A Procrustes alignment onto the previous
layout removes that for the cost of one SVD, and should go into the server with the layout.
**Clumping costs stability**, most in Spanish, whose regions are less separated. The prototype uses
0.1 because the map is worth looking at; the design's "not pinned" stance holds for now, and
warm-starting from the previous coordinates is the lever if the movement bothers the owner.

### Labels

The model's names read as places — *dinero y trabajo*, *ropa y utensilios*, *pagos y deudas*,
*aggression and hostility*, *vocalizations and shuddering*. The nearest headwords are recognisable
but read as a list, and the c-TF-IDF terms are passable for neighbourhoods and poor for regions,
where definition boilerplate (*dicho*, *indica*, *showing*) survives a stopword list. The prototype
therefore defaults to the model's names, and the other two are one switch away. If they are
adopted, the design's reason for a deterministic first — no model call on the way to a map — still
holds: the names can be asked for once per layout, off the path that draws it.

## Files

| File | What it is |
|---|---|
| `build.py` | Bundle → embeddings (cached by text) → layout → regions → labels → contours → fixture |
| `label_model.py` | One call per language naming every region; runs in the application's `.venv` |
| `requirements.txt` | This experiment's own environment: sentence-transformers, umap-learn, scikit-learn, contourpy, Playwright |
| `out/` | Ignored: the embedding cache, region summaries, model names, `report.json` |
