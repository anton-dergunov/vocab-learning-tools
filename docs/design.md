# Acervo

**Design document · Rev. E · 29 Aug 2026 · V1 scope agreed · synchronization decided**

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
- **A lexeme with no image and no audio is complete.** Media is an enhancement with its own
  lifecycle, never a blocker on a word being usable, reviewable or exportable. This is what makes
  best-effort, opportunistic generation (§09) safe.

---

## §02 · Sizing

### Two systems, four orders of magnitude apart

The single most useful sizing fact in this document: even **10,000 fully structured lexemes** with
no media amount to only tens of megabytes.

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

**`topic` — an editable grouping**

| Field | Type | Notes |
|---|---|---|
| `id` | recordId | Client-generated in the same format as every other record. |
| `name` | string | User-visible label such as `Health`, `Travel`, or `Slang`. |
| `icon` | string? | Optional emoji or symbolic icon identifier, not binary media. |
| `order` | int | Where the topic sits in the navigation rail. Arrangement is a judgement, so it is data. |

Topics are owner-scoped data, not a hard-coded classification enum. Starter topics are ordinary
seed records, so an empty topic remains available in navigation and users can add, rename, or
retire topics independently of their current lexemes.

**`lexeme` — the thing being learned**

| Field | Type | Notes |
|---|---|---|
| `id` | recordId | Fifteen lowercase letters/digits, client-generated in PocketBase's native format. |
| `language` | BCP-47 | `es`, `en`, `zh-Hans`. Required, indexed, on every query. |
| `headword` | string | As you'd look it up: `desmayarse`, `ponerse malo`, `para entonces`. |
| `lemma` | string | Normalized form for corpus matching. Usually equals headword. |
| `reading` | string? | Pinyin, furigana, transliteration. Empty for Latin scripts, mandatory for `zh`. |
| `ipa` | string? | Broad transcription, shown beside the headword. Independent of `reading`, which is a script aid. |
| `pos` | enum | noun · verb · adj · adv · **phrase** · idiom · expression |
| `gender` | enum? | Spanish articles. `la balsa` vs `el tobillo`. |
| `register` | enum? | neutral · formal · colloquial · slang · vulgar. Your Slang file is already this, as a filename. |
| `dialect` | string? | `es-ES` / `es-MX`. Matters more than you'd think once the corpus is in. |
| `emoji` | string? | Keep it — it's genuinely good recall scaffolding and it's already in your data. |
| `topicIds` | recordId[] | Zero or more topic relations; grouping is many-to-many from the lexeme side. |
| `status` | enum | inbox → active → learned → retired, plus **suppressed**. |
| `shortGloss` | string? | **Derived, with override.** The one-line form — see below. Null unless curated. |
| `notes` | string[] | Usage, register, synonyms and contrasts. |

Every domain record also carries `ownerId`, `deleted`, `createdAt`, `editedAt`, `editedBy` and
`revision`. These fields make the schema replication-ready; the replication protocol itself remains
deferred to §04.

> **WHY "SUPPRESSED" EARNS ITS PLACE**
> Without a way to say *"I saw this, I've decided not to learn it"*, the same word arrives through
> capture forever and dedup can never tell a new word from a rejected one. It's one enum value that
> saves a recurring annoyance.

**`sense` — one meaning, ordered**

| Field | Type | Notes |
|---|---|---|
| `lexemeId` | recordId | |
| `definition` | string | In the **target** language. Longman/COBUILD style — pins the sense precisely. |
| `definitionLang` | BCP-47 | Usually equals the lexeme's language; a field, not an assumption. |
| `glosses[]` | `{lang, terms[]}[]` | **An array, not one language.** `[{en:["column","spine"]},{ru:["колонна"]}]`. |
| `domain` | string? | One word naming what this meaning is about — art · theater · construction — on every sense, in the first gloss language. What the article's sense selector shows. |
| `emoji` | string? | This meaning's own emoji, beside the word's: 🎨 · 🎭 · 🏗️ for the senses of *la obra*. |
| `order` | int | Sense ordering is information — put the common one first. |

Both halves are kept, and neither is privileged. They do different jobs: the target-language
definition pins sense boundaries and is itself extra L2 input; the native gloss is the *click* of
recognition. `turmoil → суматоха` is the case where the native word maps cleanly and the English
definition is a longer road to the same place — and `sobremesa` is the case where no gloss exists
and only the definition works. You need both because your words are split between those two cases.

`glosses` being an array (rather than one `glossLang`) is what lets one lexeme carry an English
gloss *and* a Russian one without redesigning the schema.

> **NO FIELD IS EVER NAMED `l1` OR `l2`**
> L1 means native language, L2 a language being learned — and the shorthand assumes one of each,
> which is exactly what breaks here. Russian is L1; **English is simultaneously a target language
> and the pivot you gloss Spanish in**; Spanish is L2; Chinese is prospective. Your Spanish is
> glossed in English, your English in Russian (`turmoil — суматоха`, `hoax — мистификация`).
>
> So every language-bearing field names *which* language, never a role. Rev. A had this bug in
> `example` (`l2 · l1`); it is fixed below.

**`attestation` — where you actually met the word**

This is the table to fight for. It is the only data in the entire system that is genuinely
irreplaceable: a model can regenerate every gloss and every example forever, but nothing can
reconstruct the sentence you were reading on your tablet when you hit `turmoil`.

| Field | Type | Notes |
|---|---|---|
| `lexemeId` | recordId | |
| `text` | string | The sentence as encountered. Verbatim, typos included. |
| `translation` | string? | Only if you wrote one. |
| `sourceUrl` / `sourceTitle` | string? | Captured automatically — free, and you will want it later. |
| `sourceKind` | enum | web · book · conversation · video · lesson · unknown |
| `capturedAt` | ts | |

> **ATTESTATIONS ARE NOT GENERATED EXAMPLES**
> Keep verbatim source text and generated or curated examples as separate records, connect them with
> explicit lineage, and prefer the attestation whenever the real context is what matters.

**`example`, `studyState`, `captureQueue`**

- `example` — `senseId · text · textLang · translation · translationLang ·
  origin(attestation|llm|tatoeba|subtitle|wiktionary|manual) · sourceAttestationId · modelId ·
  videoRef · videoTitle · videoChannel · videoStart · videoEnd · clipRef · imageRef · emotion ·
  note · matchedForm · matchedTranslationForm`. **`emotion`** is how a speaker would sound saying the
  sentence, a short direction in English that a voice which takes one follows when the example is read
  aloud; a recording is its own record and not a field here (§04 "Media"). `origin` plus `modelId` on every row is
  what makes bulk regeneration safe; **`sourceAttestationId`** is what lets an example be cleaned up
  and still point at the messy original you actually captured. `videoTitle`, `videoChannel`,
  `videoStart` and `videoEnd` (seconds) are what turn a bare `videoRef` into the citable clip the
  specimen above shows — `[clip · DW Español · 4:12]` — and **`clipRef`** is the spoken-usage
  corpus's own stable `segment_id`, so the stored sentence can be audited against the segment it
  names at any time. **`videoRef` is what they all hang on**: any of them without it is refused on
  the way in and hidden on the way out. A clip is an example with `origin: "subtitle"` and no ninth
  table; `docs/plans/spoken-clips.md` is the whole design.

  **`matchedForm` and `matchedTranslationForm`** hold the inflected surface form the corpus or the
  generator actually matched — `pica` for the lexeme `picar`, `itches` in the translation. The
  reader emphasises those substrings. They exist because the alternative is inline markup inside
  `text`, and §01's first invariant forbids a second storage format sneaking in through a
  presentation detail: the sentence stays a plain string, and the emphasis stays a field.
- `studyState` — one row per *(lexeme, system)*: `system · noteId · cardIds[] · reps · lapses ·
  stability · difficulty · retrievability · lastReview · syncedAt`. Keyed by system so a second
  learning tool never collides with Anki.
- `captureQueue` — raw input exactly as it arrived, unprocessed. Your `Spanish vocab - Inbox.md`, as
  a table.

Multi-word entries fall out for free: `ponerse malo`, `que se mejoren` and `para entonces` are
lexemes whose headword contains spaces and whose `pos` is `phrase`. Your data already has dozens, so
make it a first-class case rather than an afterthought.

### The short form is a projection, not a second record

The concise one-liner kept in Obsidian survives as a **rendering** of
`headword + emoji + primary gloss`, which is precisely the markdown shape already in use:

```
##### **la balsa** 🛶
*raft*
```

The short form is a **projection**, not a storage class: it is what the app's list view uses before
you tap through to the full entry and what a future read-only export may render. One source, two
presentations, no drift — which is the whole point of §01's first invariant applied inside the core.

The one wrinkle: "first gloss of the first sense" is right most of the time and misleading for a
word with five senses, where choosing the best one-liner is a judgement call. Hence `shortGloss`
being **derived by default and overridable** — null normally, populated only when you edit it or the
generator judges derivation inadequate.

### `imagePrompt` — its own row, its own stage

Prompts come off the article entirely (§09 explains why) and become first-class regenerable
artifacts:

| Field | Type | Notes |
|---|---|---|
| `lexemeId` | recordId | |
| `senseId` | recordId? | Null for the lexeme-level card image; set for a per-sense example image. |
| `prompt` | string | |
| `styleId` | string | From `image.styles` in config. |
| `seed` | int | Derived from `lexemeId` — the same word keeps its look across regenerations. |
| `modelId` | string | Which model wrote the prompt, not which drew the image. |
| `promptVersion` | string | Checksum of the prompt template, so a template change is detectable. |
| `imageRef` | string? | The rendered image, once a drawing stage has produced one. Null until then. |
| `imageModelId` | string? | Which model *drew* it. Set together with `imageRef`, never alone. |

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


### Worked rows

The case that justifies phrases being first-class — isolating a word here would be nonsense:

```jsonc
// lexeme
{
  "id": "lexeme000000001",
  "ownerId": "owner0000000001",
  "language": "es",
  "headword": "que se mejoren",
  "lemma": "que se mejoren",
  "reading": null,
  "pos": "expression",
  "gender": null,
  "register": "neutral",
  "emoji": "💖",
  "topicIds": ["topic0000000001", "topic0000000002"],
  "status": "active",
  "createdAt": "2026-01-30T09:14:22.418Z",
  "editedAt": "2026-01-30T09:14:22.418Z",
  "editedBy": "device000000001",
  "revision": 0,
  "deleted": false
}

// sense — one row, no per-word breakdown, because there isn't one
{
  "lexemeId": "lexeme000000001",
  "order": 0,
  "definition": "Fórmula para desear a alguien una pronta recuperación.",
  "definitionLang": "es",
  "glosses": [
    { "lang": "en", "terms": ["get better", "feel better soon"] },
    { "lang": "ru", "terms": ["выздоравливайте"] }
  ]
}
```

Raw versus cleaned — both kept, lineage explicit:

```jsonc
// attestation — verbatim, mistakes and all, never rewritten
{
  "lexemeId": "lexeme000000001",
  "text": "espero que se mejoren pronto un abrazo a toda la familia",
  "sourceKind": "conversation",
  "sourceTitle": "WhatsApp — grupo del curso",
  "capturedAt": "2026-01-30T09:14:22.418Z"
}

// example — cleaned and lightly expanded, pointing back at its source
{
  "senseId": "sense0000000001",
  "text": "Espero que se mejoren pronto. Un abrazo a toda la familia.",
  "textLang": "es",
  "translation": "I hope you get better soon. A hug to the whole family.",
  "translationLang": "en",
  "origin": "attestation",
  "sourceAttestationId": "attest000000001",
  "modelId": "gemini-3-flash",
  "imageRef": null,
  "emotion": "warm and tender, a goodbye full of care"
}
```

The entry still displays as **yours**, shows the corrected sentence, and the original is one hop
away. Punctuation and capitalisation are repaired; wording is not invented.

Your English case, with both glossing halves earning their place:

```jsonc
{ "language": "en", "headword": "turmoil", "pos": "noun", "topicIds": ["topic0000000003"] }
{
  "definition": "A state of great confusion, disturbance or uncertainty.",
  "definitionLang": "en",
  "glosses": [{ "lang": "ru", "terms": ["суматоха", "смятение", "потрясения"] }]
}
```

And `studyState`, pulled back from Anki (§10):

```jsonc
{
  "lexemeId": "lexeme000000001",
  "system": "anki",
  "noteId": 1738291045123,
  "cardIds": [1738291045124, 1738291045125],
  "reps": 14, "lapses": 3,
  "stability": 41.7, "difficulty": 7.9, "retrievability": 0.86,
  "lastReview": "2026-08-19T07:02:11.000Z",
  "syncedAt": "2026-08-26T06:30:00.000Z"
}
```

Difficulty 7.9/10 with 3 lapses is the gate in §10: *this* is a word that earns a custom image.

### Glossing and reveal order are configuration

Not code branches, and not a global setting — one block per language in `config/defaults.yaml`,
overlaid by `config/local.yaml` as everything else already is:

```yaml
languages:
  es:
    display_name: "Spanish"
    definition_lang: es           # Longman-style, in the target language
    gloss_langs: [en]             # the pivot you actually think in for Spanish
    reveal: definition_first      # definition_first | gloss_first | both
    reading: none
    tokenizer: whitespace
    lemmatizer: "spacy:es_core_news_sm"
    anki_deck: "Spanish::Vocabulary"

  en:
    display_name: "English"
    definition_lang: en           # the Longman habit you already have, made structural
    gloss_langs: [ru]             # native — the click
    reveal: definition_first
    reading: none
    tokenizer: whitespace
    lemmatizer: "spacy:en_core_web_sm"
    anki_deck: "English::Vocabulary"

  zh-Hans:
    display_name: "Chinese (Simplified)"
    definition_lang: en
    gloss_langs: [ru, en]
    reveal: gloss_first           # no shared background — the gloss has to land first
    reading: pinyin_numbered      # stored numbered (ma1), rendered with diacritics
    tokenizer: jieba
    lemmatizer: none
    anki_deck: "Chinese::Vocabulary"
```

`reveal: definition_first` shows the target-language definition with the native gloss one tap
behind — forcing L2 processing while keeping the safety net in reach. On an Anki card the same
setting splits front and back. Chinese inverts it for the reason you gave: with no shared
etymological background, withholding the gloss buys nothing.
## §04 · Storage & sync

### PocketBase durability and an owner-scoped local replica

> ### DECISION
> **PocketBase is the durable store. IndexedDB is the complete owner-scoped local replica and the
> only store the interface reads. Reads work offline forever; writes require the server.**
>
> **Coexistence is a non-issue.** Your `compose.yaml` is already parameterized: a different
> `container_name`, `PB_PORT` and `PB_DATA_PATH` is the entire change. Separate container, separate
> volume, separate SQLite file. They never see each other.

### The asymmetry that decides everything else

This design was drawn from Calorie Logger, which has been in daily use long enough to be trusted.
Copying it wholesale would be the wrong instinct, because the two apps sit on opposite sides of one
question: **must a write survive being made with no network?**

For Calorie Logger, yes, and non-negotiably. You log a meal standing in a kitchen with no signal, the
record is a food, a day and an amount, and last-write-wins on three scalar fields is an honest merge.

For Acervo, no. Almost every write is *creation or revision of a rich article*, and almost all of it
originates on the server anyway: capture calls an LLM (§05), in-place editing calls an LLM (§06),
enrichment is a Prefect flow (§09), study state arrives from Anki (§10). What is left for a device to
originate by hand is rare — marking a word learned, flagging one to focus on, occasionally correcting
a generated sentence. Merging two independently-edited versions of an article has no honest answer,
and building the machinery to attempt it would buy a case that barely occurs.

> ### DECISION
> **Every read is served from the replica and works with the server unreachable. Every write —
> create, edit, delete, reset — is a synchronous round trip that fails loudly when offline and
> leaves the replica untouched.**
>
> **Because** this deletes the entire conflict-resolution surface rather than implementing it, and
> the cases it costs are ones this app does not have.
>
> **And it pays for itself twice.** Only the server ever mints a version of a record, so `revision`
> becomes a reliable total order on versions. There is no timestamp comparison anywhere in the merge
> path and no clock skew to tolerate — which Calorie Logger cannot have, precisely because two of its
> devices can each produce version *n+1* offline before either is seen.

`editedAt` and `editedBy` stay on every row. They are provenance — *when, and from which device* —
and no longer a merge key.

### How this differs from Calorie Logger, and why

| | Calorie Logger | Acervo | Why |
|---|---|---|---|
| **Offline writes** | Queued, unbounded | **Refused, with an error** | Rich records; merging two edited articles has no honest answer |
| **Merge key** | `editedAt` string compare, tie broken by `editedBy` | **`revision` alone** | Only the server mints versions, so revisions totally order them |
| **Concurrent edit** | Last-write-wins, counted and reported afterwards | **Refused — `409 stale_record`** | An interactive save can be retried; a queued one cannot |
| **Round trips** | One combined `POST /sync` | **Separate pull and push** | There is nothing to push at poll time |
| **Partial failure** | Rejected per record | **All-or-nothing per batch** | One save is one article; half an article is worse than none |
| **Poll interval** | 15 s | **60 s** | A newly captured word does not need to arrive this second |
| **Pending queue** | Central to the design | **Does not exist** | Nothing is ever unsent |
| **Rebuilt server** | Wipe the cursor, re-push everything | **Stop and ask** | Nothing is re-pushed here, so wiping could destroy the last full copy |

### The cursor is a counter, not a clock

Every replicated row carries `revision`: a position in one strictly increasing per-owner sequence,
assigned by the server. A client stores the highest revision it has received and asks for
`revision > cursor`.

> **WHY NOT A TIMESTAMP**
> A record written while your request is already in flight is stamped *before* the moment your read
> finishes. Ask next time for "everything since that moment" and you skip it — permanently, silently,
> and only for the one device that was unlucky. A monotonic counter has no such gap.

The counter lives in a `sync_state` row, one per owner, in a collection that is **never replicated**.
It is deliberately not a field on a synced record: a counter only the server may advance must not be
something a stale device can overwrite. That row's id doubles as the **`datasetId`** — rebuild the
database and every outstanding cursor is invalidated for free.

**Revisions are assigned by a model hook, not by the API route.** The route is not the only writer:
the seeder writes as a superuser, Prefect flows will write generated content, the Anki consumer will
write study state. A record saved with `revision` left at zero is invisible to `revision > cursor`
forever — a silent, permanent, per-record data loss. Putting the allocation in the save hook means no
writer can forget.

### The protocol

**Pull — `GET /api/acervo/v1/graph?since=<cursor>`**

Returns `{ schemaVersion, datasetId, cursor, serverTime, changes }`, where `changes` is the seven
record arrays filtered to `owner = you AND revision > since`, ordered by revision. Tombstones
included; the client filters them at read time. `since=0` returns everything, so a first sync and a
steady-state poll are the same code path with no special case.

**Push — `POST /api/acervo/v1/graph`**

Carries `{ schemaVersion, deviceId, changes }` and applies it in one transaction. Each record states
the `revision` it was edited from; if the stored revision has moved on, the whole batch is refused
with `409 stale_record` naming the entry, and the interface says so rather than guessing. The
response is the canonical stored rows plus the new cursor, so the screen repaints without waiting for
the next poll.

> **MERGE ORDER FOLLOWS THE GRAPH**
> Topics before lexemes; lexemes before senses and attestations; those before examples and
> sense-linked image prompts. Applied in that order, on both sides, a relation always resolves.

**Both requests carry `schemaVersion`.** A mismatch is a `409` that puts the client in a terminal
*blocked* state: it stops syncing and says the app needs updating, while local reading carries on
untouched.

### Polling, not push

> ### DECISION
> **The client polls every 60 seconds while visible, on focus, on regaining the network, and
> immediately after any write. There is no server push.**
>
> **Because** a cursor pull that finds nothing is one indexed range scan per collection and a few
> hundred bytes — the indexes it needs are already in the schema. SSE or PocketBase realtime would
> buy seconds of latency in exchange for a long-lived connection through a reverse proxy and
> Tailscale, reconnect and backoff logic, and a subscription surface on a server whose generic
> collection access is deliberately closed.
>
> **And it is not a one-way door.** The cursor is the client's entire synchronization state, so a
> push channel can be added later as a pure latency optimisation, changing nothing else.

A failed sync is not an error the owner must act on; it is a sync that will happen later. There is no
backoff and no retry queue — the interval *is* the retry.

### Resetting, and the trap in restoring

Two destructive actions exist, and they are not the same action:

- **Download this device's copy again** — discard the replica, pull from zero. Costs nothing; the
  server is unaffected.
- **Delete all words** — tombstone every lexeme and its senses, attestations, examples, image prompts,
  and study states, server-side, replicating to every device. Vocabulary-language settings, topics,
  the user and the dataset identity remain. This
  is the one genuinely dangerous button in the application, so it quotes the live counts and requires
  the word `DELETE` to be typed. It is a write, so it needs the server like any other. It never
  removes a row: §17's rule that tombstones are never collected means even this stays undoable.

> ### THE CONSEQUENCE OF ONE-WAY WRITES, WRITTEN DOWN
> Devices never push, so **a device replica can no longer silently repair a server restored from an
> old snapshot.** In Calorie Logger that repair is automatic and free. Here, "rebuild the server from
> this device" (§17, layer 0) becomes a *deliberate, manual* recovery path.
>
> Which is exactly why a changed `datasetId` must not behave as it does in Calorie Logger. There, a
> rebuilt server means "reset the cursor and re-push everything." Here there is nothing to re-push,
> so the same reflex would discard the most complete surviving copy of the vocabulary in order to
> replace it with an older one. **The client stops instead**, explains what happened, and does
> nothing destructive until a human chooses.

### On wanting NoSQL experience

A legitimate motivation — but don't put it in the critical path of an app you want to *use*, and
don't let it push you toward a database your data doesn't want. The core is small and thoroughly
relational: lexeme → sense → example → attestation → card link are all joins. MongoDB Community is
free to self-host, but idles at hundreds of megabytes against PocketBase's ~20, and buys nothing
here.

Put that curiosity where it is genuinely earned: **the corpus index** (§07). Millions of lemmatized
subtitle lines with ranked full-text retrieval and faceting is a real search-engineering problem —
and a far better thing to have built than "I stored 900 words in Mongo." It is also the layer where
getting it wrong costs you nothing.

### What carries on every replicated row

Every record carries `ownerId`, `deleted`, `createdAt`, `editedAt`, `editedBy` and `revision`.
Deletions are tombstones. IDs stay client-generated in PocketBase's own 15-character format: it costs
nothing, it keeps id minting out of the write path, and it means a future offline-write mode would
need no schema change — every field such a mode requires is already on the row. That is an escape
hatch left open, not a plan.

### Media

**Images are not replicated; pronunciations are.** Both live on the server and are fetched and cached
on demand by the device, but only one of them is a record in the graph.

This rule used to cover both, and it was written with 300 KB pictures in mind. A spoken headword is a
couple of kilobytes: the clips of a whole vocabulary cost about what its *text* does, while its
pictures cost two orders of magnitude more. So a clip is a row like any other — it carries the words
it speaks, the voice that spoke them, and Opus at around 60 kbps because a blind listening test said
so (`experiments/pronunciation-encoding/`) — and it travels on the ordinary cursor pull, which is what
lets a word recorded on one device be heard on another with no network at all. The text of your
vocabulary works on a plane, and now so does hearing it; the illustrations still do not, and
shouldn't pretend to.

**Built.** How a clip is identified, when it is stale, how it is encoded and which voices read what
is in `AGENTS.md` and `src/acervo/pronunciation/`; the measurements are
`experiments/pronunciation-encoding/`. What those do not say is why the shape is this one:

- **Two orders, because a reference and a reading are different things.** A headword's clip is a
  *reference*: one per word, offline, correct, and read by one voice held stable per language so that
  a deviation is audible. An example's clip is a *reading*, where prosody carries meaning and a voice
  that takes a direction earns its cost. That, not "plain versus expressive", is why `audioPlain` and
  `audioExpressive` are separate choices.
- **Nothing synthesises on the device.** Every sentence that can be spoken arrived through a write,
  and writes are online, so the server can record it the moment it exists and the clip reaches the
  device on the same pull as the record. That removes the argument for a neural voice in the
  browser, which would cost 60–180 MB per language to close a window that is already closed.
- **The device's own voice is not a fallback.** `speechSynthesis` cannot be captured, so it can never
  fill a cache; and a device with no voice for the language reads Spanish in an English voice, often
  without the page being able to tell. A pronunciation reference that may teach the wrong sounds is
  worse than none.
- **Batching words into one call buys nothing.** Speech is metered by characters or by audio
  duration, and neither shrinks when ten words share a request; only the request count does, and
  splitting the result back into words needs alignment. A request-metered tier is answered by
  choosing a character-metered provider, not by batching.
- **A bad recording is replaced from the toast.** After a stored clip plays, the message offers
  Record again: the moment you know a recording is bad is the moment you have just heard it, and a
  control under every sentence would be a page of buttons.

Deliberately not built: speech-to-text, pronunciation assessment (recording the owner and scoring
it is a product of its own), a second media store or pipeline, and voices running on the
device. Voices running on the NAS, other providers and human recordings are in
[`plans/provider-management.md`](plans/provider-management.md).

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

**Built.** The working design is [`llm-editing.md`](llm-editing.md), which settled the
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

The 192–384 px figure in `docs/image-generation-research.md` reads as though the image were a small
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

> ### DECISION
> **Everything runs on the NAS except image generation, which is dispatched to an opportunistic Mac
> worker.**
>
> The NAS handles LLM calls (plain HTTP), Kokoro TTS (82M parameters, fine on CPU), OCR, corpus
> harvest and indexing, and the whole capture→article path. Diffusion is the only thing it cannot do.

```
                    Prefect control plane + Acervo API
                          Synology NAS, always on
                                    │
                 ┌──────────────────┴──────────────────┐
                 │                                     │
      CPU / API / network work                  MPS image work
      - capture → article                       - MFLUX / local models
      - LLM calls, TTS, OCR                     - MacBook, when idle
      - corpus harvest + index                  - worker runs only while
      - Anki sync                                 you are away from it
```

The Mac worker is not always on and is not supposed to be. A launchd agent starts it when
`ioreg -c IOHIDSystem` reports idle beyond a threshold — plus on-AC-power and no thermal pressure —
and stops it on input. Jobs it abandons are requeued by the orchestrator, which is safe because
generation is content-hash keyed and therefore idempotent. Two priority bands are enough: the word
captured ten minutes ago must jump ahead of a 900-entry backfill.

### Provider chain

Per job, from configuration, tried in order:

```yaml
image:
  chain:
    - provider: gemini          # burn the expiring Vertex credits on the bulk backfill
      priority_bands: [backfill]
    - provider: cloudflare      # free daily quota carries the steady state
    - provider: mflux           # local M1 fallback, idle-gated
    - provider: none            # ← a success, not a failure
```

> **`none` IS A SUCCESSFUL OUTCOME.** A lexeme with no image is complete (§01). This is what makes
> the whole dispatch safe to be lazy about: if images were required, the queue becomes a critical
> path and your MacBook becomes a hard dependency of your vocabulary. The emoji already carries a
> visual anchor at zero cost.

### Prefect

> ### DECISION
> **Synchronous means making the entry exist and be correct. Everything that enriches it afterwards
> is asynchronous, and Prefect owns all of it.**
>
> **Synchronous, Prefect never involved:** capture → cleaned article → review / edit / approve; the
> sync API; regenerate-with-a-note; corpus *lookups* when displaying a word.
>
> **Asynchronous, all Prefect:** image-prompt generation, image generation, TTS, YouTube harvest and
> subtitle indexing, Wiktextract ingest, story and comic generation, Anki push and FSRS pull,
> Obsidian export, and the sweeps — dedup, re-topicking, mass regeneration when a better model lands.
>
> **The line to hold:** capture → article → review must work with the orchestrator down, and the sync
> API must not know Prefect exists. If Prefect is down you lose enrichment, not your vocabulary.

Two things fall out of broadening it this far.

**The Mac needs exactly one work pool.** Earlier revisions gave it two, the second for AnkiConnect —
that is gone now that §10 runs Anki on the NAS.

| Pool | Gate | Runs |
|---|---|---|
| `mac-idle` | `HIDIdleTime` > threshold, on AC, no thermal pressure | MFLUX image generation, local models |

Only one, because §10 moves Anki onto the NAS entirely. The Mac does exactly one job, and only while
you are away from it.

> ### FLOWS ARE SWEEPS, NOT EVENT CONSUMERS
> If Prefect owns everything asynchronous, its availability starts to matter. The fix is to derive
> work from the data rather than from a queue: **"which lexemes lack an image" is a query against the
> core**, not a queue entry.
>
> Then a lost enqueue cannot lose work, Prefect being down for a week costs latency and nothing else,
> and every flow is idempotent by construction rather than by discipline. Never let the queue be the
> only record that work is needed.

**§09 REVISED — enrichment is event-driven, from a durable job record, and runs in the server.**
[`plans/processing-flow.md`](plans/processing-flow.md) retires the rule above. It was written for an
architecture that no longer exists: Prefect as an *optional* orchestrator, and image generation on an
idle-gated MacBook that could be away for a week. There is no orchestrator and no second machine; one
Python process serves and works.

What the rule protected against is gone: the job is written in the **same transaction** as the word
that needs it, so either both exist or neither does. What it got right is kept — a job says *which
word* and each step re-derives what that word still lacks, the derived ids make two writers converge,
and "none" is a successful outcome. What it cost is gone too: the interface no longer carries a
pipeline, a headless capture no longer waits for a sweep, and nothing runs on a schedule except one
nightly corpus update.

Two cautions carried forward from that document, both still right:

- **Phase 1 discipline.** Ordinary Python stages first, Prefect as an optional wrapper over the same
  functions. The risk was never Prefect; it is Prefect becoming load-bearing before the stages are
  idempotent.
- **Footprint.** A Prefect server plus SQLite is a few hundred megabytes resident, queueing behind
  PocketBase, the corpus service and info-triage on the same Synology. Measure before committing —
  and if the box gets tight, that is an argument for SQLite FTS5 over Meilisearch in §07.

The existing provider-factory pattern survives intact. Future flows will derive work from canonical
PocketBase records and write results back as canonical records.

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
[`docs/plans/spoken-clips.md`](plans/spoken-clips.md).

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
(`docs/grounding-spike.md`), not a settled part of §09. Markdown may return only as a
generated export (§12), never as application storage.

---

## §17 · Durability

### The threat is not disk failure

Losing a day of Calorie Logger costs nothing — you re-add the meal. Losing this costs years of
curation that cannot be reconstructed by any amount of compute. So the backup design has to take the
threat model seriously, and the real threat is not a dead disk. It is **logical corruption that
replicates**: a bad migration or a mis-tap removes 200 words, and by the time you notice, every
device has faithfully agreed.

> ### THE TRAP SPECIFIC TO THIS ARCHITECTURE
> **Restoring the server does not undo a deletion.** Undoing a logical delete is a **data edit**, not
> a restore: write a *new* un-delete, which the server stamps with a higher revision so it beats the
> tombstone on every device. Two entirely different procedures for two failure modes that feel
> identical from the outside.
>
> §04's online-only writes make this *less* dangerous than it is in Calorie Logger — devices cannot
> re-push tombstones at a restored server, because devices never push at all — but they do not make
> it go away, because a restore that mints a new `datasetId` is exactly the situation where a client
> would otherwise replace its own good copy with the older one. That is why it stops and asks.

Which yields a design rule: **never garbage-collect tombstones.** Calorie Logger might eventually;
this must not. A deleted word remains *in* the database, so accidental deletion is recoverable by
flipping a flag. At 10,000 lexemes the storage cost is nil and it buys an undo that survives
everything.

### The layers

**0 · The replicas themselves.** Every device already holds a complete copy — N-way redundancy
against server loss, for free. A device that has not synced recently holds an accidental
*point-in-time* copy.

> **THIS LAYER IS NO LONGER AUTOMATIC.** In Calorie Logger, devices re-push everything they hold, so a
> restored snapshot repairs itself and "the replicas are a backup" is true without anyone doing
> anything. Acervo's devices never push (§04), so **the same recovery must be built and invoked by
> hand.** A deliberate "rebuild the server from this device" path is therefore not a nice-to-have
> here; it is what keeps this layer from being a comforting fiction. Until it exists, treat the
> replicas as evidence — enough to see what was lost — rather than as a restore.

The corollary already lands in the sync design: a client that meets a rebuilt server refuses to
discard its replica, because that replica may be the most complete copy left.

**1 · SQLite snapshots on the NAS.** Hourly keep 24, daily keep 30, monthly keep 12. The database is
~50 MB, so this is nearly free.

> **Use `sqlite3 .backup` or PocketBase's own backup — never `cp`.** Copying a live WAL-mode database
> is the classic route to a backup that looks fine until the day you need it.

**2 · Git-backed semantic export.** Not because git suits SQLite — it does not — but because it is a
*different representation*: it survives a schema bug that corrupts the database, it is offsite and
versioned by a third party, and it restores without any of this software working.

Format matters. **One file per lexeme**, in a tree by language:

```text
es/desmayarse.yaml
es/que-se-mejoren.yaml
en/turmoil.yaml
```

YAML rather than JSON, and the application's own article document rather than a second shape: the
one place that understands this format already both writes and reads it, so an export cannot drift
from what the editor accepts. The file is named after the *lemma*, latinised — accents stripped,
Cyrillic transliterated, and a script with no Latin form falling back to the reading, which Chinese
lexemes already carry as pinyin. The lemma rather than the headword, or half a Spanish vocabulary
files under `el-` and `la-`.

One file per word rather than one blob, because then `git log -- es/desmayarse.json` gives the
**complete edit history of a single word** — which no database backup provides — and
`git diff HEAD~1` after the daily commit is a readable review of what changed. The day 200 words
vanish, you see it in a diff rather than discovering it in November.

Export the Obsidian markdown (§12) into the same repository, and both machine-readable and
human-readable forms live together.

This tier is now half-built: Settings ▸ Data writes exactly this tree (§12), by hand. What is still
missing is the automation — a scheduled exporter that commits it.

Cadence: debounced after any sync that changed something, **plus a daily commit even when nothing
changed**. The heartbeat is what proves the exporter is alive — a silently dead exporter is the real
risk, not a missed commit. The export must carry a schema version, so a 2028 restore of a 2026 export
still parses.

**3 · Media and the Anki collection, separately.** Media is 2–10 GB, so git is the wrong tool.
Regenerable in principle (§01), but regenerating ~2,700 images costs real money and time — so restic
or rclone to another disk or cheap object storage, content-addressed by hash so dedup is free. The
Anki collection now lives on the NAS too (§10) and joins this tier: **review history is as
irreplaceable as the vocabulary**, because years of FSRS state cannot be regenerated at any price.

**4 · Restore drills.** The layer everyone skips, and the only one that proves the others work. A
monthly Prefect flow that pulls the latest backup into a scratch container, imports it, counts
lexemes and compares against production. This is what catches *"the backup has been silently empty
for six months."*

### Restoring

> **A restore must mint a new `datasetId`.** The revision sequence restarts, so every client holding
> an old cursor is asking for revisions the restored database has not reached. Without the guard it
> pulls nothing, reports itself perfectly in sync, and shows a collection no other device can see.
>
> Because the identity is the `sync_state` row's id (§04), a rebuilt database gets a new one for
> free. A restore into an *existing* database must invalidate it deliberately — restoring the file
> and leaving that row intact is the one way to reproduce this bug on purpose.

**What a new `datasetId` does here is stop every client, not reset them.** Calorie Logger resets the
cursor and re-pushes; that is safe there and unsafe here, for the reason layer 0 gives above. So the
restore procedure has a manual step by design:

1. Restore the snapshot. Every device notices and stops syncing.
2. Decide, per device, which copy is more complete — the devices are the evidence.
3. Either rebuild the server from the best replica, or accept the snapshot and let each device
   download it again.

Losing that automatic repair is the real price of online-only writes, and it is worth paying: it
costs a manual step in a rare procedure, and it buys the absence of merge conflicts in the everyday
one.

### What is not backed up

The corpus (§07), by definition — it is regenerable, and that is the invariant that earns it a
separate database in the first place. **But the harvest list** — which channels, which video ids —
**goes in git.** It is tiny and it encodes curation decisions that would be painful to reconstruct.

---

*Acervo · design document · Rev. D · Multilingual from v1 · corpus index in v1*
