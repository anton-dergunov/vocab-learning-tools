# Experiment · external dictionary storage and representation

Spike 0 for [`docs/acervo-external-dictionaries.md`](../../docs/acervo-external-dictionaries.md) §10.
Results are written back into that document; this directory holds the apparatus and the raw
numbers.

## The two questions

1. **What container should an installed dictionary use?** §7 of the design document proposed
   "SQLite as a dumb container" and labelled it a hypothesis. Measuring only that hypothesis would
   confirm it by construction, so this measures a shortlist and lets the numbers choose. Mobile is
   space-bound and memory-bound; the server is neither, so the two are scored separately.
2. **Per source format, is mapping onto Acervo's `ArticleDraft` worth it, or is sanitised HTML the
   right answer?** The article model and its renderer are good and worth keeping — but only if a
   source maps onto them cheaply and without inventing data. HTML must always work as the fallback.

## Method

Every container candidate is built from **the same payloads**, so the byte columns compare like
with like, and each is reported as **total device bytes** — artifact + any trained dictionary +
the library a client must ship to read it — rather than bare file size. Two mobile memory costs
are tracked alongside: bytes that must stay resident to serve a lookup, and peak bytes allocated
to answer one.

Fidelity is measured against the application's own parser. `fidelity.test.ts` imports the real
`parseArticle` from `web/src/yaml.ts`, because a Python re-implementation would only prove that two
of my own guesses agree. `parseArticle` is the correct gate: external entries are render-only, so
`validateGraph`'s stricter rule (at least one gloss group per sense) does not apply to them.

Design is **broad pilot, then finalists at full scale** — the pilot ranks every candidate on a
5,000-entry sample, and only the survivors are rebuilt over the full corpora.

## Files

| File | What it is |
|---|---|
| `sources.py` | One reader per source *format family*, plus the `fields` and `html` mappers |
| `containers.py` | Container and codec candidates, the memory model, and the benchmarks |
| `spike.py` | Driver: builds every candidate, benchmarks, writes `results/*.{json,md}` |
| `online.py` | Part C — the two Wiktionary-shaped APIs, access and display only |
| `fidelity.test.ts` | Runs mapped entries through Acervo's real `parseArticle` |
| `probe.html` | Opened on the target phone: what the device can actually read, and at what cost |
| `results/` | Tracked output. The tables in the design document come from here |

Downloaded corpora live in `data/dictionaries/` (gitignored, ~2.3 GB) and are never tracked.

## Running it

```bash
uv pip install -r requirements/dictionary-spike.txt

# fetch the corpora (see docs §10 for the URLs); then:
.venv/bin/python experiments/external-dictionaries/spike.py --source all --limit 5000 --fast \
  --emit-yaml --tag pilot                       # broad pilot: rank every candidate
.venv/bin/python experiments/external-dictionaries/spike.py --source kaikki-es-es \
  --finalists --blocks 64,256 --tag finalists   # survivors, full corpus

.venv/bin/python experiments/external-dictionaries/online.py

cd web && npx vitest run --config ../experiments/external-dictionaries/fidelity.config.ts

open experiments/external-dictionaries/probe.html   # and on the phone
```

`spike.py --source all` covers CC-CEDICT (fixed line grammar), kaikki `es→en` and `es→es` (rich
JSONL, bilingual and monolingual), jmdict-simplified (clean sense-tagged JSON, non-Wiktionary),
FreeDict TEI P5 (semantic XML) and FreeDict StarDict (opaque binary, via PyGlossary). The sample is
chosen to span *formats*, not languages.
