# Acervo · design, being split

> This file is being split into topic documents; [`README.md`](README.md) is the map. What remains
> here has not moved yet.

**Design document · Rev. E · 29 Aug 2026 · V1 scope agreed · synchronization decided**

> *acervo* — *m.* — the body of words a person actually holds — *working name, rename freely*

A self-hosted, offline-capable store for the words *you personally chose to learn*, in every
language you are learning — and a set of consumers that turn it into study material: Anki, a corpus
of real spoken usage, generated reading, an LLM tutor.

---

## §05 · Capture

### One endpoint, several thin transports

Capture is make-or-break: past a few seconds you stop doing it, and every other feature here is
moot. But the shape follows from one observation — **review is non-negotiable, so every route ends
in the app anyway.** The only real question is whether capture also routes through a *third* app
first.

> ### DECISION
> **Build one ingest endpoint. Every capture path is a thin client against it.**
>
> **Because** the transports have wildly different lifespans and platform constraints, while what
> they submit is identical: some text, optionally a surrounding sentence, optionally a URL and
> title. Putting the intelligence in the endpoint means adding a transport is an afternoon, and
> losing one costs nothing.

| Order | Transport | Platform | Why here |
|---|---|---|---|
| 1 | **Manual add, in-app** | all | Must exist regardless — a word you *heard* has no source to share from. The floor. |
| 2 | **Browser extension** | macOS desktop | The highest-quality capture available anywhere, and the only one with no selection dilemma. |
| 3 | **iOS Shortcut** → POST → open app | iPhone, iPad | One gesture from the share sheet that *ends in the review screen*. |
| 4 | **Web Share Target** | Android phone, Android tablet | Direct, native-feeling, cheap once the endpoint exists. |
| 5 | info-triage `lang` route | anywhere | **Optional backfill.** Useful where Acervo isn't installed. Not the path. |

**§05 REVISED — row 3 does not exist as described.** An iOS Shortcut cannot end in Acervo's review
screen: iOS has no deep link into an installed home-screen web app, the installed app's storage is
separate from Safari's so a URL opens a different, signed-out copy, and iOS offers a web app no share
target at all (WebKit bug 194593). What a Shortcut *can* do is post and walk away into the Inbox, or
resolve, confirm in a Shortcuts menu, then post. The full survey of transports per device, with the
experiments that decide between them, is [`plans/capture-transports.md`](plans/capture-transports.md).
Photo capture has since become a transport of its own ([`photo-capture.md`](features/photo-capture.md)).

### Why info-triage is demoted

Rev. B made the `lang` route the primary path on the grounds that it already existed. That was the
wrong instinct: reuse is a virtue only when the shapes match, and they don't.

info-triage is asynchronous **by necessity** — deciding where information belongs requires context
you lack at capture time. Vocabulary's decision is immediate. Routing an immediate thing through
infrastructure built for deferral adds a hop that buys nothing at the end of it: you still switch to
Acervo to review, and now two systems can fail between you and a word you wanted to keep.

The specific correction: **an iOS Shortcut beats the Telegram route on its own ground.** A Shortcut
can POST *and then open a URL*, so it is one gesture from the same share sheet that lands you on the
review screen. Same reach, one hop instead of two.

The route may still earn a place as a future capture transport. It does not create a reason to add a
legacy importer or a second persistence model.

### The selection dilemma, and the one transport that dissolves it

A share sheet carries one selection: the word *or* the sentence, never both.

**The browser extension has no such limit.** It reads the DOM *around* your selection, so one click
yields the word, its surrounding sentence, the URL and the page title — nothing to work around. That
is why it ranks above the mobile transports despite covering only the desktop.

For the share-sheet transports, the rule is: **share the sentence, pick the word in the app.** The
review screen renders the captured sentence with every token tappable; one tap sets the headword,
tap-drag across tokens captures a multi-word expression. That tap *is* the approve gesture, so it
costs nothing extra.

| Situation | Share | Then |
|---|---|---|
| Just want the word | the word | Nothing to pick. No attestation, and that is fine. |
| Word **and** context | the sentence | Tap the word. Attestation free. |
| Cannot select — WhatsApp, an image, a subtitle | **a screenshot** | A vision model reads it and proposes the sentence plus candidate words. You tap. |

On the URL: you would rarely click it, but `sourceTitle` is what makes an attestation memorable years
later — *"the Cortázar story"*, *"that Reuters piece"*. The extension gets both free; a
clipboard-and-hotkey route gets neither. Clipboard is a fine floor, not the plan.

**Voice** stays unbuilt for now. Phone and tablet dictation is mediocre but free, and building for it
before knowing you need it is speculative.

### Capture is online by nature

Worth stating plainly, because it settles what §04's online-only writes actually cost: **nothing
here.** Capture submits a word or a sentence and gets back a built article, and building it means
calling an LLM and consulting the corpus — both of which live on the server. There was never a
version of capture that worked on a plane. The rule that a write needs the network takes away a
capability capture did not have.

What you submit is small by design: one word, or one sentence containing it. Everything else is
derived.

> ### DECISION
> **Capture merges into the lexeme you already have. It does not create a second article for a word
> already in the store.**
>
> **Because** the same word arrives repeatedly — that is what reading a lot looks like — and the
> second encounter is usually *better* than the first: a sharper sentence, a sense you had not met.
> Treating it as a new entry turns the store into a pile of near-duplicates within months.
>
> **So a repeat capture is an addition, not an entry**: the new sentence becomes another attestation
> on the existing lexeme, and an unmet meaning becomes another sense. `suppressed` (§03) is what
> keeps a *rejected* word from arriving forever, and dedup is what keeps an *accepted* one from
> arriving twice.

This is also the first real consumer of the write route in §04: a merge is an ordinary batch of
records against an existing lexeme, at its current revision.

### Immediate processing, deferred approval

The transport may be fire-and-forget; the **processing is not**. Senses, glosses and an example are
fully determined by the word plus the sentence, and nothing you learn next week changes what the
entry should say — so there is no reason to defer it.

```
captured → processing → review → active            (you added it: you read it before saving)
captured → processing → inbox  → active            (it arrived unattended: an ingestion script)
                          │
                          └── suppressed
```

By the time you open the app the article is built and waiting. Review is reading the rendered entry
and saving it, not a triage session, and what you have read is not marked as unread afterwards: an
entry you saved from the Add view is an ordinary word. The Inbox holds only what arrived without
anyone reading it — which is why **an imported bundle is filed rather than piled up there**: a file
is chosen from a picker and applied on a button press, so nothing in it arrived unattended. Only
`inbox` is rewritten on the way in; `learned`, `retired` and `suppressed` are curation the owner did
and a bundle is a backup of it. And because the Inbox is a room a few hundred words can land in at
once, it has a **door**: **File it** on an article, and **File all** on the tab, both writing
`status: active` through the ordinary graph write. Without one the only way out was editing a word's
YAML, once per word. Review is of the whole entry — a missed sense is the real risk, not one example —
so there is no approval flag on individual records. Add **"regenerate with a note"** — a free-text nudge that re-runs generation in
seconds. Small feature, large effect on whether you trust the automatic path.

> **WHY "GIVE AN LLM AN ARTICLE AND ASK FOR THE INTERESTING WORDS" FAILED**
> The model is estimating *the average learner's* gaps, and you are not average — a Russian native
> with strong English and idiosyncratic holes from an unusual reading diet. No prompt fixes this; the
> missing information is not in the article.
>
> It is also the one feature only this app can eventually have. Once the core holds a couple of
> thousand of your lexemes, plus what you suppressed, plus FSRS difficulty, "which words here are new
> to me" becomes a set difference against your own store rather than a guess. **v2, not v1** — but it
> is the payoff that makes a curated store worth keeping.

---

## §06 · Article chat and LLM editing

### The article is the thing you argue with

Capture builds an entry. What is missing is everything that happens *after* you read it and find it
not quite right — you want another example, or the definition explained further, or the one thing no
dictionary gives you: **how this word differs from the neighbouring one you keep confusing it with.**

The workaround needs no software: copy the article into a chat, ask, paste the result back. It works,
and it is worth naming why it is nonetheless the wrong shape. The model in that chat does not know
the schema, so what comes back is prose you must re-key by hand. It does not know the rest of your
store, so it cannot say "you already have `mareo`, and here is the contrast." And the round trip is
long enough that you stop doing it.

> ### DECISION
> **Chat lives inside the article, and its output is a proposed revision of that record.**
>
> **Because** the value is entirely in the conditioning. A model handed the canonical record, its
> schema, and the account's related lexemes answers a different class of question than one handed a
> block of text — and can return something structurally valid rather than something you transcribe.

### How it fits what already exists

- **The prompt is assembled server-side.** The PWA sends the lexeme id and the question; the server
  attaches the record, the schema and the grounding (§09), and holds the credentials. Nothing about
  the LLM leaks into the client, and every transport gets the same behaviour for free.
- **A proposed change is shown, never applied.** The model answers in prose *and*, when the answer
  implies an edit, offers it: *"Would you like me to add that contrast to the notes?"* You approve.
- **Approval is an ordinary write.** It goes through §04's route, at the record's current revision,
  and it is refused if the entry moved underneath you. No second write path, no second storage
  format, and a chat-driven edit is indistinguishable downstream from one you typed.
- **Provenance survives it.** `editedBy` and the `modelId` already on generated rows record that a
  model made the change, which is what keeps §01's mass-regeneration promise honest.

> **THIS IS WHY MANUAL YAML EDITING STAYS**
> The projection in §03 looked like a nice-to-have when the expectation was that entries are rarely
> edited by hand — and that expectation is right. It earns its place for a different reason: it is
> the review surface for what the model proposes and the escape hatch for the case the chat gets
> wrong. A generated store you cannot open and correct directly is a store you have to trust
> blindly.

### Where the line falls

Chat is a **consumer of the core**, like every other renderer in §01 — it reads records and proposes
records. It does not get its own storage, its own article format, or a private history that matters:
the transcript is a convenience, and losing it costs nothing, which is precisely the test §01 sets
for whether something belongs in the core. It does not.

**Built.** The working design is [`features/article-chat.md`](features/article-chat.md), which settled the
four things this section left open: how the model returns an edit, how the edit is shown, where the
conversation sits on a phone, and which places in the interface open one. Two decisions above were
revised there, and both are marked **§06 REVISED** in that document:

- **The document is assembled on the device, not the server.** "The PWA sends the lexeme id and the
  server attaches the record" cannot hold: `web/src/yaml.ts` is the only place the projection is
  understood, and a server-side serialiser would be a second implementation of it, drifting from the
  first the moment a field is added. The device sends the document it already has. Nothing is lost —
  the server still holds the credentials, still owns the prompt, and still writes nothing.
- **A repeat capture can now be folded in.** §05's duplicate branch used to stop and say so, because
  merging needed the article conversation. It has one now, and it needs no extra model call: resolve
  has already run, so the learner's own sentences are in hand, separated from anything a dictionary
  supplied. The capture response carries what could be added, and the interface opens the stored
  article and asks one ordinary question.

The rest of this section stands. It is also why the write route is shaped the way §04 shapes it: an
interactive, confirmed, revision-checked batch against one article.

---

## §07 · Corpus · v1

**§07 REVISED — the corpus is its own project, and Acervo only chooses from it.** Harvesting,
segmenting, lemmatising and indexing became
[`spoken-usage-retrieval`](https://github.com/anton-dergunov/spoken-usage-retrieval), a separate
repository that Acervo runs as one pinned service. It answered the engine question with SQLite, not
Meilisearch, and reversed the authored-only rule below: measured there, YouTube's automatic captions
are more verbatim and better aligned to the speech than creator-authored ones, and most of the
corpus is automatic. What Acervo does — one search and one model call per saved word, at most one
clip per sense, stored as an ordinary example — is [`spoken-clips.md`](features/spoken-clips.md). The rest of
this section is the original reasoning, kept because the inversion it starts from still holds.

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
| 4 | **Wiktextract** | Wiktionary as JSONL — senses, IPA, inflections, domains. The *grounding* source (§09) more than an example source. |
| 5 | **Generated** | The fallback, not the default. Correct, and blander than any of the above — see §09. |

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
| **Voice** | WaveNet for words, a Gemini voice for sentences — chosen in Settings (§04 "Media") | same | same |
| **Corpus channels** | Dreaming Spanish, Easy Spanish, DW Español, TED es, RTVE | TED, plus what you already read | deferred to v1.1 |
| **Anki deck** | `Spanish::Vocabulary` | `English::Vocabulary` | `Chinese::Vocabulary` |

> **WHAT MULTILINGUAL ACTUALLY COSTS**
> Almost nothing structurally — `language` on every row and a config block per language. The real
> cost is three specific things: **Chinese needs segmentation** before anything else works, **the
> reading field** must exist in the initial schema, and **collation differs per language**, so
> sorting is a per-language function rather than a global one. Retrofitting any of those later is
> genuinely painful, which is why they belong in v1 even though Spanish is 90% of your usage today.

### Chinese: the schema, not the subsystem

The hesitation is right, and the line falls between *the language existing* and *modelling how the
language works*.

Three things about Chinese genuinely break the assumptions above:

1. **The unit of learning is not the word.** It is component ↔ character ↔ word — three levels. 妈妈
   is a word made of a character made of components. Spanish has one level. Modelling this properly
   needs a lexeme→lexeme composition relation.
2. **Tone is not decoration.** mā / má / mǎ / mà are four different words. Store numbered (`ma1`),
   render with diacritics.
3. **Traditional and Simplified** are a variant axis, not a dialect.

> ### DECISION
> **v1 ships the Chinese schema — `language`, `reading`, its config block — and none of the Chinese
> subsystem.** No composition relation, no component modelling, no measure words, no corpus harvest.
>
> **Because** the first group costs nothing now and is painful to retrofit, while character
> decomposition is not a column, it is a subsystem. Building it speculatively for a language you have
> not started is the scope creep that kills a v1 — and by the time you start, you will have opinions
> from using the thing.

> **ON THE HORSE THAT MEANS MOTHER**
> 妈 (mā, mother) = 女 (woman) + 马 (mǎ, horse). The horse is not there for meaning — it is there for
> **sound**. 女 gives the semantic category, 马 gives the pronunciation. This is a *phono-semantic
> compound*, and roughly **80%+ of Chinese characters are built this way**.
>
> The "no shared background" feeling is partly an artifact of learning characters as atomic
> pictures. They are not atomic. The anchor you get free in European languages — shared Latin and
> Greek roots — has a real analogue in Chinese; it just lives *inside* the character rather than
> across languages. Worth knowing before deciding the language is unlearnable by your usual method.

---

## §08 · External dictionaries

### Read them where they lie

A published dictionary belongs in the same application — looking a word up and keeping a word you
chose are the same gesture two seconds apart. It does **not** belong in the same storage.

> ### DECISION
> **External dictionaries are read-only files, read directly. They are never ingested into
> PocketBase and never enter the replica.**
>
> **Because** the whole justification for the core's shape — small enough to hold on every device,
> synced in full, backed up as though irreplaceable (§02) — is destroyed by a million entries you did
> not write and could re-download in an afternoon. Loading them into the relational store would be
> paying the core's costs for corpus-shaped data, which is the exact mistake §02 exists to prevent.

So: a thin reader over the downloaded dictionary file, exposing lookup and search behind the same
interface the personal store uses. No relational schema, no records, no revisions, no sync. The
`sourceKind`/provenance vocabulary already in §03 is enough to say where a shown entry came from.

**Offline availability is a file download, not replication.** The unit is "this dictionary is on this
device", chosen deliberately and stored whole — not per-entry caching and certainly not a second
replication protocol. Nothing about §04 changes.

### What they are, and are not

| | Personal store | External dictionary |
|---|---|---|
| Origin | Words you chose | Everything the compiler included |
| Editable | Yes — and via chat (§06) | **Never.** No YAML projection, no edit affordance |
| Storage | PocketBase + full replica | A file, read in place |
| Backed up | As irreplaceable (§17) | Re-downloaded |
| Carries | Attestations, clips, images, Anki state | Definitions |

An external entry is a **starting point, not an entry**: promoting one creates an ordinary Acervo
lexeme, at which point it gains everything the personal store adds — the sentence you actually met it
in, the clip, the image, the FSRS history. That promotion is a normal write through §04, and dedup
applies exactly as in §05.

This is also the honest answer to why the personal store exists at all next to a dictionary that
already defines every word: the dictionary knows the language, and the store knows *you*.

**Out of scope for this iteration.**

---

## §09 · Generation & orchestration

### Ground the model, and it stops being a knowledge source

You asked whether anyone has benchmarked LLM-written vocabulary entries against human ones. Not
directly, as far as I can find — no study compares generated bilingual dictionary entries to
lexicographer-written ones. What the adjacent literature says is more useful than a benchmark would
have been:

- In educational content generation, GPT-4-class models produce material of comparable quality to
  human experts, while weaker models are measurably worse — consistent with your own experience.
- Flashcard *authorship* barely affects retention: self-made and other-made cards both beat
  rereading, and do not differ much from each other. "A model wrote my cards" is not, by itself, a
  learning problem.
- But LLM text uses a **measurably narrower vocabulary and simpler syntax** than human writing —
  humans use roughly twice as many distinct lexical entries.

Which points somewhere precise: **the glosses are fine; the example sentences are the weak link.**
They will be grammatical, correct and bland — textbook Spanish with safe collocations, not how
anyone actually speaks. That is exactly the gap the corpus fills, and it is why §07 is in v1.

> ### THE HIGHEST-LEVERAGE CHANGE TO THE EXISTING PIPELINE
> **Pass the Wiktextract sense inventory and 2–3 real attestations into the generation prompt as
> grounding.**
>
> That demotes the model from *knowledge source* to *selector and formatter*, where hallucination
> risk on this kind of task is close to zero. It also fixes the failure you cannot currently see: a
> model hands you the two obvious meanings of `picar` and silently drops five others. Wiktionary has
> them all.

### Image prompts are their own stage

Prompts come off the validated vocabulary graph and get their own LLM call against the finished entry.

> ### DECISION
> **Generate the article first. Generate its image prompts second, from the validated article.**
>
> **Because** the two calls have competing objectives: article generation optimises for lexical
> accuracy, prompt generation for visual specificity, and today they share one prompt and one output
> budget — so the visual half loses. Splitting also means you can regenerate every prompt with a
> better model **without touching a single gloss**, which today is impossible: changing visual style
> means re-running article generation and risking drift in the part you actually care about.

**Batch within an article, never across articles.** One call covering all meanings gives the model
cross-meaning context so it can deliberately *differentiate* the images — which is the entire point
of per-meaning images. Batching across articles loses that and makes retries coarse-grained.

**Style variety is pedagogical, not decorative.** Visual sameness across 900 cards destroys
distinctiveness, and distinctiveness is the only reason the images aid recall at all.

```yaml
image:
  prompt_model: gemini-flash-latest
  styles:
    - { id: flat-vector,    weight: 3, brief: "flat vector, bold shapes, limited palette, no text" }
    - { id: storybook,      weight: 2, brief: "soft storybook gouache, warm light, no text" }
    - { id: retro-futurist, weight: 1, brief: "1970s sci-fi paperback, muted print palette, no text" }
    - { id: cartoon-robots, weight: 1, brief: "friendly retro robots acting the scene, no text" }
  selection: weighted_random
  seed_from: lexeme_id        # same word keeps its look across regenerations
```

Seeding from the lexeme id matters: the deck does not visually reshuffle every time you regenerate.

### Resolution

The 192–384 px figure in `docs/research/image-generation-research.md` reads as though the image were a small
inline anchor. For a card illustration on the devices actually used it is about a quarter of what is
needed:

| Device | Logical width | Scale | Image at ~90% width |
|---|---|---|---|
| 11" tablet | ~834 pt | 2× | **~1400 device px** |
| ~7" phone | ~412 pt | 2.6–3.5× | **~960–1300 device px** |

> ### DECISION
> **Master at 1024×1024 WebP; cap the display width at ~512 pt.**
>
> 1024 is the native output of FLUX and Gemini image models, so nothing is upscaled and nothing
> generated is thrown away. Capping the layout is what makes 1024 *sufficient* rather than merely
> better — pixel-exact at 2× on the tablet, and ~2.8× on a phone where the layout limits width to
> ~370 pt anyway. Letting the image go full-bleed on an 11" tablet would demand ~1536 and upscaling.

Consequences:

- **The current settings actively hurt quality.** `config/defaults.yaml` sets `width: 384,
  height: 384` and `src/vocabgen/vision/stable_diffusion.py` hardcodes the same, on top of an SD1.5
  checkpoint trained at 512. Generating near or below native and then discarding the rest is the
  worst of both. Moving off SD1.5 is already the research doc's recommendation; this is one more
  reason.
- **Derive variants from one master**, never generate twice: 1024 for the app, 768 (~70 KB) embedded
  in Anki if deck size bites, 256 for list thumbnails.
- **Deck size is the real tradeoff.** ~110 KB per 1024 WebP × ~2700 images ≈ 300 MB of media. Fine
  over AnkiConnect on your own machine; check it against AnkiWeb's media quota before relying on
  sync. Verify WebP renders on AnkiMobile before committing several thousand files to it.

### Where the work runs

[`architecture/jobs.md`](architecture/jobs.md): one server process, a durable job per piece of work,
and what the interface shows while it runs.

### Provider chain

Per kind of work — text, pictures, voices, OCR — the owner chooses an ordered chain of (provider,
model) pairs in Settings, and a call walks it, falling through on a transient failure and never on a
misconfiguration. The mechanism is `src/acervo/models/` and the tracked catalogue; today's rows lean
on Google while a trial lasts, and nothing is designed as if that will continue.

> **`none` IS A SUCCESSFUL OUTCOME.** A lexeme with no image is complete (§01). This is what makes
> enrichment safe to be lazy about: if images were required, the queue would be a critical path and
> a provider's outage a hole in the vocabulary. The emoji already carries a visual anchor at zero
> cost.

---

## §10 · Anki loop

### The desktop is not in this loop

Study happens on an 11" tablet, essentially always. That is a health constraint rather than a
preference — so a mechanism that requires Anki Desktop running is the wrong primary, however
convenient it looks.

> ### DECISION
> **Self-host the Anki sync server on the NAS. Update the collection with a headless robot client.
> AnkiConnect is a fallback, not the design.**
>
> Anki has shipped a built-in sync server since **2.1.57** (Python) with a Rust implementation from
> **2.1.66+**, and maintained Docker images exist. Default port 27701; the media sync URL is the same
> base URL with `/msync` appended. AnkiDroid points at it under Settings → Advanced → Custom sync
> server, AnkiMobile under Settings → Synchronization → Custom Sync Server. The email field at login
> is cosmetic — for a self-hosted server it is simply the username you configured.

This solves both open problems at once. **Media quota disappears** — it is your disk, and the real
limit becomes tablet storage, where 300 MB is nothing. **The desktop leaves the loop entirely.**

### The robot client

Do not write into the sync server's collection file — that fights the server for the same SQLite.
Run a headless collection on the NAS that behaves as **just another sync client**:

```text
Prefect flow (NAS)
  ├─ open local collection        anki.collection.Collection(path)
  ├─ sync DOWN from your server   col.sync_collection(auth)
  ├─ add / update notes           col.add_note(), col.update_note()
  ├─ read back FSRS state         revlog + card data → studyState
  └─ sync UP                      col.sync_collection(auth)
```

No locking hacks and no stopping services, because from the server's perspective this is
indistinguishable from the iPad syncing. Conflict resolution is Anki's own. `anki` pylib exposes
what is needed: `sync_login()` for a `SyncAuth`, then `sync_collection()`.

| Machine | Role |
|---|---|
| **NAS** | Sync server, robot client, everything else. Always on. |
| **Tablet** | Study. The only device touched. |
| **Mac** | Image generation only, idle-gated. |

This collapses §09's Mac pools to one: `mac-available` disappears, because Anki no longer needs the
laptop at all.

**Four risks to build for:**

1. **Sync protocol is version-locked.** pylib and the sync server must match. Both live on the NAS —
   pin them together and upgrade as a pair. This is the thing most likely to break silently on an
   unattended update.
2. **"Requires full sync" is dangerous for a robot.** A schema or deck-config change forces a full
   upload or download, and a robot that auto-resolves could push a stale collection over real
   progress on the tablet. **Fail the flow loudly instead** and decide by hand.
3. **Always sync down before mutating; never force-upload.** Mid-review edits merge correctly only if
   the robot behaves as a client rather than an authority.
4. **Reachability.** The tablet needs the NAS from outside the house. Tailscale already covers this
   for Calorie Logger; the sync server belongs behind it rather than exposed.

One bonus: the collection now lives on the NAS, so it falls under §17 like everything else. **Review
history is as irreplaceable as the vocabulary** — years of FSRS state cannot be regenerated.

### Decks

One deck per language is the default. Topic becomes a **tag**, not a deck, because per-topic decks
multiply scheduling configuration — each deck carries its own daily limits, which fragments the queue
for no benefit. The config supports splitting anyway, reusing the existing `%topic` convention:

```yaml
anki_deck: "Spanish::Vocabulary"   # default
anki_deck: "Spanish::%topic"       # split, same placeholder as output_pattern
```

> **SPLITTING DECKS DOES NOT REDUCE MEDIA SIZE.** Every deck in one collection shares a single
> `collection.media` folder; the deck is only a scheduling container. Ten decks or one, the media
> total is identical. What reduces it: smaller images, fewer images per note, or self-hosting so the
> quota question never arises — which §10 now does.

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

> **STUDY STATE IS READ-ONLY IN THE APP**
> It flows *in* — §01's first invariant, applied to the one table Anki owns. Nothing in the interface
> edits it, and it is deliberately absent from the YAML projection: reps, lapses and stability are a
> report from the scheduler, not a field you may correct. The one place a review outcome changes the
> core is the mapping above, where it moves the lexeme's `status`.

> **THE DETAIL THAT SAVES YOU A SILENT DATA LOSS**
> Put the lexeme record ID in a dedicated hidden field on every Anki note. Do **not** rely on
> deterministic GUIDs for the join. GUIDs derive from content, so the day you improve a card template
> or fix a typo, your mapping breaks — quietly, and after the fact. An explicit id survives every
> edit, template change, and re-import.

The same fields are readable from the robot client without AnkiConnect: `.anki2` is SQLite, and the
revlog and per-card FSRS state can be read directly once the collection has synced down.

Keep `.apkg` export for bootstrapping and as a disaster-recovery path — it costs nothing and it is
the only export that works when nothing else does.

---

## §11 · Learning

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
Generate a listening track of due words in sentences for walking or commuting. Converts dead time
into study time — and listening is usually the weakest skill for someone who learns from written
notes, which, judging by your Obsidian files, is you.

**Built, in two shapes.** A *loop* is a track of chosen words, each said and then glossed over a
music bed, played like a record with the translation held back until it has been spoken; a *story*
is a short illustrated text read aloud in one voice. Neither picks *due* words yet — both take the
words on screen or the ones marked by hand.

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

## §12 · Obsidian

### Export only

> ### DECISION
> **The database is the source of truth. Obsidian receives a generated, read-only export.**
>
> **Because** reconciling free-form markdown against a structured store is a swamp, and it is
> precisely the coupling you'd be building this to escape. One-directional export keeps Obsidian
> useful for reading, linking and search without making it a second half-truth.

There is deliberately no import bridge from historical Markdown or JSON formats. Existing data is
disposable during the greenfield phase; canonical records are created through the current model.

**What ships.** Settings ▸ Data exports a zip built entirely from the local replica — so it works
with the server unreachable, like every other read. Inside, a manifest, the vocabulary and topic
records, one YAML document per word under its language directory, and the markdown mirror under
`markdown/`. The markdown files are named `Spanish vocab - Food.md`: the language belongs in the
name and not only in the directory, because Obsidian is searched by note name and two languages with
a Technology topic would otherwise be two notes called Technology, neither distinguishable from an
ordinary note about technology. A word is filed under each of its topics, an unfiled one under
`Misc`, and one still waiting under `Inbox`, mirroring what the rail does.

The entries are three lines at most — the word, its one-line gloss, and a sentence if one is worth
keeping — because the value of this file is that it can be *scanned*. Senses, notes and generated
examples stay in the article. Which sentence is worth keeping needs no new field: provenance is
already modelled, so an example is kept when its origin is the owner's own — `attestation` for one
they met, `manual` for one they wrote — and dropped when it was produced.

**Importing Acervo's own export is not that bridge.** A bundle is the current model, written by this
application, and it is read back through the same `parseArticle` and written through the same
`saveArticle` a typed document is. That is the §17 layer-0 rebuild path made real: export before a
schema change, import into the rebuilt server. A word already held is skipped, never overwritten —
an import must not cost curation done after the export — and every id is re-minted on the way in, so
a bundle carries no account with it and can be handed to someone else.

---

## §13 · Build order

### What lands in v1

**1 · Canonical schema and representative seed data**
PocketBase and IndexedDB share the same owner-scoped graph, with multilingual examples present from
the initial schema. The disposable demonstration seed makes the model inspectable without creating
an alternative data source.

**2 · Sync core**
The protocol in §04, directly over the Acervo graph: a server-assigned revision cursor, a delta pull,
an online-only write route with a revision precondition, tombstones, the dataset guard, and
schema-version refusal. Conflict *handling* mostly disappears rather than being built — that is the
point of making writes online-only.

**3a · Manual add and inbox review**
The floor, and it must exist regardless — a word you *heard* has no source to share from.
A provider-backed processing worker sits behind it. **The system earns its keep here**, before a single
flashcard exists.

**3b · Ingest endpoint and transports**
One endpoint, then thin clients against it in order of leverage: browser extension (macOS), iOS
Shortcut (iPhone and iPad), Web Share Target (Android phone and tablet). The tap-to-pick-the-word
review screen lands here. Sequenced *after* 3a deliberately: a fortnight of manual use tells you
which capture friction is real.

**4 · Anki via AnkiConnect**
Content out, FSRS state in. Hidden Acervo record-ID field. One deck per language.

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
- **The Chinese subsystem.** The schema lands in v1 (§07); composition, components, measure words
  and the corpus harvest wait until you actually start.
- **Voice capture.** Phone and tablet dictation is free and adequate. Revisit only if it annoys you.
- **"Extract the interesting words from this article."** Needs a populated core to work at all — v2.
- **Offline writing.** Reading works on a plane; saving does not, deliberately (§04). The fields a
  future offline mode would need are already on every row, so this is reversible — but nothing is
  built for it now.
- **External dictionaries** (§08) and **article chat** (§06). Both are designed, neither is v1.

---

## §14 · Prior art

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

## §15 · Open

### Still open

**Meilisearch or SQLite FTS5?** — *Answered elsewhere: SQLite.*
The corpus became its own project and made the choice there, with compact token positions rather
than an FTS index. Nothing in Acervo depends on it either way.

**Does the corpus service live in the same repo?** — *Answered: no.*
It is [`spoken-usage-retrieval`](https://github.com/anton-dergunov/spoken-usage-retrieval), its own
public repository with its own release cadence, and Acervo runs one pinned version of it as a
container beside the server. The argument against won: a research project whose index is
regenerable by definition should not share a release cycle with the thing holding irreplaceable
data, and separating them makes "regenerable" structurally true rather than merely intended. See
[`docs/features/spoken-clips.md`](features/spoken-clips.md).

**Is the review UI in Acervo or in Anki?**
Anki is a better scheduler; a web UI is a better place for LLM grading and clip playback. Likely both
— but which one owns the daily session should be decided before you build either.

**Sense-level or lexeme-level cards?**
Sense-level cards are more correct and produce more cards; lexeme-level cards mean fewer reviews
but blur polysemy. The choice affects the study-state join.

**Does WebP render everywhere you review?**
Fine on desktop and AnkiDroid; verify AnkiMobile before committing several thousand files (§09).

**How large should images actually be?**
Deferred pending measurement. Per-sense images stay — senses genuinely diverge, especially in
English, and one image per lexeme would misrepresent them. The open part is only the resolution and
the resulting media total, and self-hosting (§10) removes the quota pressure that made it urgent.

**Which git remote holds the export?**
A private repository somewhere you do not also host — the point of §17's second layer is that it
survives your own infrastructure. Worth deciding before the exporter is written, since the answer
affects whether it pushes over SSH or HTTPS.

---

## §16 · Current implementation

The §03 foundation is the only application model, and §04's protocol is now built on it:

- PocketBase owns locked, owner-scoped `vocabularies`, `topics`, `lexemes`, `senses`,
  `attestations`, `examples`, `image_prompts` and `study_states`, plus a `sync_state` row per owner
  that is never replicated. Accounts are administrator-created; the app API provides password login
  and token refresh.
- The `languages` block of §03 is owner data rather than a configuration file: a `vocabularies`
  record per language studied, carrying its definition language, its gloss languages and its
  presentation. It replicates like any other record, so the interface reads it offline and the
  generation prompts are assembled from it. A configured language appears in the switcher before it
  holds a single word, which is what makes a new vocabulary fillable at all. `reveal`, tokenizer,
  lemmatizer and TTS remain unbuilt and therefore unmodelled.
- IDs are generated offline in PocketBase's native 15-character format and stored unchanged in
  every relation and consumer manifest. `revision` is allocated by a save hook on every replicated
  collection, so the seeder, a future flow and the graph route all number their writes identically
  and none of them can produce a record no client would ever receive.
- Three authenticated, owner-scoped routes carry everything: `GET /graph?since=` returns the delta
  above a cursor with tombstones included, `POST /graph` applies a change set in one transaction
  and returns the canonical rows, and `POST /graph/reset` tombstones the account's words while
  retaining its vocabularies and topics. All three refuse
  a client whose `schemaVersion` differs. Generic collection access stays closed.
- A record written to the server states the revision it was edited from; a stale one is refused
  rather than merged, and an invalid record in a batch refuses the whole batch.
- TypeScript runtime validation enforces the same graph constraints as the server. The PWA and
  native macOS host hold an IndexedDB replica whose applied records, tombstones and cursor land in
  one transaction. A replica belonging to another account or schema version is discarded rather
  than converted; one whose `datasetId` no longer matches is *not* — synchronisation stops and the
  owner chooses, because that copy may be the most complete one left.
- The client polls every sixty seconds while visible, on focus, on regaining the network, and
  immediately after any write, single-flight throughout. A failed sync changes the status and
  nothing else; the interval is the retry.
- The vocabulary interface is the design in `design/ui-prototype/` rendered from real records: the
  topic rail, list, article, YAML projection and add sheet, on every platform the same web build
  serves. Reading is served entirely from the replica, so it opens and works with the server
  unreachable; a sync chip in the topbar says which of those two situations you are in, and
  Settings explains it, offers a manual sync, a re-download, and a typed-confirmation delete.
- A development seeder inserts a disposable, multilingual demonstration vocabulary into an
  explicitly selected account. PocketBase remains the durable store; the tracked seed definition is
  initialization material, not an alternative vocabulary database.
- The former Markdown cleaner, short/extended article storage classes, directory-backed caches and
  draft `.apkg` generator have been deleted, and the pending-write queue that anticipated offline
  writing has been deleted with them. No compatibility adapters or import transformers remain.
- LLM, TTS and vision providers remain reusable. The separate headless Anki robot remains a
  consumer and uses Acervo record IDs, but is not yet wired to the core.

- An entry is created and edited through the YAML projection, which is now read in both
  directions. Every record in the document carries its id, so a save is an exact diff rather than a
  guess: a record with an id is updated, one without is created, and one the document no longer
  mentions is tombstoned, with a removed sense taking its examples and prompts with it. Ids are
  never recycled through an edit, which is what keeps the Anki note join (§10), the image seed
  derived from the lexeme id (§09) and `createdAt` intact. The whole article is one batch through
  the ordinary write route, refused as a unit, and a refusal leaves both the replica and the draft
  untouched. The projection is lossless by test: every field a record carries is written, so
  nothing can be silently dropped by a round trip. Study state is written as comments, because the
  scheduler owns it.

- Capture (§05) is one authenticated route, `POST /graph`'s neighbour: submit text, get back an
  entry. Two model calls, assembled server-side from prompts the server holds. The first decides
  what the text is about — which word, which language, which of the sentences are the learner's,
  and, walking a file, how many leading lines that entry occupied. That answer is what makes the
  rest possible: a language with no vocabulary is refused before anything is generated, and a word
  the account already holds returns the entry it has rather than a near-duplicate. Only then does
  the second call write the article, choosing from the owner's real topics and glossing into the
  languages their vocabulary asks for.
- What comes back is a *proposal*, never a stored record. The interface renders it through the same
  YAML projection it renders a stored article with, and saves it through the same repository, the
  same diff and the same write route — so a generated entry and a typed one are indistinguishable
  downstream, and review is the ordinary editor rather than a second surface. The route will also
  apply what it built, for the transports that have no replica to diff against; that path assembles
  a change set and puts it through the same merge, so capture has no private way into the store.
  Everything lands in the Inbox, because review is non-negotiable.
- Provenance is carried by the model rather than a flag: the learner's own sentence is kept verbatim
  as an `attestation`, and the example drawn from it says so and names it. An example the model
  invented carries the model that wrote it instead. Both are created by one save, which is why a
  document that names no stored entry may carry ids its producer minted.
- Transports are thin by construction. A script walks a notes file into the Inbox one entry at a
  time, advancing by exactly what the server says it consumed, checkpointed outside the notes and
  leaving them untouched unless told to cut. The share-sheet and browser transports of §05 are the
  same single POST and remain unbuilt.
- Vocabularies and topics are edited in Settings, because neither the generator nor a save can file
  a word under a topic that does not exist.

What the interface cannot do yet, it says so plainly rather than pretending: audio and clip playback
have no media behind them. Article chat (§06) and external dictionaries (§08) remain subsequent
iterations, and both will reach the store through the same YAML reader and the same write route
rather than a second path. Merging a repeat capture into the entry it belongs to waits for §06,
which is why capture stops at the duplicate rather than guessing. Whether generation should be
grounded on external sources at all is an open question with a spike planned for it
(`docs/plans/grounding-spike.md`), not a settled part of §09. Markdown may return only as a
generated export (§12), never as application storage.

---
