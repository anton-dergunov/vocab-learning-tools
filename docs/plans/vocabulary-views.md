# Vocabulary views · ways to see the word list

**Status:** a list of ideas, none specified and none built. The first to be worked out is
[the meaning space](meaning-space.md). Each of the others needs defining before it is planned.

Today the vocabulary is a plain list, sortable several ways and grouped into topics. That is a good
default and it stays. What it cannot do is show how words relate — to each other, across languages,
to what the learner knows well and badly, and to what is missing.

## The unifying idea: every view with slots is a recommender

Most of the views below have a structure with places in it: a row per concept and a column per
language, the rungs of an intensity scale, the members of a word family, the cells of a grid. Where a
place is empty, the view can draw a **ghost** — a proposed word, dashed, one tap from being added
through capture. So a view is both a way to explore and a source of candidates for discovery, and the
candidate arrives already explained by where it sits.

That also makes the views comparable: which view's ghosts actually get added is a question the
discovery experiment (`interest-aligned-vocabulary-recommendation`) can answer from the same
accept / dismiss / ignore log it already plans to keep.

**Built from** below says what each view needs. *Graph* means records Acervo already holds;
*deterministic* means no model call; *lexicon* means an open resource such as Wiktextract, `wordfreq`
or published norms; *LLM* means a model call whose output needs checking.

## Meaning space

| View | What it shows | Built from | Ghosts |
|---|---|---|---|
| **Cluster map / word clouds** | Islands of related senses, each with a label, sized by how many words it holds | Sense embeddings, clustering | Suggestions for a chosen cluster |
| **Zoomable atlas** | One continuous map: cluster labels when zoomed out, words and then senses when zoomed in | Embeddings, 2-D layout, hierarchical clusters | As above |
| **Treemap / circle packing** | The cluster hierarchy as nested areas | Hierarchical clusters | — |
| **Density holes** | Thin regions beside the learner's clusters | Embeddings | Words that would fill them |
| **Near in your vocabulary** | On an article, the learner's nearest senses — which is where confusions live | Embeddings | — |

Specified further in [`meaning-space.md`](meaning-space.md).

## Across languages

| View | What it shows | Built from | Ghosts |
|---|---|---|---|
| **Concept grid** | One row per concept, one column per language, with gaps visible: *picar* is known, 痒 is not | Graph (glosses), deterministic | Every empty cell. Anchored by a gloss, so a model rarely invents one |
| **Cognate and etymology chains** | A Latin root branching into Spanish and English | Lexicon (Wiktextract etymologies) | Missing branches |
| **False friends** | *embarazada* beside *embarrassed* | LLM, or lexicon | — |

## Lexical relations

| View | What it shows | Built from | Ghosts |
|---|---|---|---|
| **Word families** | comer → comida, comedor, comestible | Lexicon (derived terms), LLM | Missing members |
| **Character network** (Chinese) | Words sharing a character — 电 → 电脑, 电话, 电影 — and each character's components | Deterministic | Common words on a character already held |
| **Synonym, antonym, hypernym graph** | The thesaurus neighbourhood of a word | Lexicon (the compiled dictionaries) | Unheld neighbours |
| **Clines** | Words ordered by intensity: tibio < caliente < hirviendo; like < love < adore | LLM | Missing rungs |
| **Semantic-field grids** | A field against its distinguishing features: cooking verbs × heat, water, fat; motion verbs × manner, path | LLM | Empty cells |
| **Collocation wheels** | tomar → decisión, café, el pelo | Clip corpus, or LLM checked against it | Unheld collocates |
| **Frames** | A scene with roles — buyer, seller, goods, price — filled by the learner's words | LLM | Unfilled roles |
| **Contrast cards** | Two near-synonyms and what separates them | Graph (usage notes), LLM | — |

## Visual and situational

| View | What it shows | Built from | Ghosts |
|---|---|---|---|
| **Picture wall** | Sense images tiled per topic, for a fast visual scan | Graph (the images exist) | — |
| **Labelled scene** | One generated picture — a kitchen — with the learner's kitchen words as hotspots on it | Image pipeline, plus placing the labels | Unlabelled objects in the scene |
| **Emotion wheel** | Words placed by the `emotion` a lexeme already carries | Graph | — |
| **Affect and concreteness scatter** | Valence against arousal, or concrete against abstract | Lexicon (NRC VAD, concreteness norms) or LLM ratings | — |
| **Day or script timeline** | A routine — a morning, a trip to the doctor — with its words in order | LLM | Missing steps |
| **Regional map** | Spain, Mexico, Argentina: which variant a word belongs to | Graph (usage notes), LLM | Other regions' variants |

## The learner

| View | What it shows | Built from | Ghosts |
|---|---|---|---|
| **Strength map** | Any of the maps above coloured by recall strength, so weak regions show at a glance | Study states, plus exposure counts once they exist | — |
| **Frequency ladder** | Per language, words by frequency band, with a coverage curve for ordinary text | Lexicon (`wordfreq`) | High-frequency words not yet held |
| **Acquisition diary** | When words were added, as a calendar heatmap, grouped by where they were met | Graph (dates, attestations) | — |
| **Frontier** | Shaky words beside solid ones in the same cluster | Study states, embeddings | — |

## Form and sound

| View | What it shows | Built from | Ghosts |
|---|---|---|---|
| **Tone-pair grid** (Chinese) | Two-syllable words by tone pair, 1-1 to 4-4 | Deterministic (pinyin) | Empty pairs |
| **Syllable table** (Chinese) | The pinyin table, with the syllables the learner has words for | Deterministic | — |
| **Gender and conjugation** (Spanish) | Nouns by gender; verbs by irregularity class | Graph, lexicon | — |
| **Measure-word grid** (Chinese) | 张 → flat things, 条 → long things | LLM, lexicon | Nouns missing from a classifier |
| **Rhymes and minimal pairs** | Words that sound alike — useful for loops too | Deterministic (phonetic forms) | — |
| **Register scatter** | Formality against frequency | LLM, lexicon | — |

## Generated artefacts

| View | What it shows | Built from | Ghosts |
|---|---|---|---|
| **LLM outline** | A topic organised into a titled hierarchy in one call — a taxonomy rather than a map | LLM | Empty headings |
| **Crossword / word search** | A topic as a puzzle | Deterministic | — |
| **Topic dialogue** | A short exchange using a cluster's words, the small sibling of a story | LLM | New words met in it, captured by tapping |

## Where to start

- **The meaning space**, first, because it is the discovery prototype's map with one more layer,
  and it links the two projects. See [`meaning-space.md`](meaning-space.md).
- **Cheap and needing no model call:** the concept grid, the Chinese character network and the
  picture wall.
- **Showing the most language work:** clines and semantic-field grids.
