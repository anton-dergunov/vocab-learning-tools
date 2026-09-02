# Stage 1 — the dictionary catalogue and compiler

**Status:** requirements, nothing built. Written after Spike 0, whose results are
[`acervo-external-dictionaries.md`](acervo-external-dictionaries.md) §11 and whose apparatus is
[`experiments/external-dictionaries/`](../experiments/external-dictionaries/). This document states
*what* Stage 1 must do and the decisions the spike already settled. It deliberately stops short of
a file-by-file plan — that is the planning session's job.

Stages 2 and 3 (the reader, the server route, the interface) stay as §10 describes them. This
document covers Stage 1 plus the product shape Stage 3 has to serve, because that shape constrains
what Stage 1 must produce.

---

## 1 · What the spike already settled

These are measured, not open. Re-deciding them needs a reason and a number.

| Decision | Value |
|---|---|
| Container | Packed blob + sidecar index, **not** SQLite (1.53× larger) |
| Compression | DEFLATE, in **frames of 256 entries** — grouping is worth 57 % over per-entry |
| Read library | `fflate`, already a `web/` dependency, ~8 KB, no wasm |
| Size, worst case measured | Whole Spanish Wiktionary, 838,769 headwords → **~40 MiB** |
| Lookup | p50 ~0.2 ms; latency is not a design input |
| Memory per lookup | ~65 KiB — one decoded frame |
| Payload tier | `fields` and `html` are within 7 % once compressed; choose on rendering, not size |
| Coverage | 98.7–100 % of entries map, every source, nothing invented |

**The single highest-value implementation detail:** the index is currently ~half the artifact
(19.5 MiB of 39.7). Front-coding the sorted keys and varint-packing the records takes it to
~5.7 MiB — a ~35 % cut to the whole download, with no new dependency. Build this in from the start;
it is not an optimisation to defer.

---

## 2 · The product shape Stage 1 must serve

A **Dictionaries** dialog, opened from Settings, listing pre-filled sources — online and offline
together — that the owner turns on per device.

- Each row: name, languages and direction, licence, approximate download size, and its state on
  *this* device.
- Online sources are enabled with one toggle and need no download.
- Offline sources offer **"store on this device"**, which downloads and compiles the artifact
  locally. The same dictionary can be on the phone and absent from the laptop.
- **Resolution order for a lookup is: this device, then the server.** A dictionary the device does
  not hold is still usable when the server has it and is reachable. This is the one place Acervo
  reads through the network on purpose, and it does not contradict `§04` — external dictionaries
  are not the replica, and a failure here degrades a reference surface rather than losing data.
- Removing a dictionary frees its space and leaves every other one untouched.

Consequences for Stage 1: the compiler must produce **one artifact usable unchanged by both the
server and the client**, and the catalogue must carry enough metadata to render that dialog without
downloading anything.

---

## 3 · Decisions to make in planning, with the evidence

These are genuinely open. Each has a recommendation and the measurement behind it; overturn them
with a better argument, not by default.

### 3.1 · Compile at install time, or convert on demand?

**Recommend: compile once, at install time, on whichever side is doing the installing.**

- **Grouping is where the space is.** 256-entry frames are 57 % smaller than compressing entries
  individually. On-demand conversion is inherently per-entry and gives that up.
- **On-demand on mobile means shipping every source parser to the client** and keeping the raw
  source (94 MB gz for Spanish) beside the artifact. That is strictly worse on both axes.
- **Uniformity is the stated goal** and compile-time gets it: the server and the device hold byte-
  identical artifacts and run the same reader.

The argument *for* on-demand was preserving the option to switch to raw HTML later. §3.4 shows that
option is narrower than it looks, so it does not buy back the cost.

### 3.2 · Store the payload as JSON or YAML?

**Recommend: JSON for the stored payload. YAML is not a storage format here.**

This corrects a reasonable assumption. YAML is what a *person* edits and what `yaml.ts` projects
for the owner's own entries — but an external dictionary entry is never edited, and what gets
displayed is the rendered article, not the document. Measured on `picar`: YAML and compact JSON are
within 3 % raw and within 0.5 % compressed, so there is no size argument either way, and JSON parses
with `JSON.parse` while YAML costs a parser call per lookup. `AGENTS.md` already holds the line that
YAML is the editing projection rather than storage.

### 3.3 · Keep the downloaded source as a cache?

**Recommend: never on the device; optionally on the server.**

On a phone the source is 2–25× the artifact and defeats the point. On the server, keeping it makes a
rebuild cheap and space is not scarce — so make it a server-side flag, defaulting to discarding, and
never expose it as a client concern.

### 3.4 · Which HTML, and who writes it?

Worth knowing before choosing a tier, because the answer is not uniform:

- **Tier 2 (StarDict, and the other opaque binaries): the HTML is the source's own**, handed over by
  PyGlossary and stored untouched. This is genuinely free.
- **Tier 1 (kaikki, CC-CEDICT, jmdict, TEI, and both online APIs): there is no HTML at the source.**
  The spike's `*_html` functions generate it. So "just use HTML" for a Tier 1 source still means
  writing and maintaining a renderer — the same work as the field mapper, minus the structure.

Given that, **prefer `fields` wherever a source is field-structured**, which is every non-opaque
format measured, at 30–90 lines each. Reserve `html` for payloads that arrive as markup.

One caveat carried from the spike: Tier 2 HTML needs **restyling, not just sanitising**. FreeDict
StarDict payloads carry `<font color="gray">` and `<font class="grammar" color="green">`, whose
inline colours fight Acervo's theme in both light and dark. Strip `<font>`, keep the structure,
restyle from class names where they exist.

---

## 4 · Requirements — the compiler

A script that turns a downloaded source into the artifact triple. Reuse the spike's readers and
mappers (`experiments/external-dictionaries/sources.py`) as the starting point; they are measured
and correct, but they are experiment code and should be reviewed rather than copied wholesale.

1. **Output** — three files per dictionary, named by catalogue id:
   `<id>.dict` (payloads, DEFLATE frames of 256), `<id>.idx` (front-coded sorted headwords +
   varint records), `<id>.json` (metadata: name, source URL, licence, attribution, build date,
   entry count, schema version).
2. **Front-code the index and varint the records** (§1). Do not ship the naive fixed-width index.
3. **Support both payload tiers**, selected per source by the catalogue, not by a flag at the call
   site.
4. **Stream.** The largest source is 1.19 GB and must never be held in memory. The spike's
   adjacent-run grouping over kaikki works and is verified — headword occurrences are contiguous
   even though the file is unsorted.
5. **Part of speech follows §11.3:** emit `pos` only when the source's value genuinely maps to
   Acervo's enum, always emit `posLabel` verbatim, invent nothing. A source with no part of speech
   (CC-CEDICT) emits neither.
6. **Be re-runnable and deterministic** — the same input must produce a byte-identical artifact, so
   a rebuild can be diffed and a mirror can be checksummed.
7. **Record what it dropped.** Each source drops fields with no home (29 of them for kaikki `es→en`).
   The metadata should say so rather than leaving it implicit.

Source formats to support at Stage 1, in priority order — **the wiktextract mapper is the only
load-bearing one**, since it covers ~20 Wiktionary editions and hundreds of languages:

| Source | Effort measured |
|---|---|
| wiktextract JSONL (kaikki, both directions) | ~90 lines |
| CC-CEDICT | ~30 lines |
| jmdict-simplified | ~45 lines |
| FreeDict TEI P5 | ~35 lines |
| Anything PyGlossary reads → `html` | shell-out |

**PyGlossary notes from the spike:** version 5.4.2 renamed `Glossary.read` to `directRead`, and it
silently disables seven plugins — including **XDXF** — when `lxml` is missing, warning rather than
failing. Pin the version and depend on `lxml` explicitly.

---

## 5 · Requirements — the catalogue

A tracked `dictionaries/catalogue.json`, per §9: Acervo ships the *list*, never the data.

Each entry needs: id, display name, source and target languages, direction, kind (`offline` /
`online`), tier (`fields` / `html`), source URL, format, licence and attribution string, approximate
download and installed sizes, and a note field. Enough to render the dialog in §2 with nothing
fetched.

- **Start with `es` and `en` only** and grow on demand (§9).
- **Include the two online sources**, which the spike verified at 100 % coverage of held words:
  `freedictionaryapi` and `wikimedia-rest`. They need **one small connector each, ~40 lines** —
  §7's claim that they share the offline mapper is withdrawn (§11.5). Wikimedia's definition
  endpoint lives only on `en.wiktionary.org`, keyed by term with languages inside the response.
  Percent-encode headwords: accented and multi-word entries are ordinary.
- **Keep unclear provenance out** — BKRS especially (§9).
- Attribution and licence must be available to the interface wherever an entry is rendered, so they
  belong in both the catalogue and each artifact's metadata.

---

## 6 · Explicitly not Stage 1

The reader interface, the server route, and every piece of interface are Stages 2 and 3. So are:
grounding; any scraper; per-entry caching of dictionary data; bespoke connectors beyond the two
Wiktionary-shaped ones; and anything that puts a dictionary row in PocketBase.

**One thing must happen before Stage 1 is called done, though:** `probe.html` has still not been run
on a phone or in the `macos/` WKWebView host. The packed container assumes OPFS with a sync access
handle, and that assumption is currently inference from documentation rather than measurement. If it
does not hold on iOS, the fallback is IndexedDB holding the same frames, which changes the reader
but not the artifact — so the risk is contained, but it should be retired early rather than late.

---

## 7 · Verification

```bash
# the compiler, on the control case and the real one
.venv/bin/python scripts/build_dictionary.py --id cc-cedict-zh-en
.venv/bin/python scripts/build_dictionary.py --id kaikki-es-es

#  · rebuild twice, diff the artifacts: must be byte-identical
#  · index must be front-coded — compare against the naive size in §11.2
#  · spot-check `picar` against es.wiktionary.org, and a headword with no part of speech
#  · every artifact carries licence and attribution in its metadata

npm --prefix web run test && .venv/bin/python -m pytest
```
