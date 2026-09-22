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

The real vocabulary it is sized against has 1,443 Spanish senses (922 words), 857 English senses
(568 words) and one Chinese word. About 45% of words have more than one sense. The 19 Sep 2026
export also carried 227 English words twice, with identical senses, which the map leaves out.

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

It is served by one route, `GET /api/acervo/v1/map/{language}`, and kept as a file beside the
database (`maps/artifacts/<owner>/<language>.json`, next to the embedding cache in
`maps/embeddings/`). Its body is `{fingerprint, model, side, words, senses, names, points, regions,
contours}`:

- a point is `{sense, lexeme, x, y, r, h, rank, nb}`: the sense and word ids, the position, the
  region and neighbourhood indices, how central it is to its neighbourhood, and its five nearest
  senses of other words as point indices;
- a region is `{id, level, index, x, y, count, region?, labels: {words, terms, name?}}`;
- `names` is `pending` until the naming job lands, then `ready` — or `none` for a map with no
  regions, or a naming that failed for good.

The fingerprint is a digest of every `(senseId, text digest)` pair, the model and the layout's
parameters. The **version** is the fingerprint and the state of the names together, because naming
changes the map without changing its layout. A device that holds a map sends its version as
`?have=`, and a map still current answers `{"current": true}` and nothing else. Asking by
fingerprint alone, a device holding the unnamed map would be told it was current and never see the
names. An unknown language is a 404 `unknown_language`.

### When the artifact is computed

The artifact is computed on request, whenever the set of `(senseId, digest)` pairs has changed
since the last one. One lock per owner and language keeps two devices from computing the same map
at once.

It is not a job, for two reasons:
- It is a few seconds of local CPU. It makes no model call and has no allowance to wait on.
- The job runner does one job at a time. A map queued behind an import's enrich jobs would be an
  hour out of date.

The one cold cost is the first embedding of every sense in a language. On a laptop, all 1,443
Spanish senses took 35 s cold (loading the model and embedding everything) and 3.4 s warm; the NAS
is several times slower. It is paid once and shown as *Drawing your map*. After that, an edited
sense is the only one embedded again, and the rest of the time is the layout.

### The map does not stay put, by design

Each time its input changes, the map is laid out again: plain UMAP, cosine metric, fixed seed.
Nothing pins a point to where it was.

A fixed seed alone does **not** keep the picture in place. On the real vocabulary, removing 2% of
the English words and laying it out again returned the map mirrored: a median point moved half the
map's width. So each new layout is **aligned onto the previous one** (a Procrustes fit: rotation,
reflection, scale and shift, one SVD) before it is stored. After that, a median point moves 4–10% of
the map's width, measured in
[`experiments/meaning-space/`](../../experiments/meaning-space/README.md).

The UMAP setting that gives the map islands rather than an even disc (`min_dist` 0.1) is also the one
that moves more between layouts. Alignment alone was not enough on the server's own measurement:
one edited Spanish sense moved the median point 140 of 1,000 units. So **a new layout also starts
from the previous one**. Every sense the last map held begins where it was, and a new one begins
beside its three nearest held senses. With that, one edited sense moved the median point 37 units,
and 2% more words moved the rest 39 (against 179 from a cold start). Nothing is pinned: a sense
still goes where its meaning now puts it.

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

**On the real vocabulary, they did.** The model's names read as places: *dinero y trabajo*,
*pagos y deudas*, *aggression and hostility*. The nearest headwords read as a list, and the c-TF-IDF
terms carry definition boilerplate such as *dicho* and *showing*. So the map uses model-written
names, and the reason for going deterministic first still shapes how:

- A freshly drawn map with regions queues one `map.name` job. It names every region and
  neighbourhood in one call on the owner's text chain, from `prompts/acervo_map_names.md`.
- A second drawing before the first is named queues nothing new: the job's subject is the language.
- A job whose map has since been redrawn finds its fingerprint stale and does nothing.
- The map never waits for a name. Until the job lands, `names` is `pending` and each region shows
  its nearest headwords; the job's completion on `/events` is how the device knows to ask again.
- The owner's standing rules are not appended to the naming prompt: like resolve, it only labels.

### The surface is called Map

Obsidian calls its equivalent *Graph view*. "Map" suits a layout that has regions and no edges.

It is entered exactly as Loops and Stories are:
- an entry in the rail
- a third segment of the phone's foot bar

It replaces the list. The topic rail stays wherever there is room for it, so the way back is always
visible.

On the map, **the top bar carries the map's own row** in place of search, Add and sync, at every
width: Back, the name, the counts, Find, and the map's own language switcher. It is the top bar
itself — the same box, surface and rule, the brand cell beside it — rather than a card floating over
the map, which is what the first version drew. The counts of meanings and words show wherever there
is room and go on a phone, where Find takes the width and nothing is kept for them. ⌘K leaves the
map for search, as it leaves Loops. While a surface replaces the list, only its own tab in the rail
is lit; the topic behind it is not.

**From an article to the map and back.** Every sense of an article carries a small map button, beside
the one that asks about it on the page and beside its definition on a card. It opens the map in the
word's language flown to that sense with it selected, as Find would leave it, and Back from that map
returns to the article on the same sense. The other way, *Open the article* from the peek lands on the
peeked sense: its card in Cards, its section scrolled to the top in Page.

**A sense is named by its emoji.** The article's sense chips and headings show a sense's emoji and its
domain, whichever it has — `🔪 cooking`, or `😳 3` on a chip — as the map shows them. Most senses have
an emoji and no domain, and showing the emoji only beside a domain left them as bare numbers.

### Interaction, tablet first

- **Movement:** pinch to zoom and drag to pan, or on the Mac application, trackpad pinch and scroll.
  Double-tap zooms in.
- **Tapping:** a point opens its peek, and the peek's Open goes to the article. A region's label
  zooms to fit that region.
- **Controls:** a fit-all button. Plus and minus buttons appear only where there is no touch.
- **Keyboard and mouse:**
  - ⌘ + scroll zooms about the pointer (Ctrl + scroll elsewhere), as in Figma and Maps. A mouse
    wheel's notches zoom too; a trackpad's two-finger scroll pans.
  - ⌘= / ⌘− / ⌘0 zoom in, out and fit while the map is open, taking over the browser's page zoom
    the way any canvas application does. The Mac host binds no zoom item, so the keys reach the page.
  - Bare `+ − 0` and the arrows work whenever nothing is being typed.
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
   vocabulary's real layout. Built, and accepted as the design, with the map's row as the top row
   and the keyboard and mouse zoom added after testing.
   - A script in `experiments/meaning-space/`, with its own virtualenv, builds the data from an
     export bundle. It is also where encoders and labels are compared before the server adopts
     the settled choice.
   - The full real layout goes to a git-ignored file that the prototype loads when it is present.
     A committed sample of about 150 senses keeps a clean checkout openable without publishing the
     whole vocabulary.
3. **Server:** `src/acervo/meaning/`, the cache, the route, the naming job and the admin commands
   (`map show`, `map export`). Built.
4. **Web and deploy:** the component (`web/src/meaningMap/`, importing nothing of Acervo's), the
   adapter (`mapDataFor` and `mapPeekFor` in `selectors.ts`), the device's store of the last map
   per language (`mapStore.ts`) and the surface (`MapView.tsx`), entered from the rail and the foot
   bar. Built. The image gains the encoder and its dependencies and grows accordingly, but the
   schema does not change, so a plain `./deploy.sh` ships it with no converter.

## What counts as success

For this version:
- The regions are recognisable as the learner's own topics.
- The map opens instantly on the tablet, and moving around it feels like a map rather than a chart.

Later: whether ghosts proposed from a region are added more often than suggestions made without
one.
