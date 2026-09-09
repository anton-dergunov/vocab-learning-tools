# Stage 1 — the dictionary catalogue and compiler

**Status:** built. Written as requirements after Spike 0, and rewritten here to record what was
actually made and which of the requirements' assumptions did not survive contact with the sources.
The measurements behind it are [`acervo-external-dictionaries.md`](acervo-external-dictionaries.md)
§11; the apparatus is [`experiments/external-dictionaries/`](../experiments/external-dictionaries/).

What landed: the catalogue, the compiler, the artifact format, the reader, the server surface, and
the Dictionaries pane in Settings. **Rendering an external entry did not** — no search integration,
no reference section in `LexemeArticle.tsx`, no HTML restyling in the interface. The stopping point
is deliberate: mapper quality is what needs weeks of reading real entries, and that iteration is
cheaper once the artifact, the pipeline and the install path are fixed and verifiable.

---

## 1 · What the spike settled, and what it cost

Measured, not open. Re-deciding any of it needs a reason and a number.

| Decision | Value |
|---|---|
| Container | Packed blob + sidecar index, **not** SQLite (1.53× larger) |
| Compression | DEFLATE, in **frames of 256 entries** — grouping is worth 57 % over per-entry |
| Read library | `fflate`, already a `web/` dependency, ~8 KB, no wasm |
| Size, worst case measured | Whole Spanish Wiktionary → **27.8 MiB** (§11.1 measured 39.7 before the index work) |
| Lookup | p50 ~0.2 ms; latency is not a design input |
| Memory per lookup | ~65 KiB — one decoded frame |
| Payload tier | `fields` and `html` are within 7 % once compressed; choose on rendering, not size |
| Coverage | 98.7–100 % of entries map, every source, nothing invented |

The index work §11.2 called "the single largest remaining size win" was built in from the start and
delivered: 834,245 entries and 865,202 lookup keys in 19.7 MiB of payloads plus 8.1 MiB of index,
built in about 30 seconds, byte-identical on rebuild. Read back through the TypeScript reader, `picar`
returns its 37 senses and its IPA, `ñandú` and `de repente` resolve, and a prefix search over
`pica` lists `pica picaba picabais picaban picabas picabe`.

---

## 2 · The product shape

A **Dictionaries** pane, opened from Settings, listing pre-filled sources — offline, online and
link-out together — grouped by language and turned on per device.

- Each row: name, direction, licence, approximate size, and its state on *this* device.
- Online sources are enabled with one toggle and need no download.
- Offline sources offer **"store on this device"**, which downloads the compiled artifact from the
  server that built it. The same dictionary can be on the phone and absent from the laptop.
- **Resolution order for a lookup is: this device, then the server, then an online source.** A
  dictionary the device does not hold is still usable when the server has it and is reachable. This
  is the one place Acervo reads through the network on purpose, and it does not contradict `§04` —
  external dictionaries are not the replica, so a failure here degrades a reference surface rather
  than losing data.
- Removing a dictionary frees its space and leaves every other one untouched.

---

## 3 · Decisions taken during the build

### 3.1 · Compile at install time — but for one reason, not three

**Compile once, at install time.** The original argument gave three reasons and only the third
holds.

- *"Grouping is where the space is"* — withdrawn. Frame grouping is a property of how the artifact
  is packed, not of when it is packed. An on-demand compiler would group exactly the same way.
- *"On-demand on mobile means shipping every source parser to the client"* — withdrawn. Conversion
  would run on the server either way, so no parser ever reaches a client.
- **Uniformity is the reason.** The server and the device hold byte-identical artifacts and run the
  same reader. That is worth having on its own.

### 3.2 · The stored payload is JSON

The argument for YAML would have been reusing `parseArticle`, and §11.3 already establishes that
external entries cannot go through it — `posLabel` is an unknown key it rejects. YAML therefore buys
no code reuse here and costs a parser call per lookup, while `JSON.parse` is native. `yaml.ts`
remains the editing projection for the owner's own entries.

Two shape decisions came out of the same measurement. §11.0a found the `fields` tier larger than
HTML raw and traced it to `definitionLang` and `order` repeating on every sense: `definitionLang` is
now hoisted to the entry, where it is uniform for a whole dictionary, and `order` is gone because a
JSON array is already ordered.

### 3.3 · The downloaded source is cached, for now

Kept in `data/dictionaries/src/` (already gitignored), so changing a converter is a re-run rather
than another 1.19 GB fetch. `--discard-source` drops it. The default is commented to say it should
flip to discarding once the conversions are trusted — the source is 2–25× the artifact and nothing
reads it again.

### 3.4 · Which HTML, and who writes it

- **Opaque binaries (StarDict, slob, MDict, Zim, Yomitan zips …): the HTML is the source's own**,
  handed over by PyGlossary. Genuinely free.
- **Field-structured sources: there is no HTML at the source.** "Just use HTML" there still means
  writing a renderer, which is the same work as the field mapper minus the structure.

So `fields` wherever a source is field-structured, `html` where the payload arrives as markup. Tier
2 HTML is restyled rather than merely sanitised — FreeDict payloads carry `<font color="gray">` and
`<font class="grammar" color="green">`, whose inline colours fight Acervo's theme in both modes.
`restyle()` strips `<font>` and presentational attributes and keeps the structure.

### 3.5 · Compiled artifacts stay out of git, and travel in the release

Two different questions that are easy to conflate, and were:

**Not committed to the repository.** §9's decision is that Acervo ships the list, not the data.
Nearly every source is share-alike or copyleft (kaikki, CC-CEDICT, JMdict all CC BY-SA; most
FreeDict GPL), this repository is public, and Spanish alone is 27.8 MiB against GitHub's
1 GiB/month free LFS bandwidth — with a rebuild on every mapper change.

**Carried by the deployment.** §9 is about publishing to the world; moving the owner's own compiled
copy from their laptop to their own server is not publishing anything. So the release bundle carries
whatever is in `data/dictionaries/out/`, exactly the way it already carries the macOS application,
and `install.sh` publishes it into the directory the server serves. The workflow is: build locally,
check it locally, `./deploy.sh`, and the dictionaries are there.

They are **merged, not replaced**: building only the Spanish ones and deploying must not withdraw
the Chinese ones deployed last week, and a release built with none at all leaves the published ones
alone. Removing one means deleting its three files from `<acervo-root>/data/dictionaries`.
`ACERVO_INCLUDE_DICTIONARIES=false` skips the bundling when a deploy should not re-upload them.

### 3.6 · The frames live in IndexedDB, and the probe says that works

The packed container was designed assuming OPFS, and the first probe run reported OPFS missing on
every device — including desktop Chrome, which certainly has it. That was an insecure origin, and
re-running over https confirms OPFS is available everywhere (§11.7).

It is still not used, and this is now a measurement rather than a fallback. `createSyncAccessHandle`
is `[Exposed=DedicatedWorker]`, so the fast OPFS path means moving reads into a worker; IndexedDB
needs no worker, is what `localDatabase.ts` already uses, and measured:

- **1.00× storage overhead** on Android Chrome — the artifact is stored as exactly the bytes written,
  so DEFLATE frames stay compressed and the container decision survives storage intact.
- **A 64 KiB `Blob.slice` out of a 40 MiB stored Blob costs 0.00–1.40 ms**, against 14–37 ms to read
  the whole Blob. Slices are lazy, so the store behaves like the random-access file the format was
  designed against, and the ~1 MiB chunking fallback is not needed.

The condition is that IndexedDB stores **whole files, not entries** — three records per dictionary.
The per-entry shape §11 originally modelled would have paid per-record overhead 834,245 times. This
is the one place where getting the storage shape wrong would silently undo the container decision.

One interface consequence fell out of the same run: **both WebKit browsers report
`storage.estimate().usage` as unchanged after a 40 MiB write**, because WebKit updates it lazily. The
pane therefore never quotes a usage figure lower than what it knows it is holding — it reports the
headroom instead, which is the number someone deciding whether to download is actually asking.

### 3.7 · There is no server-side lookup route

Stage 2 planned `GET /api/acervo/v1/dictionary/{id}/lookup`. It is not needed. The artifact is
served as a static file and Go's file server answers Range requests, so a dictionary the device has
not stored is read by the *same* reader over an HTTP byte source. Adding the route would have meant
implementing the packed format a second time, in another language, and keeping the two in step.

---

## 4 · What was built

### The catalogue — `dictionaries/catalogue.json`

58 rows across a dozen languages: 46 offline, 2 online, 10 link-outs. Each carries id, name, kind,
tier, format, languages, source URL, licence, attribution, approximate size and a note — enough to
render the pane with nothing fetched.

**Breadth comes from rows; cost comes from converters.** Six converters carry all 46 offline rows,
and the long tail costs no code at all.

| Converter | What it carries |
|---|---|
| `wiktextract` | 18 rows. The only load-bearing one: ~20 Wiktionary editions and hundreds of languages, in both the per-language extracts and the whole-edition dumps |
| `cc-cedict` | CC-CEDICT and CC-Canto — the same line grammar, the second with `{jyutping}` |
| `jmdict` | jmdict-simplified |
| `freedict-tei` | FreeDict's ~150 dictionaries, resolved through its own database so a version bump does not rot the row |
| `moedict` | 重編國語辭典 — the monolingual Chinese answer |
| `pyglossary` | Everything opaque, with no per-source code: StarDict, slob, MDict, DSL, Zim, XDXF, and **Yomitan zips**, which opens the prebuilt `wty-release` channel of 100+ languages |

Deliberately excluded: **BKRS** (§9 — the best `zh→ru` content and the murkiest provenance here),
any API needing a key (§6 puts bespoke connectors out of scope), PanLex and Tatoeba (bare pairs and
sentences rather than dictionary entries), and the deprecated Glosbe API.

Verified end to end: `es`, `en`, `zh`, plus `ja` and `ru` through the shared converters. The rest
are rows on converters those already exercise, so a broken row is a catalogue fix and not new code.
`build_dictionary.py verify --id <id>` compiles a sample into a throwaway directory and reports what
came out, which is how a row is promoted from listed to trusted.

### The compiler — `scripts/build_dictionary.py` over `src/acervo/dictionaries/`

`container.py` owns the on-disk format and nothing else; `converters.py` owns the source formats and
nothing else; `build.py` joins them, fetches (cached), and takes a progress callback rather than
printing — so the "build it from the interface" job that comes later is a *caller* rather than a
second pipeline. `model.py` is the render-only entry, deliberately not `ArticleDraft`.

It streams (the largest source is 1.19 GB and is never resident), is deterministic (two runs produce
byte-identical `.dict` and `.idx`; `builtAt` lives in the `.json`, which is excluded), and records
what it dropped and which parts of speech it could not map into the artifact's own metadata.

**PyGlossary is pinned at 5.4.2 with `lxml` as an explicit dependency.** Without `lxml` it silently
disables seven plugins — including `EDICT2`, the CC-CEDICT reader — warning rather than failing, so
a missing dependency looks like a source with no entries. This was confirmed the hard way.

**PyGlossary is deliberately not used for the field-structured sources**, even though 5.4.2 has
readers for all of them. Every one of its plugins emits HTML — the wiktextract reader builds an lxml
tree writing `<div class="pos"><font color="green">` — and it yields one entry per JSONL line with
no headword grouping, so `gratis` would arrive as separate adjective and adverb entries. Routing
kaikki through it would turn the one load-bearing structured source into an opaque one.

### The artifact format

```
<id>.dict   payloads concatenated in index order, raw DEFLATE, frames of 256 entries
<id>.idx    header, then five varint sections: frame lengths, per-frame payload offsets,
            per-entry payload lengths, restart offsets, front-coded keys
<id>.json   name, source, licence, attribution, counts, what was dropped, checksums
```

Three details are load-bearing and were not in the original requirements:

- **Restart points.** Front-coding destroys the random access a binary search needs, so every 16th
  key is stored whole with its offset recorded. A lookup binary-searches the restart table and scans
  one bucket of at most 16.
- **Per-frame offsets into the payload-length section.** Without them, locating an entry inside its
  frame means holding every entry's length — about 2 MiB per dictionary, which does not survive ten
  dictionaries being installed. With them, resident state is the header, the frame table and the
  restart table. Measured on the finished Spanish artifact with the real reader: **499 KiB
  resident**, 210 KiB to open it, and **12.6 KiB read to answer one lookup**. Ten open at once cost
  about 5 MiB.
- **Byte-wise UTF-8 ordering**, not locale collation and not the platform's string comparison.
  JavaScript compares UTF-16 code units, which disagrees with UTF-8 byte order above the BMP.

Every key carries an explicit entry index, so **aliases are free**: the traditional spelling of a
simplified headword and a case-folded spelling of an accented one point at an existing entry and
cost one key each.

A headword can hold **more than one article**. CC-CEDICT writes one line per reading, so simplified
行 arrives as *háng*, *héng* and *xíng*; the payload is always a JSON array and the packer splices
them. An earlier build kept only the first and silently lost 3 % of that dictionary — which is why
the metadata now reports how many entries were folded together.

### `acervo-worker`

`anki-robot` was never a service — `profiles: ["tools"]`, no ports, no restart policy, started by
`docker compose run --rm` to do one job and exit. It is now `acervo-worker` with subcommand dispatch
(`anki …`, `dictionary …`), which is where Acervo's server-side Python converges as it grows. Zero
running containers were added.

### The server surface

- `GET /api/acervo/dictionaries/{path...}` — the artifacts, `$apis.static` behind `$apis.requireAuth`
  and outside `pb_public`, so the service worker never tries to precache tens of MiB and the server
  is not a public redistributor of share-alike data.
- `GET /api/acervo/v1/dictionaries` — what this server has compiled, from the metadata sidecars.
- `GET /api/acervo/v1/dictionaries/online/{source}` — the two connectors. §11.5 withdrew the claim
  that they share the offline mapper: three Wiktionary-derived sources, three field shapes.

### The client

`dictionary.ts` is the reader — pure, over a `ByteSource`. `dictionaries.ts` owns the catalogue, the
transports, the per-device preferences and the resolution order, the way `sync.ts` owns the graph
transport. `dictionaryStore.ts` is a **separate IndexedDB database** from the replica, so neither
wipe touches the other. `DictionaryPanel.tsx` is the Settings pane.

One correction found by a test: the catalogue is a starting list, **not an allow-list**. A server can
compile a dictionary nobody wrote a row for, and an installed artifact carries its own name, licence
and languages — so both the pane and `lookup` work from the union of the catalogue and what is
actually installed.

---

## 5 · Verification

```bash
uv pip install -r requirements/dev.txt

.venv/bin/python scripts/build_dictionary.py list
.venv/bin/python scripts/build_dictionary.py build --id cc-cedict
.venv/bin/python scripts/build_dictionary.py build --all --language es,zh   # 12 rows, ~1.7 GiB
.venv/bin/python scripts/build_dictionary.py build --all                    # 46 rows, ~11.6 GiB
.venv/bin/python scripts/build_dictionary.py verify --id <any other row>

#  · rebuild, diff .dict and .idx: byte-identical
#  · spot-check `picar` against es.wiktionary.org — 37 senses, IPA, and a `verb` label
#  · a CC-CEDICT entry has no part of speech at all, and 行 returns three articles
#  · either Chinese spelling, and an accented word typed in lower case, find the same entry

.venv/bin/python -m pytest tests/unit/dictionaries/
npm --prefix web run test
.venv/bin/python -m pytest tests/unit/server
npm --prefix web run build && npm run test:pwa

# end to end: build locally, deploy, and the dictionaries go with the release
./deploy.sh                       # or --local
#  · the packager reports how many dictionaries it bundled and how large they are
#  · Settings ▸ Dictionaries lists them as being on the server
#  · store on this device → progress → stored here, with its entry count
#  · stop the server → the stored dictionary still answers a lookup
#  · not stored, server down → the row says so, and nothing is written
#  · DevTools ▸ Application ▸ Storage: persisted=true, usage ≈ the artifact size

# building on the server instead, when a source is too large to want on the laptop
run-worker.sh build-dictionary --all --language es,zh
```

The format is written in Python and read in TypeScript, so it is checked where it actually crosses
that boundary: `tests/unit/dictionaries/test_fixture.py` builds a small artifact and
`web/src/dictionary.test.ts` opens those same bytes with the real reader. Regenerate with
`ACERVO_UPDATE_FIXTURES=1`, and treat the failure as the moment to look at both halves together.

---

## 6 · What is still open

- **Rendering.** The search surface, the reference section in `LexemeArticle.tsx`, "Add to my words",
  and the sanitising and restyling of an `html` payload where it is displayed.
- **Mapper quality.** The reason to stop here. Reading real entries will produce a list of
  corrections, and the pipeline is now cheap to re-run.
- **Building from the interface.** `build.build` already takes a progress callback and raises rather
  than printing, so this is a job wrapper plus a status route, with no change to the artifact,
  catalogue, client or reader.
- **A catalogue health check.** §9's monthly script that HEADs every URL and reports what moved. The
  FreeDict and GitHub resolvers already remove the most common cause of rot.
