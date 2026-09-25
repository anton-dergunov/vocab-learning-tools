# Similar projects

**As of:** September 2026. A quick survey rather than a market study: one pass over what is findable,
enough to say where Acervo overlaps with other work, where it does not, and what that implies.

No project found does what Acervo does as a whole. Most of its parts, taken one at a time, exist
somewhere else, and some of those places are crowded. The difference is the combination: one
personal, multilingual, sense-level graph that every kind of enrichment hangs off.

## The landscape

| Category | Examples | What they do better | What Acervo does that they do not |
|---|---|---|---|
| **Spaced repetition with LLM-written entries** | Jiaci (open source; LLM entries shared by all users, scheduled with ts-fsrs), Mochi, Anki add-ons | They own the review loop: scheduling and study *are* the product. | Senses as first-class records, provenance modelled rather than flagged, several languages in one graph. Scheduling is delegated to Anki rather than competed with. |
| **Sentence mining from media** | Migaku, LingQ, Language Reactor, Trancy, VocabSieve | Capture at the point of contact — inside a streaming service, a reader, a video — with little setup and a polished surface. | The clip corpus runs the other way: they find words inside media you chose; Acervo finds real speech for a word you already hold, with a model checking it is *this* sense. Nothing comparable was found. |
| **AI stories from your word list** | Storyling, LexiTale, Memfy, Miao AI, MeloLingua | Commercial polish, many languages, catalogues. **This is a crowded category.** | Stories drawn from the learner's own graph, narrated passage by passage with a direction each, with marks in both languages. A difference in quality, not in kind. |
| **Music** | Lingotify (real songs plus spaced repetition), Soundverse (generic generated songs) | Real songs carry culture that a generated track does not. | LexiBeat loops: built from the learner's own words, timed per word, with a translation never shown before it has been spoken. Nothing close was found. |
| **LLM vocabulary knowledge graphs** | DIY-MKG (EMNLP 2025 demo track): a personal graph grown by LLM-suggested related words, plus LLM-generated quizzes | The nearest research analogue to discovery by expansion. | Far deeper as a system — a durable store, sync, enrichment, media. DIY-MKG has almost no community around it, so the idea has a paper and the product space is still open. |
| **Visual lexicon explorers** | Visual Thesaurus, Visuwords, word2vec-graph, word-galaxy | Beautiful exploration of a *general* lexicon. | None of these is personal or multilingual. Acervo's meaning map is both: one learner's senses, per language (built September 2026; see below). |

## How Acervo differs

- **Personal and sense-level.** One owner, several languages at different levels, and senses as
  separate records rather than a word with a list of meanings. Provenance is part of the model: an
  attestation says where a word was met, a generated example names its model, a clip names its voice.
- **Breadth of enrichment on one graph.** Per-sense pictures briefed together per word, retrieved
  real speech, directed text-to-speech, loops, stories and offline dictionaries all read the same
  records, so an enrichment added later works on every word already held.
- **Decisions are measured.** Constrained decoding, audio encoding, caption quality and clip
  selection were each settled by an experiment with numbers, and the write-ups are in
  [`experiments/`](../experiments/README.md). That is rare in hobby projects and uncommon in
  commercial ones.
- **Offline-first and self-hosted.** Every read works without a network, and the data is the
  learner's own.
- **Discovery from interest, not ignorance.** The published work on vocabulary recommendation —
  Riiid's Pedagogical Word Recommendation — predicts what a learner does not know, pooled across a
  population. Acervo's sibling research repository, `interest-aligned-vocabulary-recommendation`,
  asks what one learner would *want* to learn next, from their vocabulary alone.

## Where it is weak, and what is planned

### The learning loop is not closed

Acervo builds the entry and hands study to Anki, so it cannot yet say whether anything it does helps
a word stick — the thing every competitor sells.

**Planned.** The Anki connection is to be wired up in both directions: cards go out to Anki, and
review statistics come back into Acervo. Anki is not going to be reimplemented. What Anki cannot do
is where Acervo adds activities of its own: loops and stories already exist, and how often a word
is heard — in a loop, in a story, as a played pronunciation — is exposure the application can
count. Those counts join the review statistics as a familiarity signal, used later to rank words
and to bring forward the less familiar ones. More activities are to come, and they are still being
thought through.

### Capture is text-first

The immersion tools meet the learner inside what they are already reading or watching. Acervo
waits for a scrap of text to be brought to it.

**Planned, in two directions.**

- **More ways in.** Capture from a photo — tap a word in a picture of a page and it is added — is
  specified in [`plans/photo-capture.md`](plans/photo-capture.md). Capture from speech may follow,
  as a secondary goal.
- **Immersion inside Acervo itself.** Generated stories and examples already contain words the
  learner does not know. Tapping one should show a short translation and, if the word looks worth
  having, add it without leaving the application. That makes Acervo's own generated material a
  source of new words, which none of the story apps above treat as a capture surface.

### The vocabulary is seen one way at a time

Today the vocabulary is a list, sortable and grouped into topics, and a **meaning map**: one
language's senses laid out by what they mean, with named regions, built in September 2026
([`server.md`](server.md), "The meaning map"). Neither shows how words relate across languages, to
what the learner knows well and badly, or to what is missing.

**Planned, as ideas rather than specifications.** The unifying idea is that **every view with slots
is a recommender**. Most of the views below have places in them — a row per concept and a column per
language, the rungs of an intensity scale, the members of a word family — and where a place is
empty the view can draw a **ghost**: a proposed word, dashed, one tap from capture, already explained
by where it sits. Which view's ghosts actually get added is then a question the sibling repository
`interest-aligned-vocabulary-recommendation` can answer from the accept / dismiss / ignore log it
already plans to keep.

On the map, ghosts are its discovery half. The discovery repository decides which words to propose,
interest-aligned rather than merely unknown; each is embedded with the same encoder and placed with
the same layout's `transform`, so it lands where its meaning belongs; tapping one opens capture, so
the entry is reviewed like every other word; a switch shows or hides them. They cannot be computed
when the map opens, since the map opens instantly and a model call does not. The map's own test of
success is that its regions read as the learner's own topics; the ghosts' is whether words proposed
from a region are added more often than ones proposed without one.

The views, by what they need — *graph* (records Acervo holds), *deterministic* (no model call),
*lexicon* (Wiktextract, `wordfreq`, published norms) or *LLM* (a model call whose output needs
checking):

- **Meaning space** (built as the map): treemap of the region hierarchy; density holes beside the
  learner's regions; *near in your vocabulary* on an article, which is where confusions live — the
  map already ships each sense's nearest neighbours, so this one is cheap.
- **Across languages:** a concept grid, one row per concept and one column per language, gaps
  visible (graph; every empty cell a ghost); cognate and etymology chains (lexicon); false friends
  (LLM or lexicon).
- **Lexical relations:** word families (lexicon, LLM); the Chinese character network, 电 → 电脑,
  电话, 电影 (deterministic); synonym and hypernym graphs (the compiled dictionaries); clines,
  tibio < caliente < hirviendo (LLM); semantic-field grids, cooking verbs × heat, water, fat (LLM);
  collocation wheels (clip corpus, or LLM checked against it); frames, a scene with roles filled by
  the learner's words (LLM); contrast cards for near-synonyms (usage notes, LLM).
- **Visual and situational:** a picture wall of sense images per topic (graph); a labelled scene,
  one generated kitchen with the learner's kitchen words as hotspots; an emotion wheel from the
  `emotion` a lexeme carries (graph); valence and concreteness scatters (NRC VAD, norms); a routine
  as a timeline (LLM); a regional map of Spanish variants (usage notes, LLM).
- **The learner:** any map coloured by recall strength, and by exposure once it is counted; a
  frequency ladder with a coverage curve (`wordfreq`); an acquisition diary as a calendar heatmap;
  the frontier, shaky words beside solid ones in the same region.
- **Form and sound:** the Chinese tone-pair grid and syllable table (deterministic); Spanish gender
  and conjugation classes; the measure-word grid, 张 → flat things; rhymes and minimal pairs, useful
  for loops too; a register scatter.
- **Generated:** an LLM outline of a topic as a titled hierarchy; crosswords and word searches; a
  short topic dialogue, the small sibling of a story.

The cheap ones, needing no model call, are the concept grid, the character network and the picture
wall; the ones that show the most language work are clines and semantic-field grids.

### Heavy to maintain, and hard for anyone else to run

A NAS, Docker, several model providers with their own credentials, and two companion services.
Acceptable for one owner; a ceiling on its value as a public project.

**Planned.**

- **A standalone macOS application**: download, open, use, with the data kept on the machine and no
  server at all. This is a real design change rather than packaging — today every write is a round
  trip to the server, by design — and it needs its own plan.
- **A simpler self-hosted path** for anyone who wants sync across devices.
- **A hosted service** with downloadable desktop and mobile applications is a possibility if the
  project succeeds, and is not planned now: it needs a server somewhere and the resources to run it.

Only macOS is in scope for the standalone application. Other platforms may come later and are not a
priority.

### Evaluated on one person

Every measurement so far is n-of-1. That is honest, and it limits what can be claimed.

**Planned.** Opening Acervo to other learners, including languages the owner is not learning.

## Sources

- Spaced repetition: [awesome-fsrs](https://github.com/open-spaced-repetition/awesome-fsrs),
  [awesome-fsrs site](https://open-spaced-repetition.github.io/awesome-fsrs/),
  [open-source Anki alternatives](https://alternativeto.net/software/anki/?license=opensource)
- Sentence mining: [Migaku vs Language Reactor](https://www.langpanda.com/compare/migaku-vs-language-reactor),
  [Language Reactor alternatives](https://www.trancy.org/blog/7-best-language-reactor-alternatives-compared-2026-3609d2252005811db7f7d41131756428),
  [Migaku alternatives](https://wordy.info/blog/migaku-alternatives),
  [LingQ alternatives](https://lexirise.app/blog/article/free-lingq-alternative),
  [VocabSieve](https://github.com/FreeLanguageTools/vocabsieve)
- Stories: [Storyling](https://www.storyling.ai/), [LexiTale](https://www.lexitale.ai/en),
  [Memfy](https://apps.apple.com/us/app/memfy/id6756895423), [Miao AI](https://miaoai.app/),
  [MeloLingua](https://melolingua.com/ai-story-language-app)
- Music: [Lingotify](https://www.lingotify.app/),
  [Soundverse on songs for language learning](https://www.soundverse.ai/blog/article/how-to-make-ai-songs-for-language-learning-content-0232)
- Knowledge graphs: [DIY-MKG](https://github.com/kenantang/DIY-MKG)
- Visual explorers: [Visual Thesaurus](https://www.visualthesaurus.com/),
  [word2vec-graph](https://github.com/anvaka/word2vec-graph),
  [word-galaxy](https://github.com/lusilva/word-galaxy),
  [Visual Thesaurus alternatives](https://alternativeto.net/software/visual-thesaurus)
- Recommendation: Shin & Park, *Pedagogical Word Recommendation*, [arXiv:2112.13808](https://arxiv.org/abs/2112.13808)
