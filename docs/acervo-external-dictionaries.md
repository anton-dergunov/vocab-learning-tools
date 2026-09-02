# External dictionaries — source research

**Status:** research, nothing built. Design §08 defines the storage stance and closes with "out of
scope for this iteration". This document is the survey that would let it be brought into scope:
which published dictionaries Acervo can read, under what licence, in what format, and how much of
one fits on a phone.

Two separate needs push toward published dictionaries:

1. **Grounding.** Design §09 names this "the highest-leverage change to the existing pipeline" —
   pass a real sense inventory into the compose prompt so the model becomes a *selector and
   formatter* rather than a knowledge source. Whether it actually improves the entry is the question
   [acervo-grounding-spike.md](acervo-grounding-spike.md) exists to answer; that document owns the
   experiment, and this one supplies the sources and the evidence base it draws on.
2. **Glancing.** LLM composition costs money, needs the server, and takes up to five seconds.
   Looking a word up to *peek* at it should be instant and should work offline — and it is
   independently valuable to check a generated article against a human-compiled one.

Design §08 already fixed the storage stance: external dictionaries are **read-only files, read
directly, never ingested into PocketBase, never in the replica**, and the unit of installation is
"this dictionary on this device". Nothing below contradicts that; this fills in *which files*, *in
what format*, and *what the reader looks like*.

Directions surveyed: `en → en/ru`, `es → es/en/ru`, `zh-Hans → zh/en/ru`, plus German, French and
Japanese as a representative sample. Figures are current as of the August 2026 Wiktionary dumps.

---

## §1 · What the lexicography research says

Directly relevant to "will conditioning on a real dictionary improve the entry?"

| Study | Finding |
|---|---|
| Lew (2023), *ChatGPT as a COBUILD lexicographer*, Humanit Soc Sci Commun | 15 communication verbs, 5-point scale. **AI definitions comparable to human lexicographers**; AI *examples* initially weaker. |
| de Schryver (2023), IJL 36(4):355–387 | Reviews the first ten ChatGPT-in-lexicography studies. A single robust prompt produced entries that "compare favourably to the best practice in dictionary compilation". |
| de Schryver, *100 scholarly echoes of generative AI in lexicography*, IJL (advance) | The follow-up survey — the field has stopped asking *whether* and moved to *how*. |
| arXiv 2404.06224, *Low-Cost Generation and Evaluation of Dictionary Example Sentences* | Zero-shot LLM + masked-LM reranking (FM-MLM) wins **85.1 % of head-to-heads against real Oxford Dictionary example sentences**; the previous best model-generated system won 39.8 %. |
| arXiv 2410.03182, *Generating bilingual example sentences with LLMs as lexicography assistants* | fr / id / tet → en, GDEX criteria. Acceptable quality, **degrades sharply for lower-resourced languages**; inter-annotator agreement is low, and in-context learning aligns the model to one annotator's taste rather than to a standard. |
| arXiv 2601.01842, *Towards Automated Lexicography* | Learner-dictionary definitions via iterative simplification with LLM-as-judge, validated against a professional lexicographer's reference set. |

### How to read it

Design §09's assumption — "the glosses are fine; the example sentences are the weak link" — is now
only half right. Against *published-dictionary* examples, 2024-era models win decisively
(2404.06224). Three things survive scrutiny:

- **Prose quality is not the gap.** Do not condition the model on dictionary *definition text*
  hoping for better writing. The result is stiffer and more telegraphic than what the pipeline
  produces today, and it drags a share-alike obligation onto the output.
- **Sense coverage is the gap.** A model hands over the two or three obvious meanings of `picar` and
  silently drops the rest. English Wiktionary lists **20 senses**. That is a completeness failure
  invisible from inside a generated article, and a sense inventory fixes exactly it.
- **Low-resource degradation is real**, and stops being an abstraction the moment Acervo is used
  outside the top ~30 languages — which is the moment it stops being a personal tool.

**Recommendation: condition on the sense inventory — gloss list, tags, domain, IPA, inflected forms
— and not on the dictionary's prose.** It is a small, cheap block of context, it is legally clean,
and it targets the one deficiency the literature supports. It also sharpens the spike's metric:
score **sense recall** against the source inventory, not prose quality.

---

## §2 · English (`en → en`, `en → ru`)

### Downloadable

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **Wiktextract / kaikki.org**, English extraction | en→en (+ translations to ~everything) | **1,780,480 senses**; raw all-language JSONL 22.9 GB / **2.6 GB gz**; English-only words JSONL ≈ 2.69 GB, ~1.35 M entries | CC BY-SA 4.0 + GFDL | **Core.** The grounding source. Richest structure available anywhere: senses, tags, categories, IPA, forms, etymology, translations, examples. |
| **Open English WordNet 2024** | en→en | 120,630 synsets · 161,705 words · 418,168 relations; 312.6 MB package | **CC BY 4.0** (no share-alike) | Best *sense-relation* graph, and the rare permissive licence in this field. Terse glosses, no register — an enrichment layer, not a reading dictionary. |
| **GCIDE** (Webster's Revised Unabridged 1913 + WordNet additions) | en→en | 124,186 headwords; ~99 k words / 160 k definitions as JSON | Public domain text / GPL packaging | Beautiful prose, **1913 vocabulary**. Charming, wrong for a learner. |
| **kaikki `ruwiktionary`** | en→ru | 103,681 English senses, **definitions in Russian** | CC BY-SA 4.0 | **Core.** The only large source of Russian-language definitions for English words. Genuinely good. |
| **FreeDict `eng-rus`** | en→ru | 62,181 headwords (v2025.11.23) | GPL-ish, per-dictionary | Actively rebuilt. TEI / dictd / StarDict / slob. |
| **Mueller 7th ed.** | en→ru | ~70 k words & expressions | **GPL** | The one solidly-licensed en→ru dictionary. Mid-20th-century vocabulary — label it as dated in the UI. |
| **WikDict `en-ru`** (from DBnary) | en→ru | part of 17.7 M translations / 26 languages | CC BY-SA 4.0 | StarDict, SQLite, TEI P5, Kobo. Clean provenance, machine-derived. |
| **PanLex** | en→ru (+ ~any pair) | 20 M lexemes, ~9,000 varieties, **1.1 B translation pairs** | **CC0** | Bare translation pairs, no definitions, no sense boundaries. The long-tail fallback. |

### Online APIs

| API | Coverage | Free tier | Notes |
|---|---|---|---|
| **freedictionaryapi.com** | Multilingual, Wiktionary-backed, "8.5 M+ words" | **No key, 1,000 req/hour/IP** | Best free option by a distance. CC BY-SA 4.0, attribution required. Not self-hostable. |
| **Wikimedia REST** `…/api/rest_v1/page/definition/{term}` | All Wiktionary editions | 500 req/h unauthenticated (5,000 authed), 200 req/s shared, User-Agent required | Official. Wikimedia Enterprise sells SLA-backed snapshots for commercial reuse. |
| **dictionaryapi.dev** | English only | No key, no published limit | Still up as of 2026. Community-run, no SLA — a fallback, not a dependency. |
| **Merriam-Webster** | Collegiate, Learner's, Spanish-English, Medical | **1,000 queries/day/key, non-commercial, max 2 reference APIs** | High editorial quality. Commercial use requires a deal — a blocker the day Acervo ships as a product. |
| **Wordnik** | AHD, Century, Wiktionary, GCIDE, WordNet — 800 k+ words | Generous free tier | Several dictionaries behind one call; good for a "what do others say" panel. |
| **WordsAPI** | English | 2,500 req/day, then $0.004/req | Cheap, thin content. |
| **Lexicala** (K Dictionaries) | 50 languages, 100 domains — Global / Password / Random House | Commercial only | The serious commercial answer for multilingual: one vendor covering en/es/zh/ru with real sense structure. Worth a quote if Acervo becomes a product. |
| Glosbe public API | — | **Deprecated** | Do not build on it. |

### What the data looks like

```
# kaikki.org / wiktextract JSONL — one JSON object per line, abridged
{"word":"picar","pos":"verb","lang_code":"es",
 "sounds":[{"ipa":"/piˈkaɾ/"}],
 "forms":[{"form":"pico","tags":["first-person","singular","present"]}, …],
 "senses":[
   {"glosses":["to itch (to feel itchy; to feel a need to be scratched)"],
    "tags":["intransitive"]},
   {"glosses":["to mince, to dice"],"categories":["Cooking"]},
   {"glosses":["to get angry, take offence"],"tags":["reflexive"]}, … 20 senses],
 "translations":[…], "etymology_text":"…"}

# CC-CEDICT — one line per entry
漢字 汉字 [Han4 zi4] /Chinese character/CL:個|个[ge4]/

# Open English WordNet
hound, hound dog — (any of several breeds of dog used for hunting,
                    typically having large drooping ears)
```

---

## §3 · Spanish (`es → es`, `es → en`, `es → ru`)

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **kaikki `eswiktionary`** | **es→es** | **1,035,866 Spanish senses**, definitions in Spanish | CC BY-SA 4.0 | **Core.** The monolingual answer, larger than the English edition's Spanish coverage. |
| **kaikki**, English edition | es→en | **874,006 senses**; postprocessed Spanish JSONL 979 MB (deprecated in favour of raw) | CC BY-SA 4.0 | **Core.** Best es→en structured data. Rich tags, dialect labels (`Mexican Spanish`), domains. |
| **WikDict `es-ru`, `es-en`** | es→ru / en | part of 17.7 M translations, 26 languages | CC BY-SA 4.0 | Best *legal* es→ru option, but translation pairs rather than definitions. |
| **kaikki `ruwiktionary`** | es→ru | **only 21,085 Spanish senses** | CC BY-SA 4.0 | Too thin to be a primary es→ru dictionary. |
| **MCR 3.0** (Spanish WordNet, EuroWordNet frame) | es→es + ILI to en | 51 MB SQL dump | **CC BY 3.0** for non-English wordnets | Sense relations plus cross-lingual links. Academic, 2016-vintage, permissively licensed. |
| **doozan/spanish_data** | es→en | Wiktionary + Tatoeba derived, with frequency and lemma data | CC BY-SA | Prebuilt StarDict / slob. Saves a pipeline. |
| **FreeDict `eng-spa` / `spa-eng`** | en→es / es→en | 64,258 / **only 4,502** headwords | GPL-ish | The needed direction is unusable. |
| **Tatoeba** | es↔en/ru examples | **13.4 M sentences, 429 languages** (Apr 2026) | CC BY 2.0 FR, some CC0 | Human sentence pairs. Already tier 2 of the corpus in §07. |
| **RAE / DLE** (23rd ed.) | es→es | ~93 k entries | **Copyrighted, no public API** | The dictionary Spanish speakers actually cite, reachable only by scraping (`pyrae`, Apify actors, Selenium wrappers). **Do not ship a scraper in a public product** — link out to `dle.rae.es`. |
| SpanishDict, Linguee, Reverso | es↔en | — | Proprietary | No usable API. Link out only. |

### The honest `es → ru` finding

There is no good open Spanish→Russian dictionary. The options are WikDict pairs, PanLex pairs
(CC0), or pivoting es→en→ru and compounding the error. **Use dictionaries for `es→es` and `es→en`,
and keep letting the LLM write the Russian gloss.** That is a genuine strength of the current
pipeline, not a gap, and it is a reason not to over-invest in bilingual dictionary plumbing.

---

## §4 · Chinese Mandarin (`zh → zh`, `zh → en`, `zh → ru`)

Subsystem deferred per §07; the schema (`reading`, traditional↔simplified as a variant axis) already
anticipates what these sources need.

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **CC-CEDICT** | zh→en (+ pinyin) | **124,948 entries** (2026-08-31); ~2.6 MB gz / **~9.5 MB plain** | **CC BY-SA 4.0** | **Core.** The backbone: traditional + simplified + numbered pinyin on one line. Every Chinese tool uses it, and it costs nothing to ship. |
| **moedict / g0v** (MOE 重編國語辭典) | **zh→zh** | 160 k Mandarin + 20 k Taiwanese + 14 k Hakka entries; JSON + bz2 + **free API** | Taiwan MOE open data | **Core.** The monolingual answer. **Traditional characters**, Taiwan norms. Bundles CC-CEDICT/CFDict/HanDeDict and stroke animations. |
| **kaikki**, English edition | zh→en | Chinese **388,964 senses**, Mandarin **112,609** | CC BY-SA 4.0 | Deeper than CC-CEDICT on senses, noisier on readings. |
| **ECDICT** | **en→zh** | 760 k base / 3.4 M in `ECDICT-ultimate`; CSV 76 MB compressed; SQLite / MDX / StarDict / Mobi | **MIT** | Superb metadata: BNC and contemporary frequency ranks, Collins star ratings, Oxford 3000 flag, CET4/CET6/IELTS/GRE tags, inflection tables. Wrong direction for the Chinese vocabulary, excellent for the English one. |
| **kaikki `ruwiktionary`** | zh→ru | 11,001 Mandarin senses | CC BY-SA 4.0 | The legal zh→ru baseline. Thin. |
| **BKRS / 大БКРС** | **zh→ru** | The reference Chinese–Russian resource; dump at `bkrs.info/p47`; converters to Pleco/GoldenDict/Dictan exist | **Licence unclear** — community-built on the copyrighted printed БКРС (Oshanin) | Best zh→ru content in existence, murkiest provenance in this document. See below. |
| **CC-Canto** | yue→en | 20 k Cantonese + 110 k CC-CEDICT with human-checked Cantonese readings | CC BY-SA 3.0 | Only if Cantonese ever matters. |
| **Unihan** (Unicode), Make Me a Hanzi, HSK lists, Jun Da / SUBTLEX-CH | characters, frequency | — | Various open | The character-decomposition and frequency substrate — the §07 Chinese subsystem, deliberately deferred. |
| **Pleco** | zh→en | Best-in-class commercial | Proprietary, no API | A reference point, not an integration. |

> **Provenance caution.** BKRS is the best Chinese→Russian resource available and has the weakest
> licensing story here. Personal use on a private server is a personal call; bundling it into a
> public product is not defensible. The legal baseline for zh→ru is kaikki's Russian edition plus
> PanLex pairs, and both are thin — an argument for keeping the LLM as the Russian gloss writer in
> this direction too.

---

## §5 · German, French, Japanese — a representative sample

Chosen to span the real range rather than the popular one: **German** has the best open bilingual
data of any pair; **French** has superb institutional dictionaries, none redistributable;
**Japanese** has the best-licensed open dictionary project anywhere plus a non-Latin script.
Between them they bracket what any new language will look like.

### German — the well-supplied case

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **FreeDict `deu-eng` / `eng-deu`** (from Ding) | de↔en | **517,534 / 460,315 headwords** | GPL-ish | The **largest open bilingual pair in existence**. Nothing else comes close. |
| **kaikki**, English edition / `dewiktionary` | de→en / de→de | 631,714 senses; de edition 2.8 GB (287.9 MB gz) | CC BY-SA 4.0 | Full structure including separable verbs. |
| **DWDS** | de→de | Free API endpoints: `/api/frequency`, `/api/wb/snippet`, `/api/ipa`, article feeds; word-list JSON/XML downloads | Terms of use apply per endpoint | Academic-grade contemporary German plus Grimm's DWB and the etymological dictionary. The best free monolingual API of any language surveyed. |
| **OpenThesaurus** | de→de synonyms | — | CC-GNU LGPL | Drop-in synonym layer. |
| **dict.cc** | de↔en | 1.3 M+ entries, 1.5 M+ audio | **Proprietary since 2005** (was GPL) | Redistribution restricted. Link out only. |

### French — the locked-up case

| Source | Direction | Size / count | Licence | Verdict |
|---|---|---|---|---|
| **kaikki**, English edition / `frwiktionary` | fr→en / fr→fr | 458,908 senses; fr edition **6.3 GB** (681.5 MB gz — the largest non-English edition) | CC BY-SA 4.0 | The only large open French resource in both directions. |
| **TLFi** (ATILF/CNRS) | fr→fr | 100 k words · **270 k definitions · 430 k examples** | Free to consult, **not redistributable** | The best French dictionary in existence. Link out to CNRTL. |
| **Dictionnaire de l'Académie française**, 9th ed. | fr→fr | Completed Nov 2024, fully online with the 4th and 8th editions | Consultation only | Prestige reference; link out. |
| **DBnary / WikDict `fr-*`** | fr→many | Part of the 26-language set | CC BY-SA 4.0 | Same pipeline as everything else. |
| **Lexique 3.83** | fr frequency/phonology | ~140 k forms | Open | Frequency, syllabification, phonology — useful for difficulty ranking. |
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
`wiktionary-to-yomitan`) publishes ready-made zips for 100+ languages — main / IPA / merged-IPA /
glossary variants — at `huggingface.co/datasets/daxida/wty-release`, **2.32 GB** for the whole
`latest/dict` set, CC BY-SA 4.0. A German→English dictionary there is ~21 MB. This is the fastest
route to a usable per-language artifact without running wiktextract over a 6 GB dump.

---

## §7 · Formats

### What exists

| Format | Nature | Random access | Structure | Verdict for Acervo |
|---|---|---|---|---|
| **wiktextract JSONL** | Line-delimited JSON | Stream only | **Richest available** | **Build input.** Never a runtime format. |
| **Yomitan** (`.zip` of `index.json`, `term_bank_N.json`, `tag_bank`, `*_meta_bank`) | Schema-validated JSON banks | On import | Structured content, tags, frequency, pitch | **Best acquisition format.** Designed to be imported into IndexedDB in a browser — exactly our constraint. |
| **SQLite** (+ FTS5) | Embedded relational DB | Page-level | Whatever schema you define | **The runtime format.** Not a "dictionary format", which is the point. |
| **StarDict** (`.ifo`/`.idx`/`.dict[.dz]`/`.syn`) | Binary index + dictzip blob | Yes | **None** — opaque text/HTML payload | Widest compatibility, zero semantics. Fine as an export target. |
| **slob** (Aard2) | Compressed, open spec | Yes | HTML payload | Good mobile container, same opaque-payload problem. |
| **dictd** (`.index` + `.dict.dz`, RFC 2229) | Server format | Yes | Plain text | Simple and ancient. Fine for a server-side DICT daemon. |
| **XDXF** | XML interchange | No | **Semantic markup** (`<def>`, `<ex>`, `<kref>`) | The right idea, weak adoption. |
| **TEI P5** (FreeDict) | Scholarly XML | No | Very rich, very verbose | A source-of-truth format, not a runtime one. |
| **OntoLex-Lemon RDF** (DBnary) | Semantic web | Via SPARQL | Formally rigorous | Heavy; WikDict already does the reduction. |
| **MDict** (`.mdx`/`.mdd`) | Proprietary binary | Yes | HTML + CSS + embedded media | Enormous catalogue of largely pirated commercial dictionaries. Avoid. |
| **ABBYY DSL** | Lingvo source markup | No | Rich | Almost every circulating DSL file is a ripped commercial dictionary. Avoid. |
| EPWING / Kobo dicthtml / Apple `.dictionary` / Kindle MOBI | Device-specific | — | — | Export targets only. |

### Conversion

**PyGlossary** is the ffmpeg of this space and settles the "can we convert?" question: it reads and
writes Aard2/slob, ABBYY DSL, AppleDict, Babylon BGL, CC-CEDICT, CSV, dictd, DictionaryForMIDs,
EPUB-2, FreeDict/TEI, HTML, JMDict, JSON, Kobo, Lingoes, Mobipocket, MDict (read), Sdictionary, SQL,
StarDict, Tabfile, XDXF, Yomichan/Yomitan (write) and Zim. Some targets require pre-sorted entries.

Specialists worth naming: `wiktextract` (Wiktionary → JSONL), `kaikki-to-yomitan` /
`wiktionary-to-yomitan`, `jmdict-simplified` (JMdict XML → clean JSON), `mdict-utils`, `dictzip`,
`wikdict-gen` (DBnary RDF → SQLite/StarDict/TEI).

### What Acervo should store

> ### DECISION
> **One internal format: SQLite, compiled by a script. Never a shipped third-party dictionary
> format.**
>
> **Because** every widely-supported dictionary format — StarDict, MDict, slob, DSL — stores an
> **opaque HTML blob per headword**. Rendering those blobs puts a foreign stylesheet inside Acervo's
> article view, which fails the whole point of showing external entries in the same unified
> interface. The value of `styles.css` is that everything looks like Acervo. A dictionary entry has
> to arrive as *fields*, not as markup.
>
> **This also means** the ingest script owns the messy per-source work exactly once per source, and
> the client reader stays trivial.

One file per (source language, gloss language, dictionary); gzip or zstd on the wire:

```
meta(key, value)              -- name, source, licence, attribution, version, built_at, counts
entry(id, headword, lemma, pos, reading, ipa, gender, freq_rank)
sense(id, entry_id, ord, definition, definition_lang, domain, tags_json)
gloss(sense_id, lang, terms_json)
example(sense_id, text, translation)      -- only where the source has them
form(form, entry_id)                      -- inflected-form index → lemma
entry_fts                                 -- FTS5 over headword + lemma + gloss terms
```

Why SQLite over shipping Yomitan zips straight into IndexedDB:

- **One artifact serves both transports.** Online, the server opens the file and answers a lookup
  route; offline, the client downloads the same file into OPFS and queries it with `sqlite-wasm`.
  Identical schema, identical reader interface, no second pipeline — the discipline `sync.ts`
  already applies to the graph routes.
- **No import step.** A Yomitan zip must be unpacked row-by-row into IndexedDB before first use; a
  downloaded SQLite file is queryable the instant the bytes land.
- **A third mode stays available.** `sql.js-httpvfs` serves a read-only database over HTTP Range
  requests — a 670 MB database answers a key lookup in roughly 1 KB of transfer.
- **FTS5 gives prefix search for free**, which is what the search box needs.

Yomitan's zips remain the **acquisition** channel, its published JSON schemas are the reference for
what a term entry should carry, and its **MIT-licensed deinflection tables for 38 languages** are
worth lifting for the `form` index. Without lemma matching, `me desmayé` never finds `desmayarse` —
the same trap §07 flags for the corpus.

**Estimated compiled sizes** — unverified; measure during implementation.

| Dictionary | Estimate |
|---|---|
| CC-CEDICT (zh→en) | ~15 MB |
| JMdict (ja→en) | ~25 MB |
| kaikki Spanish → en, glosses only | ~40–80 MB |
| FreeDict `deu-eng` | ~60 MB |
| kaikki Spanish → es, full definitions | ~120–200 MB |
| kaikki English → en | ~150–250 MB |

---

## §8 · PWA storage limits

**A non-issue at the sizes above; a real constraint only past ~1 GB.**

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
   history; Firefox prompts. This is the single most important line of code in the feature.
3. **The 7-day rule is the real risk, not the quota.** An origin with no user interaction in the last
   seven days of browser use has its script-written storage deleted. An installed Home Screen web app
   counts its own days of use, so a weekly habit is safe — but `persist()` is what makes it certain
   rather than likely.
4. **`macos/` is the tightest target, not iOS.** WKWebView is a "non-browser app": 15 % per origin,
   20 % overall. On a 256 GB Mac that is still ~38 GB — irrelevant at our sizes, but the number to
   remember.
5. **Measure, never assume.** `navigator.storage.estimate()` returns `{usage, quota}` and belongs in
   the Dictionaries settings pane before an install. Sources genuinely disagree about Safari's
   tab-origin percentage, and values are padded against fingerprinting.
6. **Guard `QuotaExceededError`** and fail the install cleanly, leaving already-installed dictionaries
   untouched — the "fail loudly, change nothing" discipline of §04.

**Verdict:** a per-language, per-direction dictionary of 15–200 MB installs safely on every target
platform, phones included. A multi-gigabyte raw wiktextract extraction stays on the server, exactly
where §02 puts it.

---

## §9 · Licensing

| Licence | Sources | What it costs |
|---|---|---|
| **CC0** | PanLex | Nothing. |
| **MIT** | ECDICT | Attribution in a notice file. |
| **CC BY 4.0** | Open English WordNet | Attribution. **No share-alike** — notable, and rare here. |
| **CC BY 3.0** | MCR non-English wordnets | Attribution. |
| **CC BY-SA 3.0 / 4.0** | Wiktionary/kaikki, CC-CEDICT, JMdict/KANJIDIC/JMnedict, WikDict/DBnary, CC-Canto | Attribution **plus share-alike on the derived database**. CC BY-SA 4.0 explicitly covers databases. |
| **GPL** | Mueller, most FreeDict | Copyleft; keep the data artifact separate from application code. |
| **Proprietary / unclear** | RAE DLE, dict.cc, TLFi, Académie française, Collins, Oxford, Merriam-Webster content, BKRS, most MDict and DSL files | Link out. Do not bundle, do not scrape into a shipped product. |

The practical rule: **the compiled `.sqlite` artifact is the derivative work, not Acervo's source
code.** Ship each artifact with its `meta` table carrying licence and attribution, render that
attribution wherever an external entry is shown, and publish the artifacts under the source's
licence. Application code keeps its own.

Two traps worth naming: do not ship an RAE scraper in a public product, and do not bundle BKRS.

---

## §10 · Recommended integration

Staged in dependency order. Nothing here changes §04, and §08's storage decision holds unchanged.

### Stage 0 — the compiler (offline, no app changes)

`scripts/build_dictionary.py`: `{kaikki JSONL | CC-CEDICT | JMdict | Yomitan zip}` → the SQLite
schema in §7. One `--source` adapter per input kind, all writing the same tables, all stamping
`meta` with licence and attribution. This is the only place a foreign format is understood — the
role `yaml.ts` plays for the YAML projection.

Start with three artifacts: `es→en` and `es→es` from kaikki, and `zh→en` from CC-CEDICT — 9.5 MB of
input as free proof that the whole path works.

### Stage 1 — the reader and the server route

- `web/src/dictionary.ts` — a pure reader interface: `lookup(headword)`, `search(prefix)`,
  `installed()`. Two transports behind it, chosen by whether the dictionary is installed locally,
  mirroring how `sync.ts` owns the graph transport. Interface code goes through this, never through
  a raw SQLite handle, the same rule `AcervoRepository` enforces.
- PocketBase hook route `GET /api/acervo/v1/dictionary/{id}/lookup` — owner-scoped, opening the same
  file server-side. This is the online-glance path and needs no WASM in the client.
- No PocketBase collections. No records. No revisions. No sync.

### Stage 2 — the interface

1. **Search.** Local results as today; below a separator, an "Other dictionaries" section. With no
   local results, the dictionary results become the answer instead of a bare "no results".
   `visibleRows()` in `selectors.ts` stays untouched — this is a second, independently-fetched list.
2. **Article.** A reference section on `LexemeArticle.tsx` showing what published dictionaries say
   about the same headword, rendered in Acervo's own components from *fields*, never from source
   HTML. Read-only: no YAML projection, no edit affordance, per §08.
3. **Promote.** A dictionary entry with no lexeme gets "Add to my words", seeding Capture with the
   headword — an ordinary `repository.saveArticle` write, dedup exactly as in §05.
4. **Settings → Dictionaries.** Per-vocabulary list with size, licence, install and remove, the
   `navigator.storage.estimate()` readout, and a `persist()` request on first install.

### Stage 3 — grounding, gated on the spike

Server-side only, and only once [acervo-grounding-spike.md](acervo-grounding-spike.md) says it
helps. The compose hook fetches the sense inventory for the resolved lemma and injects a compact
block into `prompts/acervo_compose.txt` — **gloss list, tags, domain, IPA, forms. Not the
dictionary's definition prose.** The prompt is content, not code, so this is a prompt edit plus one
lookup in the hook.

Note that the spike document already anticipates this ordering: it says the comparison is worth
running *after* §08 lands, because installed dictionaries are a better grounding candidate than raw
Wiktextract — curated, consistently formatted, and already chosen.

### Explicitly out of scope

The Chinese subsystem (§07), MDict/DSL/StarDict as runtime formats, any scraper, bundling BKRS,
per-entry caching of dictionary data, and anything that puts a dictionary row in PocketBase.

---

## Verification

```bash
# Stage 0 — the compiler, on the cheapest real source first
.venv/bin/python scripts/build_dictionary.py --source cc-cedict \
  --in cedict_ts.u8 --out dict/zh-en.sqlite
sqlite3 dict/zh-en.sqlite "select count(*) from entry;"          # expect ~124,900
sqlite3 dict/zh-en.sqlite "select * from meta;"                  # licence + attribution present
sqlite3 dict/zh-en.sqlite \
  "select headword, reading from entry where headword='漢字' or headword='汉字';"

# Stage 1 — reader unit tests, pure, no replica (the selectors.test.ts pattern)
npm --prefix web run test
npm run test:hooks          # the lookup route against stubbed PocketBase globals

# Stage 2 — offline behaviour, the invariant that matters
npm --prefix web run build && npm run test:pwa
#  · install a dictionary, then stop PocketBase → lookup and search must still work
#  · with no dictionary installed and the server down → the section reports unavailable,
#    the local list is unaffected, nothing is written
#  · DevTools → Application → Storage: confirm persisted=true and usage after install

# Stage 3 — grounding, measured not felt
#  · run the same headwords with and without the sense-inventory block
#  · score sense recall against the source inventory, not prose quality
```

---

## Sources

**Wiktionary extraction** — [kaikki raw data](https://kaikki.org/dictionary/rawdata.html) ·
[language index](https://kaikki.org/dictionary/index.html) ·
[Spanish](https://kaikki.org/dictionary/Spanish/index.html) ·
[ru edition](https://kaikki.org/ruwiktionary/index.html) ·
[es edition](https://kaikki.org/eswiktionary/index.html) ·
[wiktextract](https://github.com/tatuylonen/wiktextract) ·
[Wiktionary:Copyrights](https://en.wiktionary.org/wiki/Wiktionary:Copyrights)

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
