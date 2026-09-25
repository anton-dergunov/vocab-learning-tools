#!/usr/bin/env python3
"""Spike 0 for docs/external-dictionaries.md §10 — measure, then choose.

Answers two questions with numbers rather than assertion:

  1. What container should an installed dictionary use? Mobile is space-bound; the server is not.
     Every candidate is built from the same payloads and reported as total device bytes
     (artifact + trained dictionary + the library a client must ship to read it).
  2. Per source format, is mapping onto Acervo's ArticleDraft worth it, or is sanitised HTML the
     right answer? Reported as mapper cost, fidelity against the application's own parser, and the
     byte cost of each tier on the same entries.

  experiments/external-dictionaries/spike.py --source cc-cedict
  experiments/external-dictionaries/spike.py --source kaikki-es-es --limit 20000
  experiments/external-dictionaries/spike.py --source all --emit-yaml
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import containers  # noqa: E402
import sources  # noqa: E402
from containers import Codec, build_all, bench_packed, bench_sqlite  # noqa: E402

RESULTS = HERE / "results"
OUT = HERE.parents[1] / "data" / "dictionaries" / "out"

# Key order matches yamlForDraft in web/src/yaml.ts; absence means null, so empties are dropped.
DRAFT_KEYS = ["id", "language", "headword", "lemma", "reading", "ipa", "pos", "gender", "register",
              "dialect", "emoji", "status", "topics", "shortGloss", "notes", "senses",
              "attestations", "imagePrompts"]
# posLabel is deliberately absent from DRAFT_KEYS: it is a render-only field the current
# parseArticle would reject as an unknown key. §11.3 records what that implies.
SENSE_KEYS = ["id", "order", "definition", "definitionLang", "domain", "glosses", "examples",
              "imagePrompts"]


def to_yaml(draft: dict) -> str:
    """Emit the document `parseArticle` reads, in the order `yamlForDraft` writes it."""
    import yaml as pyyaml

    def ordered(source: dict, keys: list[str]) -> dict:
        return {key: source[key] for key in keys
                if key in source and source[key] not in (None, [], "")}

    body = ordered(draft, DRAFT_KEYS)
    body["senses"] = [ordered(sense, SENSE_KEYS) for sense in draft["senses"]]
    return pyyaml.dump(body, allow_unicode=True, sort_keys=False, width=100)


SOURCES = {
    "cc-cedict": "cedict.txt.gz",
    "kaikki-es-en": "kaikki-Spanish.jsonl",
    "kaikki-es-es": "kaikki-eswiktionary.jsonl.gz",
    "jmdict-eng": "jmdict-eng.json.tgz",
    "freedict-eng-rus-tei": "freedict-eng-rus.src.tar.xz",
    "freedict-eng-rus-stardict": "freedict-eng-rus.stardict.tar.xz",
}


def load(name: str, limit: int | None, lenient: bool) -> tuple[list[sources.Entry], int]:
    """Return mapped entries plus the source's own byte count."""
    path = sources.SRC / SOURCES[name]
    size = path.stat().st_size
    entries: list[sources.Entry] = []

    if name == "cc-cedict":
        for row in sources.read_cc_cedict(path, limit):
            entry = sources.cedict_fields(row)
            entry.html = sources.cedict_html(row)
            entries.append(entry)
    elif name in {"kaikki-es-en", "kaikki-es-es"}:
        # The English edition glosses Spanish in English; the Spanish edition defines it in Spanish.
        definition_lang = "en" if name == "kaikki-es-en" else "es"
        lang_filter = None if name == "kaikki-es-en" else "es"
        for group in sources.read_kaikki(path, lang_filter, limit):
            entry = sources.kaikki_fields(group, "es", definition_lang, lenient)
            entry.html = sources.kaikki_html(group)
            entries.append(entry)
    elif name == "jmdict-eng":
        for word in sources.read_jmdict(path, limit):
            entry = sources.jmdict_fields(word, lenient)
            entry.html = sources.jmdict_html(word)
            entries.append(entry)
    elif name == "freedict-eng-rus-tei":
        for row in sources.read_freedict_tei(path, limit):
            entry = sources.tei_fields(row, lenient)
            entry.html = sources.tei_html(row)
            entries.append(entry)
    elif name == "freedict-eng-rus-stardict":
        for headword, defi in sources.read_stardict(path, limit):
            entry = sources.Entry(key=headword, lemma=headword)
            entry.html = defi                      # opaque tier: nothing to map
            entry.dropped.add("(entire payload is markup)")
            entries.append(entry)
    else:
        raise SystemExit(f"unknown source {name}")
    return entries, size


def measure(name: str, limit: int | None, lenient: bool, fast: bool, emit_yaml: bool,
            codec_names: set[str] | None = None, blocks=(16, 64, 256),
            finalists: bool = False) -> dict:
    started = time.perf_counter()
    entries, source_bytes = load(name, limit, lenient)
    read_seconds = time.perf_counter() - started
    if not entries:
        raise SystemExit(f"{name}: no entries read")

    mapped = [entry for entry in entries if entry.fields]
    fidelity = len(mapped) / len(entries)

    fields_rows = [(entry.key, json.dumps(entry.fields, ensure_ascii=False,
                                          separators=(",", ":")).encode())
                   for entry in mapped]
    html_rows = [(entry.key, entry.html.encode()) for entry in entries if entry.html]

    dropped: set[str] = set()
    unmapped_pos: set[str] = set()
    invented: set[str] = set()
    for entry in entries:
        dropped |= entry.dropped
        unmapped_pos |= entry.pos_unmapped
        invented |= entry.invented

    if emit_yaml and mapped:
        OUT.mkdir(parents=True, exist_ok=True)
        sample = random.Random(7).sample(mapped, min(300, len(mapped)))
        target = OUT / f"{name}.yaml.jsonl"
        with target.open("w", encoding="utf-8") as handle:
            for entry in sample:
                handle.write(json.dumps({"source": name, "key": entry.key,
                                         "yaml": to_yaml(entry.fields)}, ensure_ascii=False) + "\n")

    report: dict = {
        "source": name,
        "entries": len(entries),
        "source_bytes": source_bytes,
        "read_seconds": round(read_seconds, 1),
        "fidelity": round(fidelity, 4),
        "mapped": len(mapped),
        "fields_bytes": sum(len(value) for _, value in fields_rows),
        "html_bytes": sum(len(value) for _, value in html_rows),
        "dropped_fields": sorted(dropped),
        "unmapped_pos": sorted(unmapped_pos)[:40],
        "invented_fields": sorted(invented),
        "containers": {},
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for tier, rows in (("fields", fields_rows), ("html", html_rows)):
            if not rows:
                continue
            codec_list = containers.codecs_for([value for _, value in rows[:5000]], codec_names)
            built = build_all(rows, tmpdir, blocks=blocks, fast=fast, codecs=codec_list,
                              packed_only=finalists, skip_idb=finalists)
            keys = [key for key, _ in random.Random(11).sample(rows, min(1000, len(rows)))]
            table = []
            for item in built:
                entry = {
                    "container": item.container, "codec": item.codec, "engine": item.engine,
                    "artifact": item.artifact, "dictionary": item.dictionary,
                    "engine_bytes": item.engine_bytes, "total": item.total,
                    "resident": item.resident, "transient": item.transient,
                }
                if item.extra:
                    entry["extra"] = item.extra
                if item.path:
                    codec = next(c for c in codec_list if c.name == item.codec)
                    block = int(item.container.split("block")[1]) if "block" in item.container else None
                    if item.container.startswith("sqlite"):
                        entry.update(bench_sqlite(item, keys, codec, block))
                    else:
                        entry.update(bench_packed(item, keys, codec, block))
                table.append(entry)
            report["containers"][tier] = table
    return report


def markdown(reports: list[dict]) -> str:
    lines: list[str] = []
    lines.append("## Representation — is the mapper worth writing?\n")
    lines.append("| Source | Entries | Source B | fields B | html B | html/fields | Fidelity | Invented | Unmapped POS |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---:|")
    for report in reports:
        ratio = (report["html_bytes"] / report["fields_bytes"]) if report["fields_bytes"] else 0
        lines.append(
            f"| `{report['source']}` | {report['entries']:,} | {report['source_bytes']:,} | "
            f"{report['fields_bytes']:,} | {report['html_bytes']:,} | {ratio:.2f}× | "
            f"{report['fidelity'] * 100:.1f} % | {', '.join(report['invented_fields']) or '—'} | "
            f"{len(report['unmapped_pos'])} |")
    lines.append("")
    for report in reports:
        for tier, table in report["containers"].items():
            lines.append(f"\n### {report['source']} · `{tier}` payload\n")
            lines.append("| Container | Codec | Artifact | Dict | Engine | **Total** | vs best | RAM held | RAM/lookup | exact p95 ms |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
            best = min(row["total"] for row in table)
            for row in sorted(table, key=lambda item: item["total"]):
                lines.append(
                    f"| {row['container']} | {row['codec']} | {row['artifact']:,} | "
                    f"{row['dictionary']:,} | {row['engine_bytes']:,} | **{row['total']:,}** | "
                    f"{row['total'] / best:.2f}× | {row.get('resident', 0) // 1024:,} KiB | "
                    f"{row.get('transient', 0) // 1024:,} KiB | {row.get('exact_p95', '—')} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True,
                        help=f"one of {', '.join(SOURCES)} or 'all'")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many entries")
    parser.add_argument("--lenient-pos", action="store_true",
                        help="bucket an unmappable part of speech instead of failing the entry")
    parser.add_argument("--fast", action="store_true", help="skip the FTS5 variants")
    parser.add_argument("--emit-yaml", action="store_true",
                        help="write a sample of mapped entries for the fidelity check")
    parser.add_argument("--tag", default="", help="suffix for the results filename")
    parser.add_argument("--codecs", default="", help="comma-separated codec shortlist")
    parser.add_argument("--blocks", default="16,64,256", help="comma-separated block sizes")
    parser.add_argument("--finalists", action="store_true",
                        help="full-scale pass: packed candidates plus one SQLite reference")
    args = parser.parse_args()

    names = list(SOURCES) if args.source == "all" else [args.source]
    reports = []
    for name in names:
        print(f"--- {name}", file=sys.stderr)
        try:
            reports.append(measure(
                name, args.limit, args.lenient_pos, args.fast, args.emit_yaml,
                set(args.codecs.split(",")) if args.codecs else None,
                tuple(int(b) for b in args.blocks.split(",")), args.finalists))
        except Exception as error:                        # a source that cannot be read is a result
            print(f"    FAILED: {type(error).__name__}: {error}", file=sys.stderr)
            reports.append({"source": name, "error": f"{type(error).__name__}: {error}",
                            "entries": 0, "source_bytes": 0, "fidelity": 0, "mapped": 0,
                            "fields_bytes": 0, "html_bytes": 0, "dropped_fields": [],
                            "unmapped_pos": [], "invented_fields": [], "containers": {}})

    RESULTS.mkdir(parents=True, exist_ok=True)
    tag = args.tag or (args.source if args.source != "all" else "all")
    (RESULTS / f"{tag}.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    text = markdown([r for r in reports if not r.get("error")])
    (RESULTS / f"{tag}.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
