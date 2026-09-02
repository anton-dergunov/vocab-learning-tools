#!/usr/bin/env python3
"""Part C — the online dictionary path: access and display, never scraped, never stored.

Tests §7's claim that freedictionaryapi and the Wikimedia REST endpoint "share the offline
wiktextract mapper". They do not: both are Wiktionary-derived but each ships its own field shape,
so this measures how large the fork actually is.

  experiments/external-dictionaries/online.py --words picar,desmayarse,balsa --lang es
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sources  # noqa: E402

RESULTS = HERE / "results"
OUT = HERE.parents[1] / "data" / "dictionaries" / "out"
AGENT = "AcervoDictionarySpike/0.1 (https://acervo.example.com)"
TAG = re.compile(r"<[^>]+>")

DEFAULT_WORDS = ["picar", "desmayarse", "balsa", "gratis", "correr", "mesa", "aunque", "rápidamente",
                 "zzzznotaword"]


def fetch(url: str) -> tuple[dict | list | None, float, int]:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, (time.perf_counter() - started) * 1000, response.status
    except urllib.error.HTTPError as error:
        return None, (time.perf_counter() - started) * 1000, error.code
    except Exception:
        return None, (time.perf_counter() - started) * 1000, 0


# --- freedictionaryapi -------------------------------------------------------------------------
# Shape: entries[].partOfSpeech, .pronunciations[].text, .senses[].definition (a string),
#        .senses[].examples (strings). Wiktextract uses pos, sounds[].ipa, senses[].glosses (a
#        list) and senses[].examples[].text — related data, different field names and arities.

def free_fields(payload: dict, language: str, lenient: bool) -> sources.Entry:
    entry = sources.Entry(key=payload.get("word", ""), lemma=payload.get("word", ""))
    entries = payload.get("entries") or []
    if not entries:
        return entry
    head = entries[0]
    pos = sources.POS_MAP.get((head.get("partOfSpeech") or "").lower())
    if pos is None:
        entry.pos_unmapped.add(head.get("partOfSpeech") or "")
        if not lenient:
            return entry
        pos = sources.LENIENT_POS
    senses = []
    for block in entries:
        for sense in block.get("senses") or []:
            definition = sense.get("definition")
            if not definition:
                continue
            item = {"order": len(senses), "definition": definition, "definitionLang": language}
            examples = [{"text": text, "textLang": language, "origin": "wiktionary"}
                        for text in (sense.get("examples") or [])[:3] if text]
            if examples:
                item["examples"] = examples
            senses.append(item)
            entry.dropped |= {"synonyms", "antonyms", "quotes", "subsenses", "tags"} & set(sense)
        entry.dropped |= {"forms", "pronunciations"} & set(block)
    if not senses:
        return entry
    draft = {"language": language, "headword": entry.key, "lemma": entry.key, "pos": pos,
             "status": "inbox", "senses": senses}
    ipa = next((p.get("text") for p in head.get("pronunciations") or []
                if (p.get("text") or "").startswith("/")), None)
    if ipa:
        draft["ipa"] = ipa
    entry.fields = draft
    return entry


def free_html(payload: dict) -> str:
    out = [f"<h1>{escape(payload.get('word', ''))}</h1>"]
    for block in payload.get("entries") or []:
        out.append(f"<h2>{escape(block.get('partOfSpeech', ''))}</h2><ol>")
        for sense in block.get("senses") or []:
            if not sense.get("definition"):
                continue
            out.append(f"<li>{escape(sense['definition'])}")
            for text in (sense.get("examples") or [])[:3]:
                out.append(f"<blockquote>{escape(text)}</blockquote>")
            out.append("</li>")
        out.append("</ol>")
    return "".join(out)


# --- Wikimedia REST ----------------------------------------------------------------------------
# Shape: {lang: [{partOfSpeech, definitions: [{definition: HTML, parsedExamples: [{example: HTML}]}]}]}
# The definitions arrive as HTML fragments, so a fields mapper has to strip markup — which is
# exactly the "extracting from HTML" case that argues for rendering instead of mapping.

def rest_fields(payload: dict, language: str, lenient: bool, word: str) -> sources.Entry:
    entry = sources.Entry(key=word, lemma=word)
    blocks = payload.get(language) or []
    if not blocks:
        return entry
    pos = sources.POS_MAP.get((blocks[0].get("partOfSpeech") or "").lower())
    if pos is None:
        entry.pos_unmapped.add(blocks[0].get("partOfSpeech") or "")
        if not lenient:
            return entry
        pos = sources.LENIENT_POS
    senses = []
    for block in blocks:
        for item in block.get("definitions") or []:
            text = TAG.sub("", item.get("definition") or "").strip()
            if not text:
                continue
            entry.dropped.add("(definitions arrive as HTML; markup stripped)")
            sense = {"order": len(senses), "definition": text, "definitionLang": language}
            examples = [{"text": TAG.sub("", ex.get("example") or "").strip(),
                         "textLang": language, "origin": "wiktionary"}
                        for ex in (item.get("parsedExamples") or [])[:3]]
            examples = [ex for ex in examples if ex["text"]]
            if examples:
                sense["examples"] = examples
            senses.append(sense)
    if not senses:
        return entry
    entry.fields = {"language": language, "headword": word, "lemma": word, "pos": pos,
                    "status": "inbox", "senses": senses}
    return entry


def rest_html(payload: dict, language: str, word: str) -> str:
    out = [f"<h1>{escape(word)}</h1>"]
    for block in payload.get(language) or []:
        out.append(f"<h2>{escape(block.get('partOfSpeech', ''))}</h2><ol>")
        for item in block.get("definitions") or []:
            # Already HTML at the source, so this tier needs sanitising rather than mapping.
            out.append(f"<li>{item.get('definition', '')}</li>")
        out.append("</ol>")
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--words", default=",".join(DEFAULT_WORDS))
    parser.add_argument("--lang", default="es")
    parser.add_argument("--lenient-pos", action="store_true")
    args = parser.parse_args()
    words = [w for w in args.words.split(",") if w]

    report = {"language": args.lang, "words": len(words), "apis": {}}
    yaml_rows = []

    for api in ("freedictionaryapi", "wikimedia-rest"):
        latencies, mapped, html_bytes, fields_bytes, misses = [], 0, 0, 0, 0
        dropped, unmapped = set(), set()
        for word in words:
            if api == "freedictionaryapi":
                url = f"https://freedictionaryapi.com/api/v1/entries/{args.lang}/{word}"
            else:
                # The definition endpoint exists only on the English Wiktionary; the response is
                # keyed by language code, so the target language is selected from the payload.
                url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{word}"
            payload, ms, status = fetch(url)
            latencies.append(ms)
            if payload is None:
                misses += 1
                continue
            if api == "freedictionaryapi":
                entry = free_fields(payload, args.lang, args.lenient_pos)
                entry.html = free_html(payload)
            else:
                entry = rest_fields(payload, args.lang, args.lenient_pos, word)
                entry.html = rest_html(payload, args.lang, word)
            dropped |= entry.dropped
            unmapped |= entry.pos_unmapped
            html_bytes += len(entry.html.encode())
            if entry.fields:
                mapped += 1
                fields_bytes += len(json.dumps(entry.fields, ensure_ascii=False).encode())
                yaml_rows.append({"source": api, "key": entry.key, "yaml": _to_yaml(entry.fields)})

        report["apis"][api] = {
            "requests": len(words), "misses": misses, "mapped": mapped,
            "acceptance": round(mapped / max(1, len(words) - misses), 3),
            "latency_p50_ms": round(statistics.median(latencies), 1),
            "latency_max_ms": round(max(latencies), 1),
            "fields_bytes": fields_bytes, "html_bytes": html_bytes,
            "dropped": sorted(dropped), "unmapped_pos": sorted(unmapped),
        }

    if yaml_rows:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "online.yaml.jsonl").open("w", encoding="utf-8") as handle:
            for row in yaml_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "online.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    lines = ["| API | Requests | Misses | Mapped | p50 ms | max ms | fields B | html B |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for api, data in report["apis"].items():
        lines.append(f"| `{api}` | {data['requests']} | {data['misses']} | {data['mapped']} | "
                     f"{data['latency_p50_ms']} | {data['latency_max_ms']} | "
                     f"{data['fields_bytes']:,} | {data['html_bytes']:,} |")
    text = "\n".join(lines)
    (RESULTS / "online.md").write_text(text, encoding="utf-8")
    print(text)
    for api, data in report["apis"].items():
        print(f"\n{api}: dropped={data['dropped']} unmapped_pos={data['unmapped_pos']}")
    return 0


def _to_yaml(draft: dict) -> str:
    import spike
    return spike.to_yaml(draft)


if __name__ == "__main__":
    sys.exit(main())
