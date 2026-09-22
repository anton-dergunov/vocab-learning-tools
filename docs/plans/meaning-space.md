# Meaning space · a map of the vocabulary

**Status:** specified; the first version is being built. Ghosts, the map's discovery half, are a
later task. It is the first of the [vocabulary views](vocabulary-views.md) to be worked out.

## Outcome

The learner opens a map of one language's vocabulary. Senses that mean related things sit together.
Zoomed out, the map shows labelled regions: the learner's interests, as their words reveal them.
Zoomed in, it shows the words, and then what each one means. Tapping a word gives a short peek, and
from the peek its article.

It is meant to be two things on one surface: a way to **explore** what is held, and a way to
**discover** what to add next. This document specifies the first. The second is the subject of
the sibling research repository `interest-aligned-vocabulary-recommendation` (its
`docs/discovery-v0.md`). That repository will compute the proposed words, and the map will draw
them. See [Ghosts](#ghosts-later).

## The first version

The aim is something basic that works on the real vocabulary, looks good from the start, and can
be reacted to. It is built in few, large steps (see [Steps](#steps)).

**In:**
- one map per vocabulary language
- one point per sense
- regions with labels at two levels
- pinch, pan and zoom
- tap to peek, and then the article

**Out:**
- ghosts
- the other layers: recall strength, recency, exposure
- positions pinned from one layout to the next
- a map spanning several languages
- model-written labels, unless the deterministic ones read poorly
- a standalone macOS application

The real vocabulary it is sized against has 1,443 Spanish senses (922 words), 1,194 English senses
(795 words) and one Chinese word. About 45% of words have more than one sense.

## Decisions

### One map per language

Every language gets its own map. It follows the language switcher, as Loops and Stories do.

The plan originally called for one multilingual space. That was dropped because a learner's
languages serve different purposes: one for travel, one for work, one for everyday life. The words
held in each are a different set of interests. Pooled into one space, they would make regions that
describe no single language's vocabulary.

### One point per sense, drawn briefly

Polysemy is exactly what collapses in a word-level map. The schema already separates senses, so a
word with two meanings appears in two places.

A sense is described by a paragraph, so the point cannot show it. What the point shows depends on
the zoom level:

| Zoom | Shown |
|---|---|
| Far | a dot |
| Middle | the headword and the sense's `emoji` |
| Close | adds the sense's first gloss term underneath |
| Peek | the definition, the gloss, the `domain` and the picture if the device holds it |

The two senses of *abyss* read as *abyss 🕳️* and *abyss 📉* long before the definitions are
needed.

Selecting a point draws faint links to the same word's other senses. This is the one thing a map
of senses can show that a list cannot: where else the word lives.

### What is embedded

For each sense, the encoder reads this text:

```
{headword} ({pos}) — {definition} — {gloss terms}
```

It is not the bare surface form, whose embedding is dominated by spelling and frequency. It is the
same template as `discovery-v0.md`, so Acervo and the discovery experiment compute the same vectors
and the experiment can take them from Acervo instead of recomputing them.

### The encoder

The encoder is `intfloat/multilingual-e5-small`: about 118 M parameters, 384 dimensions, MIT
licensed. It runs on CPU, with its weights baked into the server image at a pinned revision.

It still has to be multilingual, even with one map per language, because every embedded text mixes
two languages. A Spanish sense has a Spanish definition and English glosses; an English sense has
an English definition and Russian glosses.

It is small enough for the NAS: about half a gigabyte of memory out of twenty. The model id is part
of the cache key, so trying a stronger one later (bge-m3, EmbeddingGemma) means changing a setting
and recomputing. That comparison waits for a measurement; the discovery experiment's held-out
recall gives one.

### Computed on the server

Embeddings are computed on the server, not on the device. A phone is slow at it and pays in
latency and battery. The server is idle most of the time and every device reads the same answer.

A standalone macOS application, if one is ever built, would ship the server and start it with the
application, so this answer holds there too.

### Where embeddings live

Four options were considered:

| Option | Why not, or why |
|---|---|
| A replicated collection | Megabytes of floats that no device needs, a `LOCAL_SCHEMA_VERSION` bump, and a model change rewriting every row's revision. |
| Columns on `senses` | Mixes a derived value into an authored record, and changes a replicated shape. |
| A server-only table | Works, but it is a schema change, so it needs a throwaway converter, and it is lost on every `--reset-database`. |
| **A content-addressed cache beside the database** | **Chosen.** |

The chosen cache works the way the loop take store (`pronunciation/takes.py`) does. It is keyed by
`(model, digest of the embedded text)`. There is no table, no schema and no converter. It survives
rebuilds and re-imports because it is keyed on text rather than on record ids, which an import
re-mints.

**Invalidation is the digest.** Adding a sense, removing one, or editing one in any way that
changes what it says produces a new key, and only that sense is embedded again. An edit that
changes nothing embedded, such as a new picture or a new example, costs nothing. This is the rule
"any change to a word recomputes it", applied exactly.

### The map artifact

The server derives one artifact per owner and language. It contains:

- every sense id, with its `x`, `y`
- the sense's region at each zoom level
- each region's label and position
- each sense's few nearest neighbours, which the later
  [near in your vocabulary](vocabulary-views.md#meaning-space) view needs as well

No vector ever reaches the device. The artifact carries no text either: the device joins its ids to
the replica. That way an edited headword shows at once, and a map already drawn reads offline like
everything else.

It is served by one route, `GET /api/acervo/v1/map/{language}`.

### When the artifact is computed

The artifact is computed on request, whenever the set of `(senseId, digest)` pairs has changed
since the last one. One lock per owner and language keeps two devices from computing the same map
at once.

It is not a job, for two reasons:
- It is a few seconds of local CPU. It makes no model call and has no allowance to wait on.
- The job runner does one job at a time. A map queued behind an import's enrich jobs would be an
  hour out of date.

The one cold cost is the first embedding of every sense in a language, on the order of a minute on
the NAS. It is paid once and shown as *Drawing your map*.

### The map does not stay put, by design

Each time its input changes, the map is laid out again: plain UMAP, cosine metric, fixed seed.
Nothing pins a point to where it was.

Most vectors and the seed stay the same between layouts, so the picture moves less than a fresh
map would. Seeding the layout from the previous coordinates is a cheap later improvement. It is not
a requirement of this version, which is for finding out what the map is good for.

### Opens straight away

The device keeps the last artifact for each language in its own small IndexedDB store. It is kept
separate from the replica, as `dictionaryStore.ts` is, so neither wipe touches the other.

Opening the map draws that stored artifact at once, offline included. Meanwhile the device fetches
the current one. When it arrives, new points fade in and moved ones glide to their new places: the
map visibly grows by the words added since it was last opened.

If there is no stored map and no server, the map says so plainly. It never shows a spinner that
cannot finish.

### Regions

Regions come from agglomerative clustering (Ward) on the **2-D layout**, cut at two levels: about
8 regions and about 30 neighbourhoods. There is no noise class. HDBSCAN was rejected for the reason
the earlier plan gave: it marks much of a thousand-word vocabulary as noise, and that noise is the
long tail of minor interests worth keeping.

Clustering on the layout departs from the earlier plan, which clustered the raw vectors. The reason
is that a label has to sit over its points. A cluster found in 384 dimensions can land in pieces
across the plane, and its label then describes a place where half of it is not.

Below roughly 150 senses in a language, regions churn from one layout to the next. Such a map, like
Chinese today, has no regions, only words.

### Labels

Labels are deterministic first:
- the words nearest the region's centre
- c-TF-IDF terms over the region's definitions: the terms distinctive to that region compared with
  the others

They are written in the vocabulary's `definitionLang`, the language its definitions are in: Spanish
labels on the Spanish map, English labels on the English map.

The prototype shows these beside one model-written set, made once from the real vocabulary. A model
call becomes part of the map only if the deterministic labels read poorly.

### The surface is called Map

Obsidian calls its equivalent *Graph view*. "Map" suits a layout that has regions and no edges.

It is entered exactly as Loops and Stories are:
- an entry in the rail
- a third segment of the phone's foot bar

It replaces the list. The topic rail stays wherever there is room for it, so the way back is always
visible.

### Interaction, tablet first

- **Movement:** pinch to zoom and drag to pan, or on the Mac application, trackpad pinch and scroll.
  Double-tap zooms in.
- **Tapping:** a point opens its peek, and the peek's Open goes to the article. A region's label
  zooms to fit that region.
- **Controls:** a fit-all button. Plus and minus buttons appear only where there is no touch.
- **Returning:** coming back from an article puts the map where it was left.

What is labelled follows the zoom:
1. regions
2. neighbourhoods and the words nearest their centres
3. every headword
4. headword and gloss

Labels that would overlap are culled, in order of how central a word is to its region.

### The look

The proposed direction is an atlas:
- a paper background
- region names in spaced Literata italic, as on a printed map
- words in Plex Sans
- faint density contours showing where the vocabulary is thick
- teal kept for the selection alone

The prototype offers two or three directions behind its scaffolding switch, for the owner to
choose from: the atlas, a constellation drawn with nearest-neighbour links (close to Obsidian's
look), and softly tinted regions. The visual design is the part of this feature that decides
whether it gets used, so it is chosen by looking at it, not by writing about it.

### Built so it can move out

The owner may later move the map to the discovery repository and import it back here as a
package. Both halves are written so that the move is cheap.

**On the device,** the component lives in its own directory, `web/src/meaningMap/`. It takes its
own `MapData` type and imports nothing of Acervo's; a test checks that. It could then move to the
discovery repository and come back as a pinned package, the way the clip player comes from
`spoken-usage-retrieval`. Acervo's side is a pure adapter in `selectors.ts`'s manner, joining the
artifact to the replica.

**On the server,** the package mirrors `images/`:
- `src/acervo/meaning/` is standalone and pure: encode, lay out, cluster, label.
- A `services/` binding layer reads the graph and the cache.
- There is one route.
- An admin command exports texts and vectors for the discovery experiment.

## Ghosts (later)

Ghosts are not built now. They are named here so the first version does not block them.

- A ghost is a proposed word, drawn dashed.
- Which words to propose is decided by the discovery repository's algorithm, which is built to be
  interest-aligned rather than to find merely unknown words.
- Each ghost is embedded with the same encoder and placed with the same UMAP model's `transform`,
  so it lands where its meaning belongs.
- Tapping a ghost opens capture. The map decides *which* word and never builds the entry itself,
  so the article is reviewed before it is saved, like every other word.
- A switch on the map shows or hides ghosts.
- When they are computed, and what they cost, is part of that later task. The map opens instantly
  and a model call does not, so ghosts cannot be made when the map is opened.

## Steps

1. **This document.**
2. **Prototype** in `design/ui-prototype/`, opened by `?map=1` like `?loops=1`, with the real
   vocabulary's real layout.
   - A script in `experiments/meaning-space/`, with its own virtualenv, builds the data from an
     export bundle. It is also where encoders and labels are compared before the server adopts
     the settled choice.
   - The full real layout goes to a git-ignored file that the prototype loads when it is present.
     A committed sample of about 150 senses keeps a clean checkout openable without publishing the
     whole vocabulary.
3. **Server:** `src/acervo/meaning/`, the cache, the route and the admin export.
4. **Web and deploy:** the component, the adapter and the surface. The image gains the encoder and
   its dependencies and grows accordingly, but the schema does not change, so a plain
   `./deploy.sh` ships it with no converter.

## What counts as success

For this version:
- The regions are recognisable as the learner's own topics.
- The map opens instantly on the tablet, and moving around it feels like a map rather than a chart.

Later: whether ghosts proposed from a region are added more often than suggestions made without
one.
