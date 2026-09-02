# External dictionaries — source research

**Status:** research, nothing built. Design §08 defines the storage stance and closes with "out of
scope for this iteration". This document is the survey that would let it be brought into scope, plus
the decisions that survived a first review.

Two separate needs push toward published dictionaries:

1. **Glancing.** LLM composition costs money, needs the server, and takes up to five seconds.
   Looking a word up to *peek* at it should be instant and should work offline — and it is
   independently valuable to check a generated article against a human-compiled one. **This is the
   need that justifies the feature.**
2. **Grounding.** Design §09 names this "the highest-leverage change to the existing pipeline".
   [acervo-grounding-spike.md](acervo-grounding-spike.md) owns that experiment and it is
   **postponed** — too much else is unbuilt, and §1 below argues the expected benefit is narrower
   than §09 assumes. Grounding is a later, optional consumer of whatever this document produces, not
   its motivation.

Design §08 already fixed the storage stance: external dictionaries are **read-only files, read
directly, never ingested into PocketBase, never in the replica**, and the unit of installation is
"this dictionary on this device". Nothing below contradicts that.

Directions surveyed: `en → en/ru`, `es → es/en/ru`, `zh-Hans → zh/en/ru`, plus German, French and
Japanese as a representative sample. Figures are current as of the August 2026 Wiktionary dumps.

---

## §1 · Sense coverage is not the goal — condensation is

An earlier draft of this document recommended chasing **sense recall**: how many of the source's
senses appear in the generated article. That was wrong for this product, and the correction matters
enough to state plainly.

`picar` is the test case. The [Spanish Wiktionary entry](https://es.wiktionary.org/wiki/picar) lists
**37 numbered senses**. Sense 36 is "jactarse de algo con demasiada presunción"; sense 37 is
Argentine colloquial for "correr a toda prisa". Acervo currently generates three to five senses for
a word like this, and that is the right number for something a person will actually read. A
37-sense article does not teach `picar` better — it makes the word look like a chore and drives the
reader away from it.

So the dictionary's completeness is a **library property, not an article property**:

- **A short list is the deliverable.** Three to five senses that give the overall shape of the word,
  from which a reader can infer the rest in context. Condensation is the editorial work, and it is
  the thing the LLM is currently good at.
- **Obscure, regional and highly specific senses are opt-in.** They belong in the external
  dictionary, reachable on demand, and enter the personal store only when someone deliberately adds
  one because they met it and want to remember it. A regional slang sense arriving unbidden in a
  generated article is a defect.
- **Sense inflation is a regression, not a win.** If grounding causes more senses to be shown, that
  is the failure mode to watch for, not the success metric.
- **The narrow real risk remains.** The literature's finding — that models silently drop senses —
  still holds, but only matters when a *common* sense goes missing. That is the thing worth
  measuring: not recall over 37, but whether the top three to five are the right three to five.

### What that means for the grounding spike, when it eventually runs

The metric is not recall. It is: does the grounded variant change the senses that get *shown*, and
are the changes improvements? With a hard negative check on sense count. This is a materially
smaller and more honest question than the one §09 implies, and it is a reason the spike can wait.

### Related, and deliberately noted here

The same "condense, don't enumerate" instinct points at where generated imagery is worth investing:
**images per sense and per example sentence, not per headword.** A sentence already carries the
action and the context, so the image prompt has something to draw; a bare headword usually does not,
and for concrete nouns the emoji already in the model does the job. This belongs in design §09's
`imagePrompt` staging rather than here, but it came out of the same reasoning and should not be lost.

---

## §2 · English (`en → en`, `en → ru`)

### Downloadable

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **Wiktextract / kaikki.org** | en→en (+ translations to ~everything) | English: **1,780,480 senses**, ~1.35 M entries, **2.69 GB** as JSONL. (The widely-quoted 22.9 GB / 2.6 GB gz figure is the **all-languages** raw dump extracted from the English Wiktionary — hundreds of languages, not English alone.) | CC BY-SA 4.0 + GFDL | **Core.** Richest structure available anywhere: senses, tags, categories, IPA, forms, etymology, translations, examples. |
| **Open English WordNet 2024** | en→en | 120,630 synsets · 161,705 words · 418,168 relations; 312.6 MB package | **CC BY 4.0** (no share-alike) | Best *sense-relation* graph, and the rare permissive licence in this field. Terse glosses, no register — an enrichment layer, not a reading dictionary. |
| **GCIDE** (Webster's Revised Unabridged 1913 + WordNet additions) | en→en | 124,186 headwords; ~99 k words / 160 k definitions as JSON | Public domain text / GPL packaging | Beautiful prose, **1913 vocabulary**. Charming, wrong for a learner. |
| **kaikki `ruwiktionary`** | en→ru | 103,681 English senses, **definitions in Russian** | CC BY-SA 4.0 | **Core.** The only large source of Russian-language definitions for English words. |
| **FreeDict `eng-rus`** | en→ru | 62,181 headwords (v2025.11.23) | GPL-ish, per-dictionary | Actively rebuilt. TEI / dictd / StarDict / slob. |
| **Mueller 7th ed.** | en→ru | ~70 k words & expressions | **GPL** | The one solidly-licensed en→ru dictionary. Mid-20th-century vocabulary — label it as dated in the UI. |
| **WikDict `en-ru`** (from DBnary) | en→ru | part of 17.7 M translations / 26 languages | CC BY-SA 4.0 | StarDict, SQLite, TEI P5, Kobo. Clean provenance, machine-derived. |
| **PanLex** | en→ru (+ ~any pair) | 20 M lexemes, ~9,000 varieties, **1.1 B translation pairs** | **CC0** | Bare translation pairs, no definitions, no sense boundaries. The long-tail fallback. |

### Online APIs

Rate limits deserve less anxiety than they usually get. Realistic personal use is a handful of
lookups a day; every free tier below is two to three orders of magnitude above that. Limits only
become a design input if a dictionary panel starts prefetching, which it should not.

| API | Coverage | Free tier | Notes |
|---|---|---|---|
| **freedictionaryapi.com** | Multilingual, Wiktionary-backed, "8.5 M+ words" | **No key, 1,000 req/hour/IP** | **Start here.** Wiktionary-shaped, so it shares a field mapper with the offline kaikki files. Attribution required. Not self-hostable. |
| **Wikimedia REST** `…/api/rest_v1/page/definition/{term}` | All Wiktionary editions | 500 req/h unauthenticated, 5,000 authed; User-Agent required | **The fallback.** Official, and same upstream data — same mapper again. |
| **dictionaryapi.dev** | English only | No key, no published limit | Still up as of 2026. Community-run, no SLA. |
| **Wordnik** | AHD, Century, Wiktionary, GCIDE, WordNet — 800 k+ words | Generous free tier | Several dictionaries behind one call. Needs its own connector. |
| **WordsAPI** | English | 2,500 req/day, then $0.004/req | Ample for personal use. Thin content, own connector. |
| **Merriam-Webster** | Collegiate, Learner's, Spanish-English, Medical | 1,000 queries/day/key, **non-commercial**, max 2 reference APIs | High editorial quality. Commercial use requires a deal. |
| **Lexicala** (K Dictionaries) | 50 languages, 100 domains | Commercial only | One vendor covering en/es/zh/ru with real sense structure, if the free sources ever prove insufficient. |
| Glosbe public API | — | **Deprecated** | Do not build on it. |

### What the data looks like

Note how close the first one already is to Acervo's own article model — that similarity is the whole
basis of the tiering in §7.

```
# kaikki.org / wiktextract JSONL — one JSON object per line, abridged
{"word":"picar","pos":"verb","lang_code":"es",
 "sounds":[{"ipa":"/piˈkaɾ/"}],
 "forms":[{"form":"pico","tags":["first-person","singular","present"]}, …],
 "senses":[
   {"glosses":["to itch (to feel itchy; to feel a need to be scratched)"],
    "tags":["intransitive"]},
   {"glosses":["to mince, to dice"],"categories":["Cooking"]},
   {"glosses":["to get angry, take offence"],"tags":["reflexive"]}, … many more],
 "translations":[…], "etymology_text":"…"}

# CC-CEDICT — one line per entry, fixed grammar
漢字 汉字 [Han4 zi4] /Chinese character/CL:個|个[ge4]/

# Open English WordNet
hound, hound dog — (any of several breeds of dog used for hunting,
                    typically having large drooping ears)
```

---

## §3 · Spanish (`es → es`, `es → en`, `es → ru`)

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **kaikki `eswiktionary`** | **es→es** | **1,035,866 Spanish senses**, definitions in Spanish | CC BY-SA 4.0 | **Core.** The monolingual answer, larger than the English edition's Spanish coverage. Also the source of the 37-sense `picar` entry in §1. |
| **kaikki**, English edition | es→en | **874,006 senses** | CC BY-SA 4.0 | **Core.** Best es→en structured data. Rich tags, dialect labels (`Mexican Spanish`), domains. |
| **WikDict `es-ru`, `es-en`** | es→ru / en | part of 17.7 M translations, 26 languages | CC BY-SA 4.0 | Best *legal* es→ru option, but translation pairs rather than definitions. |
| **kaikki `ruwiktionary`** | es→ru | **only 21,085 Spanish senses** | CC BY-SA 4.0 | Too thin to be a primary es→ru dictionary. |
| **MCR 3.0** (Spanish WordNet) | es→es + ILI to en | 51 MB SQL dump | **CC BY 3.0** | Sense relations plus cross-lingual links. Academic, 2016-vintage, permissive. |
| **doozan/spanish_data** | es→en | Wiktionary + Tatoeba derived, with frequency and lemma data | CC BY-SA | Prebuilt StarDict / slob. Saves a pipeline. |
| **FreeDict `eng-spa` / `spa-eng`** | en→es / es→en | 64,258 / **only 4,502** headwords | GPL-ish | The needed direction is unusable. |
| **Tatoeba** | es↔en/ru examples | **13.4 M sentences, 429 languages** (Apr 2026) | CC BY 2.0 FR, some CC0 | Human sentence pairs. Already tier 2 of the corpus in §07. |
| **RAE / DLE** (23rd ed.) | es→es | ~93 k entries | **Copyrighted, no public API** | The dictionary Spanish speakers actually cite, reachable only by scraping. Link out to `dle.rae.es`; do not ship a scraper. |
| SpanishDict, Linguee, Reverso | es↔en | — | Proprietary | No usable API. Link out only. |

### The honest `es → ru` finding

There is no good open Spanish→Russian dictionary. The options are WikDict pairs, PanLex pairs
(CC0), or pivoting es→en→ru and compounding the error. **Use dictionaries for `es→es` and `es→en`,
and keep letting the LLM write the Russian gloss.** (§11.3 confirms both directions map cleanly —
95.0 % and 97.5 % of entries — with nothing invented.) That is a genuine strength of the current
pipeline, not a gap, and it is a reason not to over-invest in bilingual dictionary plumbing.

---

## §4 · Chinese Mandarin (`zh → zh`, `zh → en`, `zh → ru`)

Subsystem deferred per §07; the schema (`reading`, traditional↔simplified as a variant axis) already
anticipates what these sources need.

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **CC-CEDICT** | zh→en (+ pinyin) | **124,948 entries** (2026-08-31); ~2.6 MB gz / **~9.5 MB plain** | **CC BY-SA 4.0** | **Core, and the ideal first spike input.** Traditional + simplified + numbered pinyin on one line, fixed grammar, trivially parsed. |
| **moedict / g0v** (MOE 重編國語辭典) | **zh→zh** | 160 k Mandarin + 20 k Taiwanese + 14 k Hakka entries; JSON + bz2 + **free API** | Taiwan MOE open data | **Core.** The monolingual answer. **Traditional characters**, Taiwan norms. Bundles CC-CEDICT/CFDict/HanDeDict and stroke animations. |
| **kaikki**, English edition | zh→en | Chinese **388,964 senses**, Mandarin **112,609** | CC BY-SA 4.0 | Deeper than CC-CEDICT on senses, noisier on readings. |
| **ECDICT** | **en→zh** | 760 k base / 3.4 M in `ECDICT-ultimate`; CSV 76 MB compressed; SQLite / MDX / StarDict / Mobi | **MIT** | Superb metadata: BNC and contemporary frequency ranks, Collins stars, Oxford 3000 flag, exam tags, inflection tables. Wrong direction for the Chinese vocabulary, excellent for the English one. |
| **kaikki `ruwiktionary`** | zh→ru | 11,001 Mandarin senses | CC BY-SA 4.0 | The legal zh→ru baseline. Thin. |
| **BKRS / 大БКРС** | **zh→ru** | The reference Chinese–Russian resource; dump at `bkrs.info/p47` | **Licence unclear** — built on the copyrighted printed БКРС (Oshanin) | Best zh→ru content in existence, weakest provenance here. Keep it out of the default catalogue (§9). |
| **CC-Canto** | yue→en | 20 k Cantonese + 110 k CC-CEDICT with human-checked Cantonese readings | CC BY-SA 3.0 | Only if Cantonese ever matters. |
| **Unihan**, Make Me a Hanzi, HSK lists, Jun Da / SUBTLEX-CH | characters, frequency | — | Various open | The §07 Chinese subsystem, deliberately deferred. |
| **Pleco** | zh→en | Best-in-class commercial | Proprietary, no API | A reference point, not an integration. |

---

## §5 · German, French, Japanese — a representative sample

Chosen to span the real range rather than the popular one: **German** has the best open bilingual
data of any pair; **French** has superb institutional dictionaries, none redistributable;
**Japanese** has the best-licensed open dictionary project anywhere plus a non-Latin script.

### German — the well-supplied case

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **FreeDict `deu-eng` / `eng-deu`** (from Ding) | de↔en | **517,534 / 460,315 headwords** | GPL-ish | The **largest open bilingual pair in existence**. Nothing else comes close. |
| **kaikki**, English edition / `dewiktionary` | de→en / de→de | 631,714 senses; de edition 2.8 GB (287.9 MB gz) | CC BY-SA 4.0 | Full structure including separable verbs. |
| **DWDS** | de→de | Free API: `/api/frequency`, `/api/wb/snippet`, `/api/ipa`, article feeds; word-list JSON/XML downloads | Terms of use apply per endpoint | Academic-grade contemporary German plus Grimm's DWB. The best free monolingual API of any language surveyed. |
| **OpenThesaurus** | de→de synonyms | — | CC-GNU LGPL | Drop-in synonym layer. |
| **dict.cc** | de↔en | 1.3 M+ entries, 1.5 M+ audio | **Proprietary since 2005** (was GPL) | Redistribution restricted. Link out only. |

### French — the locked-up case

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **kaikki**, English edition / `frwiktionary` | fr→en / fr→fr | 458,908 senses; fr edition **6.3 GB** (681.5 MB gz — largest non-English edition) | CC BY-SA 4.0 | The only large open French resource in both directions. |
| **TLFi** (ATILF/CNRS) | fr→fr | 100 k words · **270 k definitions · 430 k examples** | Free to consult, **not redistributable** | The best French dictionary in existence. Link out to CNRTL. |
| **Dictionnaire de l'Académie française**, 9th ed. | fr→fr | Completed Nov 2024, fully online with the 4th and 8th editions | Consultation only | Prestige reference; link out. |
| **DBnary / WikDict `fr-*`** | fr→many | Part of the 26-language set | CC BY-SA 4.0 | Same pipeline as everything else. |
| **Lexique 3.83** | fr frequency/phonology | ~140 k forms | Open | Useful for difficulty ranking. |
| **FreeDict `fra-eng` / `eng-fra`** | fr↔en | **8,505 / 8,799 headwords** | GPL-ish | Effectively unusable. |

France is the clear case where the good dictionaries are not licensable and the licensable one is
Wiktionary. Plan accordingly.

### Japanese — the well-run case

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **JMdict** (EDRDG) | ja→en/fr/de | ~100,000 entries; "New Generation" distribution began May 2026 | **CC BY-SA 3.0** | The model for what an open dictionary project should be: versioned XML, sense-tagged, POS-tagged, priority-flagged, maintained for thirty years. `jmdict-simplified` publishes clean JSON. |
| **KANJIDIC2** | kanji | 6,355 kanji at JIS X 0208; 13 k+ in kanjidic2 | CC BY-SA 3.0 | Readings, meanings, stroke counts, grade, JLPT level. |
| **JMnedict** | proper names | ~740,000 named entities | CC BY-SA 3.0 | Names — the thing every other language's open dictionaries lack. |
| **FreeDict `jpn-eng`** | ja→en | 173,747 headwords | GPL-ish | JMdict-derived. |
| **kaikki**, English / `jawiktionary` | ja→en / ja→ja | 236,443 senses | CC BY-SA 4.0 | Complements JMdict on rarer senses. |
| **Jisho.org** | ja→en | JMdict frontend | Unofficial JSON API | Convenient; not a dependency. |

---

## §6 · Every other language — six hubs, not two hundred dictionaries

No language needs individual research. Six hubs cover essentially all of them; everything else is a
link-out.

| Hub | What it gives | Coverage | Licence | Shape |
|---|---|---|---|---|
| **kaikki.org / wiktextract** | Full structured entries: senses, tags, domains, IPA, inflected forms, examples, translations | **~20 Wiktionary editions** extracted (en, zh, nl, fr, el, de, id, it, ja, ko, ku, ms, ru, pl, pt, es, th, tr …); the English edition alone covers hundreds of languages | CC BY-SA 4.0 + GFDL | JSONL |
| **DBnary → WikDict** | Bilingual translation pairs, cleaned and cross-checked | 26 languages, **17.7 M translations** | CC BY-SA 4.0 | RDF (OntoLex-Lemon) → StarDict / SQLite / TEI P5 / Kobo |
| **FreeDict** | Curated bilingual dictionaries, some very large | ~150 dictionaries, rebuilt through 2025-11 | GPL-ish, per-dictionary | TEI P5 → dictd / StarDict / slob |
| **PanLex** | Bare translation pairs, panlingual | **~9,000 language varieties**, 20 M lexemes, **1.1 B pairs** | **CC0** | CSV / JSON monthly snapshots + `api.panlex.org` |
| **Open Multilingual Wordnet** | Sense graphs linked through the English ILI | 60 wordnets / 49 languages + auto-extracted for 150+ | Apache-2.0 packaging; per-wordnet licences vary | LMF / GWA XML; Python `wn` |
| **Tatoeba** | Human sentence pairs, for examples rather than definitions | **13.4 M sentences / 429 languages** | CC BY 2.0 FR, some CC0 | TSV |

Plus one **pre-built** channel: the Yomitan ecosystem (`kaikki-to-yomitan` →
`wiktionary-to-yomitan`) publishes ready-made zips for 100+ languages at
`huggingface.co/datasets/daxida/wty-release` — **2.32 GB** for the whole `latest/dict` set,
CC BY-SA 4.0, a German→English dictionary being ~21 MB. The fastest route to a per-language
artifact without running wiktextract over a 6 GB dump.

---

## §7 · Formats, and what Acervo should actually store

### Separate the content model from the container

The first draft of this section proposed one canonical relational schema with an adapter per source.
Two objections to that are correct and change the design:

1. **A bespoke schema per source is an unbounded maintenance surface.** Anyone reusing the project
   who wants a dictionary Acervo has not mapped must either extend the compiler or go without, and
   each new source invites its own corner cases.
2. **Relational normalisation is the wrong shape for something read whole.** A dictionary entry is
   always fetched entirely, by key, and rendered. Splitting it across five tables buys query
   flexibility nobody needs and pays for it in rows, indexes and bytes.

But the container requirement does not go away: a 2.69 GB JSONL file cannot be scanned per keystroke
on a phone, so *something* must provide keyed random access and prefix search.

> ### DECISION — SUPERSEDED by §11
> *Measured and rejected. SQLite costs 1.66× the packed-blob container for the same corpus; the
> replacement decision is in §11. The two-tier payload idea survives, but not its rationale — HTML
> turned out to be **smaller** than the mapped fields, not larger. Kept here because §11 is only
> legible as a correction to it.*
>
> **SQLite as a dumb container, not as a relational model. Two tiers of payload.**
>
> ```
> meta(key, value)                           -- name, source, licence, attribution, built_at
> entry(headword, lemma, tier, payload)      -- payload: compressed bytes
> index on headword, index on lemma
> ```
>
> `tier` is `fields` (the source's own structured JSON, lightly normalised) or `html` (a rendered
> fragment). **There is no per-source relational schema at all.**
>
> **Because** this removes the maintenance surface — adding a source becomes "can PyGlossary read
> it? then it is `html`" — while keeping the keyed access a phone needs. SQLite is the cheapest such
> container: it is in the Python standard library, ships to the browser as `sqlite-wasm`, and is one
> file to download and delete.
>
> **This also means** SQLite is not the bloat risk it appears to be. Column names are stored once in
> the schema, whereas JSONL repeats every key on every one of 1.35 M records — key repetition alone
> is a large share of that 2.69 GB. The genuine bloat risks are elsewhere and are avoidable: FTS5
> indexes can rival the size of the text they index, so full-text search stays **optional per
> dictionary** (headword and lemma B-trees are small), and payloads are compressed **per row** so
> one entry can be decompressed without touching the rest. A zstd dictionary trained on a sample
> recovers most of the cross-row redundancy that per-row compression gives up.

Alternatives considered:

| Approach | Why not |
|---|---|
| Raw JSONL plus a sidecar offset index | Works, but the index is hand-rolled, there is no prefix search, and every platform needs its own byte-range reader. SQLite provides all three. |
| Yomitan zip imported into IndexedDB | Requires unpacking row-by-row before first use, and puts dictionary bulk in the same store as the replica, which §04 keeps precious. |
| Whole-file gzip of JSONL | No random access. Decompressing 2.69 GB to answer one lookup. |
| `sql.js-httpvfs` over HTTP Range | Not an alternative — **keep it** for the online path, where it serves a server-side file without a lookup route. |

### Which formats map to Acervo's model, and which do not

**Tier 1 — `fields`.** Field-structured at the source, so one mapper produces something the existing
article components can render. These are worth the mapping effort.

| Format | Mapper effort | Why it maps |
|---|---|---|
| **wiktextract JSONL** | One mapper, reused everywhere | Near-isomorphic to Acervo's model already: `word`, `pos`, `sounds[].ipa`, `senses[].glosses`, `senses[].tags`, `forms[]`. This is the mapper that matters — it covers ~20 Wiktionary editions and hundreds of languages. |
| **Wiktionary-shaped JSON APIs** (freedictionaryapi.com, Wikimedia REST) | ~~Shares the above~~ **one small connector each** | Same upstream data but *three different field shapes* — measured in §11.5, which withdraws this claim. |
| **CC-CEDICT** | ~30 lines | Fixed line grammar: traditional, simplified, `[pinyin]`, `/gloss/gloss/`. |
| **jmdict-simplified JSON** | Small | Sense-tagged, POS-tagged JSON. |
| **ECDICT CSV** | Small | Columnar, with frequency and exam metadata worth keeping. |
| **Yomitan zip** | Medium (~60 lines) | Its structured content is a tree of typed nodes — cheap to walk, and cheap to render straight to HTML if mapping proves fiddly. |

**Tier 2 — `html`.** The payload is an opaque text or HTML blob at the source, so there is nothing to
map. PyGlossary reads all of these; convert to HTML, sanitise, and display it in a styled container
with Acervo's fonts and spacing.

StarDict · slob (Aard2) · MDict `.mdx` · ABBYY DSL · dictd · Babylon BGL · Lingoes · Zim ·
XDXF · TEI P5.

XDXF and TEI P5 are genuinely semantically marked up and *could* be mapped, but adoption is thin
enough that HTML is the right call until a specific dictionary justifies otherwise.

**Tier 3 — link out.** No redistributable file and no API: RAE / DLE, TLFi, Dictionnaire de
l'Académie française, dict.cc, Pleco, Linguee, SpanishDict. These get a link in the UI and nothing
else.

### The online-API gap

The format tiering above is clean for files because **PyGlossary is a universal reader**. There is no
equivalent for APIs: every one needs a hand-written connector, and that is precisely the kind of
per-source maintenance the tiering exists to avoid.

The mitigation is to exploit shared upstreams rather than write many connectors:

- **freedictionaryapi.com and Wikimedia REST are both Wiktionary-derived**, so ship these two and
  stop: one primary, one fallback. But *not* "zero new mapping logic" — §11.5 measured three
  different field shapes across the three Wiktionary-derived sources. Budget ~40 lines each.
- Wordnik, WordsAPI, Merriam-Webster and Lexicala each need a bespoke connector. Add one only when a
  concrete gap in the free sources appears — not speculatively.
- Rate limits are not a constraint at personal scale (§2). Do not prefetch; look up on demand.

### Sizes — measure, do not assert

An earlier draft listed estimates (≈150–250 MB for kaikki English, ≈120–200 MB for Spanish). Those
were guesses and they look implausibly small next to the 2.69 GB source, so they are removed. The
reasoning behind them, stated so it can be falsified by the spike:

1. Stripping wiktextract to display fields drops categories, etymology templates, `head_templates`,
   wikitext residue and sense ids — guessed at 85–90 % of the bytes.
2. Per-row compression of what remains — guessed at roughly half again.
3. 2.69 GB → ~300 MB → ~150 MB.

Any link in that chain could be wrong by 2× or more, in either direction. §10's spike measured it
instead: **35–38 MiB** for the whole Spanish Wiktionary (838,769 headwords), so the guess was about
4× too high. See §11.1.

---

## §8 · PWA storage limits

**A non-issue at plausible sizes; a real constraint only past ~1 GB.**

| Platform | Per origin | Overall | Eviction |
|---|---|---|---|
| **Chrome / Edge / Chrome Android** | up to **60 % of total disk** | 80 % of disk | LRU under storage pressure; best-effort origins only |
| **Safari / WebKit browser tab**, iOS 17+ & macOS 14+ | up to **60 % of total disk** (WebKit's own figure; MDN and some secondary sources report ~20 % for tabs) | 80 % | LRU plus the 7-day rule |
| **Safari Home Screen / Dock web app** (installed PWA) | same as a browser app | 80 % | Has its **own days-of-use counter**, separate from Safari's |
| **Embedded WebKit** (WKWebView in `macos/`) | **15 % of total disk** | **20 %** | Same policy |
| **Firefox** | best-effort `min(10 % of disk, 10 GiB)` per site group; **persistent up to 50 %** | — | LRU |
| `localStorage`, everywhere | **5 MiB** | — | — |

Consequences for Acervo:

1. **The pre-iOS-17 1 GB cap is gone.** Since iOS 17 / macOS Sonoma the quota is computed from disk
   size with no user prompt. Advice that iOS PWAs get 50 MB is obsolete.
2. **Call `navigator.storage.persist()` once** after a dictionary is installed. Persistent-mode
   origins are exempt from eviction entirely. Chrome and Safari decide silently from engagement
   history; Firefox prompts. The single most important line of code in the feature.
3. **The 7-day rule is the real risk, not the quota.** An origin with no user interaction in the last
   seven days of browser use has its script-written storage deleted. An installed Home Screen web app
   counts its own days of use, so a weekly habit is safe — but `persist()` is what makes it certain.
4. **`macos/` is the tightest target, not iOS.** WKWebView is a "non-browser app": 15 % per origin,
   20 % overall. On a 256 GB Mac that is still ~38 GB.
5. **Measure, never assume.** `navigator.storage.estimate()` returns `{usage, quota}` and belongs in
   the Dictionaries settings pane before an install. Sources disagree about Safari's tab-origin
   percentage, and values are padded against fingerprinting.
6. **Guard `QuotaExceededError`** and fail the install cleanly, leaving already-installed dictionaries
   untouched — the "fail loudly, change nothing" discipline of §04.

Storage headroom is therefore *not* the binding constraint; **download size and install time are**.
A 150 MB download over a phone connection is the thing a person actually notices, which is another
reason §7's compactness work matters and §10's spike measures it.

---

## §9 · Licensing — Acervo ships a catalogue, not dictionaries

The share-alike analysis in the first draft assumed Acervo would distribute dictionary data. It will
not, and that changes the obligation substantially.

> ### DECISION
> **Ship a catalogue of pointers. The user chooses what to install, and the download happens between
> them and the source.**

A tracked `dictionaries/catalogue.json` lists what is available — id, display name, languages and
direction, tier (`fields` / `html` / `link`), source URL, format, licence, approximate bytes, notes.
The application reads it, offers the list per vocabulary, and installs on request. Acervo distributes
the *list*, which is a set of facts and URLs.

What remains a real obligation, and is cheap:

- **Show attribution and licence wherever an external entry is rendered.** This is what CC BY-SA asks
  of anyone displaying the content, distributor or not, and the `meta` table already carries it.
- **Honour API terms**: User-Agent on Wikimedia, no prefetch storms, no circumventing rate limits.
- **Do not ship a scraper.** RAE and friends stay Tier 3 link-outs regardless of how good they are.
- **Keep unclear provenance out of the default catalogue.** BKRS is the case in point: excellent
  zh→ru content, murkiest licensing here. Someone can add it themselves; Acervo should not suggest it.

Licence classification, kept for catalogue metadata rather than as a compliance exercise:

| Licence | Sources |
|---|---|
| **CC0** | PanLex |
| **MIT** | ECDICT |
| **CC BY 4.0** (no share-alike) | Open English WordNet |
| **CC BY 3.0** | MCR non-English wordnets |
| **CC BY-SA 3.0 / 4.0** | Wiktionary/kaikki, CC-CEDICT, JMdict/KANJIDIC/JMnedict, WikDict/DBnary, CC-Canto |
| **GPL** | Mueller, most FreeDict |
| **Proprietary / unclear** | RAE DLE, dict.cc, TLFi, Académie française, Collins, Oxford, Merriam-Webster content, BKRS, most MDict and DSL files |

**Catalogue maintenance.** Start with only the languages in use — `es` and `en` — and grow on demand.
A monthly script that HEADs every catalogue URL and reports what moved or died is enough; it is a
cron-able check, not a service.

---

## §10 · Build order

### Spike 0 — measure, then choose

**Before any application code.** The open questions are all empirical, and §7's decision is stated
with enough specificity to be wrong. Scope this narrowly: a throwaway script under `scripts/`, a
table of numbers, and a go/no-go.

**Inputs, cheapest first**

| Input | Why this one |
|---|---|
| **CC-CEDICT** (~9.5 MB) | The control. Trivial grammar, small, Tier 1 — if the path does not work here it works nowhere. |
| **kaikki `eswiktionary`** | The real case: Spanish is the language actually in use, and it is the 37-sense `picar` source. Big enough for the size question to mean something. |
| **One Tier 2 dictionary** — FreeDict `eng-rus` as StarDict or slob | Proves the PyGlossary → HTML path and gives the `html` tier a real byte count. |
| **freedictionaryapi.com**, ~20 headwords | Proves the online path and, critically, whether the *same* Tier 1 mapper serves it. |

**What to measure**

1. **Bytes at each stage** for both Tier 1 inputs: source → stripped fields → SQLite with per-row
   gzip → per-row zstd → zstd with a trained dictionary → each of those again with and without FTS5.
   This settles whether the ~150 MB guess in §7 was anywhere near right.
2. **Lookup latency** for exact headword, lemma, and prefix search, on the largest artifact.
3. **Render fidelity**: does the mapped `fields` payload actually satisfy the existing `Article` view
   model, and which fields have no home? Enumerate the drops rather than guessing.
4. **PyGlossary in practice**: does it read the chosen Tier 2 file without hand-holding, how big is
   the HTML, and does the output need sanitising before display?
5. **Mapper reuse**: one function mapping both kaikki JSONL and the API response, or two?

**Deliverable.** A short results section appended to this document with real numbers, plus a decision
on the container. If SQLite loses on size to something simpler, say so and take the simpler thing —
the decision in §7 is a hypothesis, not a commitment.

### Then, in order

- **Stage 1 · the catalogue and the compiler.** `dictionaries/catalogue.json`, plus
  `scripts/build_dictionary.py` reduced to what the spike proved: one Tier 1 mapper for wiktextract
  shape, a handful of tiny Tier 1 parsers, and a PyGlossary shell-out for Tier 2. No per-source
  schemas.
- **Stage 2 · the reader and the server route.** `web/src/dictionary.ts` — a pure interface,
  `lookup` / `search` / `installed`, with two transports behind it chosen by whether the dictionary
  is installed locally, mirroring how `sync.ts` owns the graph transport. A PocketBase hook route
  `GET /api/acervo/v1/dictionary/{id}/lookup` opens the same file server-side. No collections, no
  records, no revisions, no sync.
- **Stage 3 · the interface.** Search gets an "Other dictionaries" section below a separator, which
  becomes the answer when there are no local results. `LexemeArticle.tsx` gets a read-only reference
  section. A dictionary entry with no lexeme gets "Add to my words", seeding Capture with the
  headword. Settings gets a Dictionaries pane with size, licence, install/remove,
  `storage.estimate()` and the `persist()` request.
- **Stage 4 · grounding.** Postponed indefinitely, gated on
  [acervo-grounding-spike.md](acervo-grounding-spike.md), and re-scoped by §1: the question is
  whether the *shown* senses improve, not whether coverage increases.

### The interface may flex to fit the data

Two accommodations are explicitly acceptable rather than compromises, and they are what make the
tiering affordable:

- **Render an `html` payload as HTML** — sanitised, in Acervo's fonts and spacing, without pretending
  it is a structured entry.
- **Drop source fields that have no home** in the article view rather than growing the view model to
  accommodate every dictionary. External entries are a reference surface, not a second data model.

### Explicitly out of scope

The Chinese subsystem (§07); any scraper; bundling BKRS or anything else of unclear provenance;
per-entry caching of dictionary data; bespoke connectors for APIs beyond the two Wiktionary-shaped
ones; and anything that puts a dictionary row in PocketBase.

---

## Verification

```bash
# Spike 0 — the control case first
.venv/bin/python scripts/spike_dictionary_sizes.py --source cc-cedict --in cedict_ts.u8
#   reports: source bytes, stripped bytes, sqlite+gzip, sqlite+zstd, +/- FTS5, lookup ms

# then the real case
.venv/bin/python scripts/spike_dictionary_sizes.py --source wiktextract-es --in es-extract.jsonl

# the Tier 2 path
pyglossary --read-format=Stardict --write-format=Html eng-rus.ifo eng-rus.html

# the online path, same mapper
.venv/bin/python scripts/spike_dictionary_sizes.py --source freedictionaryapi \
  --words picar,desmayarse,balsa --compare-mapper wiktextract-es

# Stage 2 onward — the invariant that matters
npm --prefix web run test && npm run test:hooks
npm --prefix web run build && npm run test:pwa
#  · install a dictionary, then stop PocketBase → lookup and search must still work
#  · no dictionary installed and the server down → the section reports unavailable,
#    the local list is unaffected, nothing is written
#  · DevTools → Application → Storage: confirm persisted=true and usage after install
```

---

## Sources

**Wiktionary extraction** — [kaikki raw data](https://kaikki.org/dictionary/rawdata.html) ·
[language index](https://kaikki.org/dictionary/index.html) ·
[Spanish](https://kaikki.org/dictionary/Spanish/index.html) ·
[ru edition](https://kaikki.org/ruwiktionary/index.html) ·
[es edition](https://kaikki.org/eswiktionary/index.html) ·
[wiktextract](https://github.com/tatuylonen/wiktextract) ·
[Wiktionary:Copyrights](https://en.wiktionary.org/wiki/Wiktionary:Copyrights) ·
[es.wiktionary `picar`](https://es.wiktionary.org/wiki/picar)

**English** — [Open English WordNet](https://en-word.net/downloads) ·
[english-wordnet](https://github.com/globalwordnet/english-wordnet) ·
[GCIDE](https://gcide.gnu.org.ua/) · [Mueller](https://mueller-dict.sourceforge.net/) ·
[OpenRussian](https://en.openrussian.org/dictionary)

**APIs** — [freedictionaryapi.com](https://freedictionaryapi.com/) ·
[dictionaryapi.dev](https://dictionaryapi.dev/) ·
[Wikimedia REST API](https://www.mediawiki.org/wiki/Wikimedia_REST_API) ·
[Wikimedia rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits) ·
[Merriam-Webster](https://dictionaryapi.com/) · [Wordnik](https://developer.wordnik.com/) ·
[Lexicala](https://api.lexicala.com/) · [DWDS API](https://www.dwds.de/d/api)

**Hubs** — [FreeDict](https://freedict.org/downloads/) ·
[WikDict](https://www.wikdict.com/page/download) ·
[wikdict-gen](https://github.com/karlb/wikdict-gen) · [PanLex](https://panlex.org/) ·
[Open Multilingual Wordnet](https://omwn.org/) · [Tatoeba](https://tatoeba.org/en/downloads) ·
[MCR 3.0](https://adimen.si.ehu.es/web/MCR) ·
[doozan/spanish_data](https://github.com/doozan/spanish_data)

**Chinese & Japanese** — [CC-CEDICT](https://cc-cedict.org/wiki/) ·
[MDBG download](https://www.mdbg.net/chinese/dictionary?page=cc-cedict) ·
[CC-Canto](https://cantonese.org/download.html) ·
[ECDICT](https://github.com/skywind3000/ECDICT) ·
[moedict-data](https://github.com/g0v/moedict-data) ·
[BKRS converters](https://github.com/ukoloff/bkrs) ·
[JMdict](https://www.edrdg.org/jmdict/jmdictart.html) ·
[EDRDG licence](https://www.edrdg.org/edrdg/licence.html)

**European** — [dict.cc word list](https://www.dict.cc/?s=about%3Awordlist) ·
[TLFi](https://www.atilf.fr/ressources/tlfi/) ·
[CNRTL](https://www.cnrtl.fr/dictionnaires/modernes/)

**Formats & tooling** — [PyGlossary](https://github.com/ilius/pyglossary) ·
[format list](https://github.com/ilius/pyglossary/wiki/Formats) ·
[GoldenDict-ng format notes](https://xiaoyifang.github.io/goldendict-ng/dictformats/) ·
[making Yomitan dictionaries](https://github.com/yomidevs/yomitan/blob/master/docs/making-yomitan-dictionaries.md) ·
[term-bank schema](https://github.com/yomidevs/yomitan/blob/master/ext/data/schemas/dictionary-term-bank-v3-schema.json) ·
[wiktionary-to-yomitan](https://github.com/yomidevs/wiktionary-to-yomitan) ·
[wty-release](https://huggingface.co/datasets/daxida/wty-release) ·
[Yomitan supported languages](https://yomitan.wiki/supported-languages/) ·
[sql.js-httpvfs](https://github.com/phiresky/sql.js-httpvfs)

**Storage** — [WebKit: Updates to Storage Policy](https://webkit.org/blog/14403/updates-to-storage-policy/) ·
[MDN: Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)

**Lexicography research** — [Lew, ChatGPT as a COBUILD lexicographer](https://www.nature.com/articles/s41599-023-02119-6) ·
[de Schryver, Generative AI and Lexicography](https://academic.oup.com/ijl/article-abstract/36/4/355/7288213) ·
[100 scholarly echoes](https://academic.oup.com/ijl/article/doi/10.1093/ijl/ecag021/8753141) ·
[Dictionaries and lexicography in the AI era](https://www.nature.com/articles/s41599-024-02889-7) ·
[arXiv 2404.06224](https://arxiv.org/abs/2404.06224) ·
[arXiv 2410.03182](https://arxiv.org/abs/2410.03182) ·
[arXiv 2601.01842](https://arxiv.org/abs/2601.01842)

---

## §11 · Spike 0 results

**Status:** measured. Apparatus and raw numbers in
[`experiments/external-dictionaries/`](../experiments/external-dictionaries/). Everything below is
measured on the real corpora unless labelled an estimate.

Corpora: CC-CEDICT (2026-08-31), kaikki `eswiktionary` and kaikki Spanish (English edition),
jmdict-simplified 3.6.2, FreeDict `eng-rus` 2025.11.23 in both TEI P5 and StarDict form, plus
freedictionaryapi and the Wikimedia REST definition endpoint. Sources were chosen to span *formats*
— fixed line grammar, rich JSONL, clean sense-tagged JSON, semantic XML, opaque binary, JSON API —
rather than languages.

### The four headline findings

1. **The `fields` tier is not smaller than HTML — it is larger.** On every source measured, a
   rendered HTML fragment costs less than the mapped `ArticleDraft` JSON, because the JSON repeats
   its keys on every sense while the HTML does not. Whatever justifies mapping, it is not space.
2. **Latency is not a constraint and never becomes one.** Exact lookup p95 is 0.01–0.25 ms across
   every container at every scale tested. The stated tolerance was ~1 s. Size can decide alone.
3. **§7's ~150 MB guess was about 4× too high.** The whole Spanish Wiktionary — 838,769 headwords —
   lands at **35–38 MiB** installed. Storage is a non-issue at this size; §8's conclusion is
   reinforced, not merely preserved.
4. **The headword index, not the payload, is now the thing worth optimising.** At full scale the
   index is 21.2 MiB against a 16–19 MiB compressed payload. Front-coding the sorted keys and
   varint-packing the records takes it to **5.7 MiB** — a ~40 % cut to the whole artifact, and by
   some distance the highest-leverage work remaining.

> ### DECISION — supersedes the container decision in §7
> **A packed blob plus a sidecar index, block-compressed at 256 entries, read with `fflate`.
> Not SQLite.**
>
> ```
> <name>.dict   concatenated payloads, deflate-compressed in 256-entry frames
> <name>.idx    sorted headwords + one fixed record per entry (front-coded — see below)
> <name>.json   meta: name, source, licence, attribution, built_at
> ```
>
> **Because** it is the smallest total on the device and the fewest moving parts at once. SQLite
> costs **1.53× more** than the recommended packed build for the same corpus (58.3 MiB against
> 38.0 MiB, and 1.66× against the smallest packed build at 35.1 MiB): a
> 1.3 MB wasm engine, plus page-alignment overhead on every row. `fflate` is already a `web/`
> dependency, is ~8 KB, and supports the shared-dictionary API in both directions, so the read path
> ships no new engine at all. A lookup is one binary search and one 256-entry frame decode — about
> 50 KiB transient, which is the memory budget a phone actually cares about.
>
> **One container serves both mobile and the server.** The server has no space problem and could
> use anything, but the same file read by the same code is worth more than a second format that
> saves nothing anyone is short of. `sql.js-httpvfs` is no longer needed for the online path either
> — an HTTP Range read of the packed blob is the same operation.

### §11.1 · Container — full corpus, kaikki `eswiktionary`, 838,769 headwords

`fields` payload, 229.3 MiB raw. "Total device" is artifact + trained dictionary + the library a
client must ship to read it.

| Container | Codec | Blob | Index | Library | **Total device** | vs best | RAM/lookup | exact p95 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| packed+block256 | zstd19+dict | 16.0 | 18.7 | 340 KiB | **35.1 MiB** | 1.00× | 50 KiB | 0.25 ms |
| packed+block256 | zstd19 | 18.0 | 18.7 | 8 KiB | **36.7 MiB** | 1.05× | 50 KiB | 0.24 ms |
| packed+block256 | deflate+dict | 18.4 | 18.7 | — | **37.2 MiB** | 1.06× | 50 KiB | 0.25 ms |
| **packed+block256** | **deflate** | **19.3** | **18.7** | **—** | **38.0 MiB** | **1.08×** | **50 KiB** | **0.25 ms** |
| sqlite+block256 | deflate | 57.1 | — | 1,275 KiB | **58.3 MiB** | 1.66× | 164 KiB | 0.13 ms |

**Plain `deflate` is the recommendation despite not winning.** It is 8 % larger than the best
result and needs no library beyond what is already bundled. zstd-with-a-trained-dictionary saves
2.9 MiB but costs a ~340 KB wasm build, because `fzstd` (the 8 KB pure-JS decoder) cannot supply a
custom dictionary — so the real comparison is 35.1 against 38.0 MiB, and 2.9 MiB does not justify a
second compression engine on the read path. Revisit only if many dictionaries are installed at once.

Block size matters more than codec choice: 256-entry frames roughly halve per-row compression, and
once blocked, `deflate` and `zstd19` are within 8 % of each other. Brotli-11 was measured and
discarded — never competitive after its engine cost, and the Python binding exposes no
custom-dictionary API at all, so that variant is impractical by construction.

### §11.2 · The index is the remaining prize

| Index | Bytes | Note |
|---|---:|---|
| As built (sorted keys + 16-byte records) | 21.2 MiB | keys 8.4 + records 12.8 |
| Front-coded keys | 2.5 MiB | 29 % of raw — sorted headwords share long prefixes |
| Varint records | 3.2 MiB | with a fixed block size the block number is `index // 256` |
| **Both applied** | **5.7 MiB** | **saves 15.5 MiB, ~40 % of the artifact** |

This is Stage 1 work, not a research question. It is the single largest remaining size win and it
needs no new dependency.

### §11.3 · Representation — is the mapper worth writing?

5,000-entry samples. "Mapped" is the share of source entries that produce an `ArticleDraft` at all.

| Source | Format family | fields MiB | html MiB | html ÷ fields | Mapped | Dropped fields | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| `cc-cedict` | fixed line grammar | 1.3 | 0.7 | 0.56× | 100.0 % | 1 | **map** (~30 lines) |
| `jmdict-eng` | sense-tagged JSON | 1.4 | 0.5 | 0.36× | 98.0 % | 6 | **map** (~45 lines) |
| `freedict-eng-rus-tei` | semantic XML | 1.0 | 0.4 | 0.41× | 97.8 % | 0 | **map** (~35 lines) |
| `kaikki-es-es` | rich JSONL | 2.8 | 2.1 | 0.75× | 97.5 % | 15 | **map** (~90 lines, reused) |
| `kaikki-es-en` | rich JSONL | 1.6 | 1.2 | 0.75× | 95.0 % | 29 | **map** (same mapper) |
| `freedict-eng-rus-stardict` | opaque binary | — | 1.8 | — | 0 % | all | **html only** |

**Every mapped entry is a valid article.** Run through the application's own `parseArticle` — not a
re-implementation — acceptance is **100 % on all seven sources**, so the failure mode is never a
malformed article, only an entry that produces none at all.

What actually costs entries is **Acervo's closed seven-value `pos` enum**. Wiktextract offers
`det`, `prep`, `conj`, `pron`, `num`, `particle`, `article`, `character`, `prefix`, `suffix`;
jmdict offers 17 more; TEI offers `pn`, `prefix`, `suffix`, `pronoun`. There is no escape-hatch
field, so those entries are dropped rather than mistranslated. That is the honest behaviour and it
costs 2–5 % of entries.

Two source-specific notes worth keeping:

- **CC-CEDICT carries no part of speech at all.** The mapper invents `pos: noun`. This is the one
  place something is fabricated, and it is flagged rather than hidden. Its traditional-character
  form is also dropped — a variant axis a single lexeme has nowhere to put.
- **`es→en` and `es→es` both map, contrary to the concern in §3.** The English edition's glosses
  are written as an English definition with `definitionLang: "en"` rather than pretended to be
  Spanish, so nothing is invented. `parseArticle` requires a definition per sense but enforces no
  minimum on glosses — `validateGraph`'s stricter rule does not apply, because external entries are
  render-only and never enter the graph.

### §11.4 · Tier 2, and PyGlossary in practice

The opaque-binary path works and produces usable HTML, confirming the fallback is real: 5,000
StarDict entries → 1.8 MiB of HTML, 0.3 MiB installed. Two practical frictions:

- **PyGlossary 5.4.2 renamed `Glossary.read` to `directRead`**, and silently disables seven plugins
  — including **XDXF** — when `lxml` is absent, printing a warning rather than failing. Anything
  depending on those formats must install `lxml` explicitly.
- **Its HTML needs restyling, not merely sanitising.** FreeDict StarDict payloads carry
  presentational markup — `<font color="gray">` for IPA, `<font class="grammar" color="green">` for
  part of speech — whose inline colours would fight Acervo's theme in both light and dark. Strip
  `<font>`, keep the structure, restyle from the class names where they exist.

Notably these payloads *do* contain IPA, part of speech, definition and translation as recoverable
structure. They could be mapped by parsing the HTML — and that is exactly the case where the answer
is no: extracting fields from presentational markup is unbounded maintenance for a source that
renders perfectly well as-is.

### §11.5 · Online sources

| API | Requests | Misses | Mapped | p50 | max | Shape |
|---|---:|---:|---:|---:|---:|---|
| `freedictionaryapi` | 9 | 1 | 6 | 131 ms | 459 ms | `entries[].partOfSpeech`, `senses[].definition` (string) |
| `wikimedia-rest` | 9 | 2 | 6 | 254 ms | 679 ms | `{lang: [{definitions: [{definition: HTML}]}]}` |

**§7's claim that these "share the offline wiktextract mapper" is wrong and is corrected here.**
Three Wiktionary-derived sources, three different field shapes: wiktextract uses `pos`,
`sounds[].ipa` and `senses[].glosses` (a *list*); freedictionaryapi uses `partOfSpeech`,
`pronunciations[].text` and `senses[].definition` (a *string*); Wikimedia REST returns definitions
as **HTML fragments with `mw:WikiLink` markup**, so its `fields` path must strip markup — and its
raw HTML is 2.4× larger than the mapped fields. Budget one small connector each, roughly 40 lines,
not one shared mapper.

Two further practical notes: the definition endpoint exists **only on `en.wiktionary.org`**, keyed
by term with languages inside the response — a per-language host 404s. And both APIs return far
more senses than §1 wants shown: **7.7 and 8.2 senses per entry** against the three-to-five target.
Whatever renders them must truncate.

### §11.6 · What this changes

- **§7's container DECISION is superseded** by §11's. SQLite was a reasonable hypothesis and it
  lost on measurement, at 1.66× the size for no benefit that matters here.
- **§7's "same mapper" claim about the APIs is withdrawn** (§11.5).
- **§7's removed ~150 MB estimate is replaced by 35–38 MiB measured** for the largest corpus.
- **The `fields`/`html` tiering survives, but its rationale is inverted.** Mapping is not a space
  optimisation — HTML is smaller. Mapping buys *rendering in Acervo's own article view*, and it is
  worth it exactly where a source is already field-structured, which the measurements show is four
  of the five non-opaque formats at under 100 lines each.
- **Answering the question that motivated the spike:** yes, build the ingest path — but only the
  wiktextract mapper is load-bearing, since it covers ~20 Wiktionary editions and hundreds of
  languages. The small parsers are cheap enough to add on demand, and HTML remains the guaranteed
  fallback for everything opaque.

### §11.7 · Not measured

`probe.html` reports what a device can actually do — `DecompressionStream` formats, OPFS and
`createSyncAccessHandle`, `storage.estimate()`, whether `fflate` round-trips a dictionary-compressed
payload on-device, and decode throughput. **It has not yet been run on a phone or in the `macos/`
WKWebView host.** Until it is, the read path is verified only on desktop Python, and the OPFS
assumption behind the packed container is inference rather than measurement. That is the one gap
before Stage 1 starts.

IndexedDB is reported as a payload floor only; its true per-record overhead is invisible from
Python and needs the same probe.
