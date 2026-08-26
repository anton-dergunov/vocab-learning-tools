# Acervo

**Design document · Rev. A · 26 Aug 2026 · V1 scope agreed**

> *acervo* — *m.* — the body of words a person actually holds — *working name, rename freely*

A self-hosted, offline-capable store for the words *you personally chose to learn*, in every
language you are learning — and a set of consumers that turn it into study material: Anki, a corpus
of real spoken usage, generated reading, an LLM tutor.

---

## §01 · The shape

### One durable core, several disposable consumers

The failure mode of every tool in this space is that the word list is scaffolding for one output —
a deck, a reader, a mining workflow — so the list inherits that tool's assumptions and dies with it.
Acervo inverts this. The vocabulary is the asset. Everything else is a renderer that can be deleted
and rebuilt.

```
CONSUMERS — disposable, rebuildable
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Anki + FSRS   │ │ LLM tutor     │ │ Narrow        │ │ Clip review   │ │ Obsidian      │
│ stats flow    │ │ production    │ │ reading       │ │ real spoken   │ │ export        │
│ back in       │ │ practice      │ │ stories·comics│ │ usage         │ │ read-only     │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                 │                 │                 │
        ▼                 ▼                 ▼                 ▼                 ▼
════════════════════════════════════════════════════════════════════════════════════════
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ THE CORE — durable, synced, yours                                                    │
│                                                                                      │
│   lexeme · sense · attestation · example · studyState                                │
│                                                                                      │
│   full replica on every device · tombstoned · revision cursor · ~940 entries today   │
│   es · en · zh-Hans — multilingual from row one                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
                  ╎ grounding                        ╎ lookups
                  ▼                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ THE CORPUS — large, read-only, regenerable from scratch                              │
│                                                                                      │
│   Wiktextract senses · Tatoeba pairs · subtitle index · frequency lists              │
│   never synced to devices · queried online only · millions of rows                   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Solid arrows: content out, statistics back. Dashed: the corpus is consulted, never replicated.

### The invariants

- **Content flows out of the core; statistics flow in. Never both ways.** Anki does not own "is this
  word learned." It reports, the core decides. Bidirectional content sync between a structured store
  and a flashcard collection is the swamp that eats these projects.
- **Anything the corpus holds must be rebuildable by running a script.** If losing it would hurt, it
  belongs in the core instead.
- **The core is small enough to hold entirely, on every device, forever.** No pagination, no
  server-side query, no sync scoping. This is a design constraint, not just a happy fact — see §04.
- **Every generated row carries its provenance and the model that made it.** That is what lets you
  mass-regenerate in two years without touching a word you wrote yourself.

---

## §02 · Sizing

### Two systems, four orders of magnitude apart

The single most useful number in this document: your Spanish vocabulary is **~940 entries** across
twelve topic files, and the English file is ~700 lines. Ten times that, with full extended articles
and no media, is still tens of megabytes.

**What each layer actually holds**

| Layer | Rows (realistic ceiling) | On disk | Lives where | If lost |
|---|---|---|---|---|
| **Core** | ~10,000 lexemes | 20–50 MB | Every device, in full | Irreplaceable |
| **Media** | ~30,000 files | 2–10 GB | Server, fetched on demand | Regenerate on the Mac |
| **Dictionaries** | ~1M senses / language | 1–3 GB | Server only | Re-download |
| **Subtitle index** | 3–5M merged lines | 2–6 GB | Server only | Re-harvest |

> ### DECISION
> **The core and the corpus do not share a database, a container, or a backup policy.**
>
> **Because** they have nothing in common: one is 50 MB of precious hand-curated relational data
> that must sync to a phone, the other is gigabytes of disposable read-only text that must be
> full-text searched. Every design pressure points the opposite way for each.
>
> **This also means** you can experiment freely on the corpus side — rebuild it, swap the engine,
> get the schema wrong — with zero risk to the data you care about.

---

## §03 · Data model

### The schema, and the table worth fighting for

Your current markdown conflates things that need separating — a headword, its several meanings, the
sentence you met it in, and an illustrative example are four different kinds of thing with four
different lifetimes.

**`lexeme` — the thing being learned**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Client-generated. Never server-assigned — see §04. |
| `language` | BCP-47 | `es`, `en`, `zh-Hans`. Required, indexed, on every query. |
| `headword` | string | As you'd look it up: `desmayarse`, `ponerse malo`, `para entonces`. |
| `lemma` | string | Normalized form for corpus matching. Usually equals headword. |
| `reading` | string? | Pinyin, furigana, transliteration. Empty for Latin scripts, mandatory for `zh`. |
| `pos` | enum | noun · verb · adj · adv · **phrase** · idiom · expression |
| `gender` | enum? | Spanish articles. `la balsa` vs `el tobillo`. |
| `register` | enum? | neutral · formal · colloquial · slang · vulgar. Your Slang file is already this, as a filename. |
| `dialect` | string? | `es-ES` / `es-MX`. Matters more than you'd think once the corpus is in. |
| `emoji` | string? | Keep it — it's genuinely good recall scaffolding and it's already in your data. |
| `topics` | string[] | Was your filename. Now many-per-word, which fixes the 387-entry *Misc* file. |
| `status` | enum | inbox → active → learned → retired, plus **suppressed**. |
| `addedAt` / `deviceId` | ts / string | Sync metadata, per §04. |

> **WHY "SUPPRESSED" EARNS ITS PLACE**
> Without a way to say *"I saw this, I've decided not to learn it"*, the same word arrives through
> capture forever and dedup can never tell a new word from a rejected one. It's one enum value that
> saves a recurring annoyance.

**`sense` — one meaning, ordered**

| Field | Type | Notes |
|---|---|---|
| `lexemeId` | uuid | |
| `glossLang` | BCP-47 | **Not a constant.** See the note below — this is the field your data forced. |
| `gloss` | string[] | `["column", "spine"]` — your `la columna` is already two senses pretending to be one. |
| `definitionL2` | string? | Monolingual definition. Optional, and increasingly the one you should be reading. |
| `domain` | string? | medicine · law · cooking. Comes free from Wiktextract. |
| `order` | int | Sense ordering is information — put the common one first. |

> **CAUGHT WHILE READING YOUR NOTES**
> Your Spanish is glossed in English — but your English vocabulary is glossed in **Russian**
> (`turmoil — суматоха`, `hoax — мистификация`). A single global "L1" would have silently mangled
> half your data on import. `glossLang` lives on the sense, and a lexeme may carry senses glossed in
> more than one language.

**`attestation` — where you actually met the word**

This is the table to fight for. It is the only data in the entire system that is genuinely
irreplaceable: a model can regenerate every gloss and every example forever, but nothing can
reconstruct the sentence you were reading on your tablet when you hit `turmoil`.

| Field | Type | Notes |
|---|---|---|
| `lexemeId` | uuid | |
| `text` | string | The sentence as encountered. Verbatim, typos included. |
| `translation` | string? | Only if you wrote one. |
| `sourceUrl` / `sourceTitle` | string? | Captured automatically — free, and you will want it later. |
| `sourceKind` | enum | web · book · conversation · video · lesson · unknown |
| `capturedAt` | ts | |

> **YOUR EXISTING PIPELINE DISCARDS THIS**
> `clean_vocab.py` keeps the model's rewrite and drops the source. Invert it: keep both, mark
> provenance, and prefer the real one when rendering. Your English file is full of these and they
> are the best thing in it — *"Since then, I have been navigating the job market as a junior,
> alongside the uncertainties and turmoil caused by losing my job."* No generated sentence will ever
> mean that much to you.

**`example`, `studyState`, `captureQueue`**

- `example` — `senseId · l2 · l1 · origin(llm|tatoeba|subtitle|wiktionary|manual) · modelId ·
  videoRef · imageRef · audioRef · approved`. `origin` plus `modelId` on every row is what makes
  bulk regeneration safe.
- `studyState` — one row per *(lexeme, system)*: `system · noteId · cardIds[] · reps · lapses ·
  stability · difficulty · retrievability · lastReview · syncedAt`. Keyed by system so a second
  learning tool never collides with Anki.
- `captureQueue` — raw input exactly as it arrived, unprocessed. Your `Spanish vocab - Inbox.md`, as
  a table.

Multi-word entries fall out for free: `ponerse malo`, `que se mejoren` and `para entonces` are
lexemes whose headword contains spaces and whose `pos` is `phrase`. Your data already has dozens, so
make it a first-class case rather than an afterthought.

**Specimen — one entry, fully rendered**

> ### desmayarse  *v. pron. · es · neutral*  😵‍💫
>
> 1. **to faint; to pass out**
>    - Me **desmayé** cuando vi a la aterradora criatura.  `[yours · Jan 2026]`
>    - Se **desmayó** en pleno directo, delante de las cámaras.  `[clip · DW Español · 4:12]`
> 2. **to be overcome (with emotion)** — *lit.*
>    - Casi me **desmayo** de la emoción.  `[tatoeba]`

Every example says where it came from. Watching which tier your words actually land in is the
fastest way to learn whether the corpus is big enough.

---

## §04 · Storage & sync

### A second PocketBase, and the sync engine you already wrote

> ### DECISION
> **The core runs on a second PocketBase instance beside Calorie Logger, reusing its sync design
> wholesale.**
>
> **Because** you have a proven, documented, offline-first replica engine that you personally rely
> on daily. It already solves tombstones, the monotonic revision cursor, per-record rejection, and
> the `datasetId` trap that makes a rebuilt database silently report itself in sync. Rewriting that
> costs weeks and buys nothing.
>
> **Coexistence is a non-issue.** Your `compose.yaml` is already parameterized: a different
> `container_name`, `PB_PORT` and `PB_DATA_PATH` is the entire change. Separate container, separate
> volume, separate SQLite file. They never see each other.

### On wanting NoSQL experience

A legitimate motivation — but don't put it in the critical path of an app you want to *use*, and
don't let it push you toward a database your data doesn't want. The core is small and thoroughly
relational: lexeme → sense → example → attestation → card link are all joins. MongoDB Community is
free to self-host, but idles at hundreds of megabytes against PocketBase's ~20, and buys nothing
here.

Put that curiosity where it is genuinely earned: **the corpus index** (§06). Millions of lemmatized
subtitle lines with ranked full-text retrieval and faceting is a real search-engineering problem —
and a far better thing to have built than "I stored 900 words in Mongo." It is also the layer where
getting it wrong costs you nothing.

### What carries on every replicated row

Unchanged from Calorie Logger, because it works: `deleted`, `createdAt`, `editedAt`, `editedBy`,
`revision`. Last-writer-wins on `(editedAt, editedBy)`, computed identically on client and server.
Deletions are tombstones. Ids are client-generated so a word captured on a plane can be edited,
glossed and deleted before any server hears of it.

> **ONE THING THAT MUST BE RE-DERIVED, NOT COPIED**
> Merge order. Calorie Logger merges foods before entries before settings, because an entry's food
> relation must resolve. Here it is `lexeme → sense → example / attestation / studyState`. Get this
> wrong and offline-created rows fail validation on push and sit in the queue looking like a network
> problem.

### Media

Images and audio are **not** replicated. They live on the server, are referenced by content hash,
and are fetched and cached on demand by the service worker. The text of your vocabulary works on a
plane; the illustrations do not, and shouldn't pretend to.

---

## §05 · Capture

### Three seconds, or you will stop doing it

You buried this in the middle of describing the system, but it is the make-or-break. If capturing a
word from a page you're reading takes longer than a few seconds, you stop, and every other feature
here is moot.

**Capture path per platform**

| Where | Mechanism | Reality |
|---|---|---|
| **Android** | PWA **Web Share Target** | Select text → Share → Acervo appears in the sheet. Works properly. Best case. |
| **iPad / iPhone** | **iOS Shortcut** that POSTs | Safari does not support share targets. A Shortcut on the share sheet is the real answer, works inside any app, one-time setup. |
| **Desktop browser** | Bookmarklet | Grabs selection + URL + title in one click. |
| **Anywhere** | Paste into the app | The floor. Must never be the only option. |

- **Always capture the surrounding sentence, the URL and the page title**, not just the selected
  word. Free `attestation` rows, and it costs the user nothing.
- **Everything lands in `captureQueue` raw.** No processing at capture time — it must work offline
  and finish instantly.
- **Processing is a separate, reviewable batch:** language detection, lemmatization, sense
  splitting, dedup against existing lexemes, article generation. This is what `clean_vocab.py`
  already does; it becomes a worker against the API instead of against markdown files.
- **An inbox review screen is v1, not a nicety.** Batch-approve, edit, merge into an existing
  lexeme, or suppress.

---

## §06 · Corpus · v1

### Invert the video problem and it disappears

You framed it as: acquire a subtitle corpus, then find the intersection with video you can legally
play for free. That intersection is genuinely painful to compute, and it is where the idea dies.

> ### DECISION
> **Start from channels you can already play, and take only their human-authored subtitles.**
>
> ```
> yt-dlp --skip-download --write-subs --no-write-auto-subs --sub-langs es --sub-format vtt <channel>
> ```
>
> `--no-write-auto-subs` means machine-generated captions are never downloaded. Videos without real
> subtitles simply produce no file. **The quality filter and the playability filter become the same
> filter**, computed for free, and the intersection problem stops existing.

This settles every worry you raised at once:

- **Playable?** By construction — you enumerated it from YouTube.
- **Subtitle quality?** By construction — auto-captions were never fetched.
- **Blocked for scraping?** No. You fetch *text only*, once, incrementally, throttled, from a
  curated channel list. A few thousand VTT files is tens of megabytes — nothing like scraping
  volume.
- **Storage and legality?** You store subtitle text, video id and timestamp. **Never the video.**
  Playback is the YouTube IFrame embed with `start=<seconds>`: the video streams from YouTube, the
  creator gets the view, you host nothing.

### Sources, tiered

| # | Source | What it gives |
|---|---|---|
| 1 | **Video clip** | Human subtitles from free channels. Shows register, speed, regional accent. Playable in place. |
| 2 | **Tatoeba** | Millions of human-translated sentence pairs, CC-BY. Text only, but genuinely human. |
| 3 | **OpenSubtitles / OPUS** | Sentence-aligned subtitle corpora, 60 corpora across 58 languages. Broad coverage, no playback. |
| 4 | **Wiktextract** | Wiktionary as JSONL — senses, IPA, inflections, domains. The *grounding* source (§07) more than an example source. |
| 5 | **Generated** | The fallback, not the default. Correct, and blander than any of the above — see §07. |

### The pipeline

`harvest → merge cues into sentences → tokenize → lemmatize → filter → index`

- **Merge cues before indexing.** Subtitle cues are display fragments, not sentences — they break
  mid-clause every two seconds. Merging adjacent cues into sentence-ish units, carrying the earliest
  timestamp, is the difference between usable results and garbage. This is the step most people
  skip.
- **Lemmatize, or the whole feature under-delivers.** Your entry is `desmayarse`; the subtitle says
  `me desmayé`. Without lemma matching your hit rate is dismal and you'll wrongly conclude the
  corpus is too small. Index lemmas, match lemmas, display surface forms.
- **Filter** on length, on being sentence-like, on not being a duplicate across episodes, and drop
  lines that are mostly proper nouns.
- **Offset the timestamp ~0.5 s earlier** for the embed, or the clip starts mid-word.

> ### ENGINE
> **Meilisearch, with SQLite FTS5 as the honest fallback.**
>
> At 3–5M rows either works. Meilisearch gives you ranking, faceting by channel/source/difficulty,
> and real ops experience in a single container; FTS5 gives you zero operational surface and one
> fewer thing to back up. Since exact lemma matching doesn't need typo tolerance, this is genuinely
> a preference — and it is the one place in this design where "which would I rather have learned" is
> a valid tiebreaker.

### Language coverage from row one

**Per-language configuration — one config block per language, not code branches**

| | Spanish `es` | English `en` | Chinese `zh-Hans` |
|---|---|---|---|
| **Gloss language** | `en` | `ru` | `en` |
| **Tokenizer** | whitespace | whitespace | **jieba** — no word boundaries |
| **Lemmatizer** | spaCy `es_core_news_sm` | spaCy `en_core_web_sm` | n/a — characters are stable |
| **Reading field** | — | — | **required** (pinyin) |
| **Dictionary** | kaikki `es`, Apertium, FreeDict | kaikki `en` | CC-CEDICT / ECDICT |
| **TTS** | Kokoro `es` | Kokoro `en` | Kokoro `zh` |
| **Corpus channels** | Dreaming Spanish, Easy Spanish, DW Español, TED es, RTVE | TED, plus what you already read | deferred to v1.1 |
| **Anki deck** | `Spanish::Vocabulary` | `English::Vocabulary` | `Chinese::Vocabulary` |

> **WHAT MULTILINGUAL ACTUALLY COSTS**
> Almost nothing structurally — `language` on every row and a config block per language. The real
> cost is three specific things: **Chinese needs segmentation** before anything else works, **the
> reading field** must exist from the first migration, and **collation differs per language**, so
> sorting is a per-language function rather than a global one. Retrofitting any of those later is
> genuinely painful, which is why they belong in v1 even though Spanish is 90% of your usage today.

---

## §07 · Generation

### Ground the model, and it stops being a knowledge source

You asked whether anyone has benchmarked LLM-written vocabulary entries against human ones. Not
directly, as far as I can find — no study compares generated bilingual dictionary entries to
lexicographer-written ones. What the adjacent literature does say is more useful than a benchmark
would have been:

- In educational content generation, GPT-4-class models produce material of comparable quality to
  human experts, while weaker models are measurably worse — consistent with your own experience.
- Flashcard *authorship* barely affects retention: self-made and other-made cards both beat
  rereading, and don't differ much from each other. "A model wrote my cards" is not, by itself, a
  learning problem.
- But LLM text uses a **measurably narrower vocabulary and simpler syntax** than human writing —
  humans use roughly twice as many distinct lexical entries.

Which points somewhere precise: **the glosses are fine; the example sentences are the weak link.**
They will be grammatical, correct, and bland — textbook Spanish with safe collocations, not how
anyone actually speaks. That is exactly the gap the corpus fills, and it is why §06 is in v1 rather
than deferred.

> ### THE HIGHEST-LEVERAGE CHANGE TO YOUR EXISTING PIPELINE
> **Pass the Wiktextract sense inventory and 2–3 real attestations into the generation prompt as
> grounding.**
>
> That demotes the model from *knowledge source* to *selector and formatter*, where hallucination
> risk on this kind of task is close to zero. It also fixes the failure you can't currently see: a
> model hands you the two obvious meanings of `picar` and silently drops five others. Wiktionary has
> them all.

### Where generation runs

> ### DECISION
> **Media and article generation run on the Mac. The server only stores and serves the results.**
>
> **Because** your Mac has MFLUX/MLX and you have already built image-provider benchmarking and
> ranking in this repo. A NAS or small VPS should never be asked to run diffusion. This keeps
> `src/vocabgen/` as a local worker that talks to the API — not a service you deploy — and keeps the
> deployed server to one small PocketBase container plus the corpus service.

The existing provider-factory pattern survives intact. What changes is only the edges: input comes
from `captureQueue` instead of a markdown inbox, and output is written to the API instead of to
topic files. Caching moves from directory-keyed to content-hash-keyed rows, which you are most of
the way to already.

---

## §08 · Anki loop

### Let FSRS tell you what's hard; don't rely on discipline

The gear icon you noticed is Anki's More menu: Flag (seven colours, `Ctrl+1..7` during review), Mark
(adds a `marked` tag), Suspend, Bury, Set Due Date, Forget, Delete Note. All of it is readable
through AnkiConnect — `findCards`, `cardsInfo`, `notesInfo`, `getReviewsOfCards`.

But manual marking is the weaker signal, because it depends on you remembering to do it. Since FSRS,
Anki maintains a memory state per card — **stability** (days until recall drops to 90%),
**difficulty**, and **retrievability** — exposed as `card.fsrs_memory_state` and searchable with
`prop:s>` / `prop:d>`.

**Signals pulled back into the core**

| Signal | Source | Effect on the lexeme |
|---|---|---|
| **Learned** | `stability > 365d` | status → `learned`, retire from active rotation |
| **Struggling** | high `difficulty` / `lapses` | **Gates expensive treatment** — custom images, comics, extra clips |
| **Explicit "I know this"** | green flag or suspend | status → `learned`, overriding FSRS |
| **Explicit "wrong card"** | red flag | Back to `inbox` for regeneration |
| **Never scheduled** | card absent | Reveals drift between core and deck |

Your instinct to spend the image budget only on hard words was right — and FSRS hands you that list
for free, with no marking discipline required.

> **THE DETAIL THAT SAVES YOU A SILENT DATA LOSS**
> Put the lexeme UUID in a dedicated hidden field on every Anki note. Do **not** rely on
> deterministic GUIDs for the join. GUIDs derive from content, so the day you improve a card template
> or fix a typo, your mapping breaks — quietly, and after the fact. An explicit id survives every
> edit, template change, and re-import.

Move off `.apkg` generation to `addNotes` / `updateNoteFields` for the steady state, as you planned.
Keep `.apkg` export for bootstrapping a new device and as a disaster-recovery path — it costs you
nothing to keep and it is the only export that works when AnkiConnect isn't running.

---

## §09 · Learning

### Six ways to learn a word, ranked by what they return

**01 · Production with LLM grading**
Your own instinct, and the best-supported one. Recognition — "does *desmayarse* mean to faint?" — is
far easier than production, and recognition is most of what a default Anki card tests. An LLM grader
is the genuinely new capability: it judges *meaning*, accepts valid alternatives an exact-match would
reject, and flags "grammatical, but no native says this." **Design note:** have it emit an
Anki-compatible rating and feed that back, or it's a fun toy disconnected from your scheduler.

**02 · Narrow reading — short generated texts using your due words**
Text-only, so cheap. Teaches collocation and register, which is precisely where isolated cards fail,
and where blandness hurts least because the point is repetition in context. Higher retention per
pound than comics.

**03 · Audio-first review**
Kokoro is already wired in. Generate a listening track of due words in sentences for walking or
commuting. Converts dead time into study time — and listening is usually the weakest skill for
someone who learns from written notes, which, judging by your Obsidian files, is you.

**04 · Clip review as a first-class session**
"Ten clips of your due words" is a legitimate review mode, not a decoration on a card. It is the only
mode that shows real register, real speed, and real regional variation.

**05 · Comics, manga, illustrated stories — gated on difficulty**
Genuinely fun, and bizarre imagery is well-supported as a mnemonic for *stubborn* items. But it's the
most expensive per word and the weakest per pound in general. Gate it on FSRS difficulty and it
becomes excellent; run it across the whole deck and it becomes a bill.

**06 · Collocations over synonym clusters**
When exploring outward from a word, prefer "words that appear *with* this word" over "words that mean
the same." Teaching close synonyms together risks interference — learners blend them. `desmayarse` +
`mareo` + `perder el conocimiento` in one scene is good; five near-identical words for "sad" in one
session is not.

> ### ANTI-RECOMMENDATION
> **Do not write your own spaced-repetition scheduler.**
>
> Anki with FSRS beats anything either of us would build, and every mode above should *report into*
> it rather than compete with it. The one thing worth building yourself is the queue that decides
> *which mode* a due word gets today.

---

## §10 · Obsidian

### Export only, and one honest import

> ### DECISION
> **The database is the source of truth. Obsidian receives a generated, read-only export.**
>
> **Because** reconciling free-form markdown against a structured store is a swamp, and it is
> precisely the coupling you'd be building this to escape. One-directional export keeps Obsidian
> useful for reading, linking and search without making it a second half-truth.

The import runs once. Your twelve Spanish topic files are regular enough to parse deterministically —
the `##### **word** emoji` / `*gloss*` / `> example` shape holds throughout, and topic comes from the
filename. The English file needs LLM-assisted parsing because it is genuinely heterogeneous: Russian
glosses, English-only definitions, multi-line quotes, occasional prose asides about usage. Route it
through `captureQueue` and review it in the inbox rather than trusting a one-shot conversion.

Two things to decide during import rather than after: the 387-entry *Misc* file wants re-topicking
now that topics are many-per-word, and there are exact duplicates already in your data
(`desmayarse` appears twice in *Health* alone) that the dedup pass should catch.

---

## §11 · Build order

### What lands in v1

**1 · Schema and import**
All ~940 Spanish entries and the English file into the database, attestations preserved, multilingual
from the first migration. Until the data is in, everything else is speculation.

**2 · Sync core**
Ported from Calorie Logger — tombstones, revision cursor, `datasetId` guard, schema-version refusal.
Re-derive only the merge order.

**3 · Capture and inbox review**
Share target, iOS Shortcut, bookmarklet; `clean_vocab.py` as the worker behind it. **The system earns
its keep here**, before a single flashcard exists.

**4 · Anki via AnkiConnect**
Content out, FSRS state in. Hidden UUID field. One deck per language.

**5 · Dictionary grounding**
Wiktextract ingest plus grounded generation. Raises quality across every downstream consumer at once.

**6 · Corpus and clips**
Harvest, cue merging, lemmatized index, embedded playback. The biggest build and the most
differentiated.

`──────────────────── end of v1 ────────────────────`

**7 · Tutor, narrow reading, audio, comics**
All consumers of a core that exists by then, and can arrive in any order — driven by which one you
actually miss.

### Explicitly out of scope for v1

- **Grammar.** You said it yourself, and you were right — it's a different data model and a different
  learning mode. Don't let it in.
- **Multi-user, sharing, publishing.** This is a personal tool. Registration stays closed, as in
  Calorie Logger.
- **A reader.** Lute already does reading-based acquisition well. Capture from wherever you already
  read instead.
- **Chinese corpus channels.** The Chinese *schema* lands in v1; the harvest can wait until you're
  actually studying it.

---

## §12 · Prior art

### What exists, and why none of it is this

| Project | What it is | Why not | Worth stealing |
|---|---|---|---|
| [VocabSieve](https://github.com/FreeLanguageTools/vocabsieve) | Sentence mining → Anki. Local StarDict/MDX/DSL dictionaries, lemmatization, frequency lists, EPUB reader. | Desktop Qt. No sync, no phone, no LLM, no server. Anki is the only output. | **Its dictionary-format parsers** — the best prior art you'll find. |
| [Lute v3](https://github.com/LuteOrg/lute-v3) | Self-hosted Flask. Learn by reading; per-word status New → Known; multi-word and parent terms. | Reading-centric — vocabulary is a byproduct of imported texts, not a curated list you own. Online dictionaries only. | Its multi-word term handling and status model. |
| [anki-llm](https://github.com/raine/anki-llm) | CLI/TUI for bulk LLM processing of Anki notes; a JSON-oriented AnkiConnect wrapper. | A tool *for* Anki, not a vocabulary store. No durable core. | Its AnkiConnect usage as a reference. |
| [playphrase](https://github.com/kelciour/playphrase) | Self-hosted subtitle search that plays the matching video fragment. | Local media files, not embedded YouTube. | Proof the clip feature is a solved shape. |
| [Obsidian → Anki](https://github.com/ObsidianToAnki/Obsidian_to_Anki) family | Markdown → Anki, some LLM-assisted. | One-directional pipes — exactly the linear model you've outgrown. | Nothing. |

> **VERDICT**
> Build it — not because nothing exists, but because the distinctive part (a synced,
> offline-capable, personally-curated lexeme store as the *system of record*, with pluggable
> consumers) is precisely what nobody has built. Everyone else treats the word list as scaffolding
> for their one output, so adopting any of them means adopting their centre of gravity.

---

## §13 · Open

### Still open

**Meilisearch or SQLite FTS5?**
Genuinely a preference at your scale (§06). One container and real search-ops experience, versus zero
operational surface and one fewer backup.

**Does the corpus service live in the same repo?**
Argument for: one deploy script, as with Calorie Logger. Argument against: it has a wholly different
lifecycle, and separating it makes "regenerable" structurally true rather than merely intended.

**How much of the English file survives import?**
~700 lines of genuinely messy notes. A judgement call on whether to import everything into `inbox`
and triage over weeks, or import only entries with an attestation and archive the rest as a raw note.

**Is the review UI in Acervo or in Anki?**
Anki is a better scheduler; a web UI is a better place for LLM grading and clip playback. Likely both
— but which one owns the daily session should be decided before you build either.

**Sense-level or lexeme-level cards?**
Your `ArticleExtended` already generates one Anki note per meaning. Sense-level is more correct and
more cards; lexeme-level is fewer reviews and blurs polysemy. Affects the study-state join.

---

*Acervo · design document · Rev. A · Multilingual from v1 · corpus index in v1*
