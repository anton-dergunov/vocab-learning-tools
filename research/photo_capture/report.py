#!/usr/bin/env python3
"""Every table in the write-up, rebuilt from cached results with no network calls.

    .venv/bin/python report.py > runs/report.md
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
from pathlib import Path

import score as S

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"


def pct(values) -> str:
    values = [v for v in values if v is not None]
    return f"{100 * sum(1 for v in values if v) / len(values):.0f}%" if values else "–"


def num(value, digits=3) -> str:
    return "–" if value is None or value != value else f"{value:.{digits}f}"


def p(values, q):
    values = sorted(values)
    if not values:
        return float("nan")
    index = min(len(values) - 1, max(0, round(q * (len(values) - 1))))
    return values[index]


def ocr_tables(report) -> None:
    print("## OCR and taps, per engine and upload\n")
    print("Sentence CER is measured by alignment, so it is independent of splitting. Tap columns are "
          "primary taps (54) with the SaT splitter; `boundary` isolates the splitter from OCR errors.\n")
    print("| Engine | Upload | Median bytes | CER camera | CER screenshot | Word hit | Word CER | "
          "Sentence OK | Sentence CER | Tap cropped away |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for arm in report["arms"]:
        if arm["segmenter"] != "S2-sat":
            continue
        prim = [r for r in arm["results"] if r["class"] == "primary"]
        text_prim = [r for r in prim if r.get("sentenceCer") is not None or r["cropped"]]
        print(f"| {arm['engine']} | {arm['variant']} | {arm['bytesMedian'] / 1000:.0f} KB | "
              f"{num(arm['cerCamera'])} | {num(arm['cerScreenshot'])} | {pct(r['wordHit'] for r in prim)} | "
              f"{num(S.mean([r['wordCer'] for r in prim]))} | {pct(r['sentenceOk'] for r in text_prim)} | "
              f"{num(S.mean([r['sentenceCer'] for r in prim]))} | {sum(r['cropped'] for r in prim)} |")
    print()


def splitter_table(report) -> None:
    print("## Sentence splitting\n")
    print("On the truth text itself, then on OCR output (full frame, 2048 px), where the page's "
          "non-sentence text — status bars, URLs, headings, show-through from the facing page — is "
          "in the stream.\n")
    print("| Splitter | Truth text: precision / recall | Vision: boundary right | RapidOCR v5m box .3: boundary right |")
    print("|---|---|---|---|")
    truth = report["segmentationOnTruth"]
    for name in truth:
        cells = []
        for engine in ("vision", "rapid-v5m-box.3"):
            arm = next((a for a in report["arms"] if a["engine"] == engine and a["variant"] == "full-2048"
                        and a["segmenter"] == name), None)
            prim = [r for r in arm["results"] if r["class"] == "primary"] if arm else []
            cells.append(pct(r["boundaryOk"] for r in prim) if arm else "–")
        print(f"| {name} | {truth[name]['precision']:.2f} / {truth[name]['recall']:.2f} "
              f"({truth[name]['boundaries']} boundaries) | {cells[0]} | {cells[1]} |")
    print()


def edge_table(report) -> None:
    print("## Edge taps (reported, not optimised for)\n")
    print("| Engine | Upload | Word hit (5 taps) |")
    print("|---|---|---|")
    for arm in report["arms"]:
        if arm["segmenter"] == "S2-sat" and arm["variant"] in ("full-2048", "centre-2048"):
            edge = [r for r in arm["results"] if r["class"] == "edge"]
            print(f"| {arm['engine']} | {arm['variant']} | {pct(r['wordHit'] for r in edge)} |")
    print()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"^(el|la|los|las|un|una)\s+", "", text.strip())
    return re.sub(r"[^\w ]", "", text).strip()


def quick_table() -> None:
    path = RUNS / "quick.json"
    if not path.exists():
        return
    runs = json.loads(path.read_text())
    taps = {t["id"]: t for t in json.loads((RUNS / "taps-vision-full-2048-sat.json").read_text())}
    print("## Tap → meaning (the quick call)\n")
    print("Sentences are Vision's OCR at 2048 px split by SaT, so OCR damage is part of the input. "
          "`exact` compares lemma to truth after folding case, accents and articles; `near` also "
          "accepts one containing the other (`cada vez más` for `cada vez`).\n")
    print("| Pair | Answered | Unit exact | Unit exact or near | Latency p50 | p90 |")
    print("|---|---|---|---|---|---|")
    pairs = sorted({r["pair"] for r in runs.values()})
    for pair in pairs:
        rows = [r for r in runs.values() if r["pair"] == pair and taps[r["tap"]]["class"] == "primary"]
        ok = [r for r in rows if r["error"] is None and r["answer"]]
        exact = [fold(r["answer"].get("lemma")) == fold(taps[r["tap"]]["unit"]) for r in ok]
        near = [(lambda a, t: a == t or (a and t and (a in t or t in a)))(fold(r["answer"].get("lemma")),
                                                                         fold(taps[r["tap"]]["unit"])) for r in ok]
        latency = [r["latency"][-1] for r in ok]
        print(f"| {pair} | {len(ok)}/{len(rows)} | {pct(exact)} | {pct(near)} | "
              f"{num(statistics.median(latency) if latency else None, 2)} s | {num(p(latency, 0.9), 2)} s |")
    print()
    print("Misses, for the owner to judge:\n")
    for pair in pairs:
        for r in runs.values():
            if r["pair"] != pair or r["error"] or not r["answer"]:
                continue
            tap = taps[r["tap"]]
            if tap["class"] == "primary" and fold(r["answer"].get("lemma")) != fold(tap["unit"]):
                print(f"- `{pair}` {tap['id']} tapped *{tap['word']}*: answered "
                      f"`{r['answer'].get('lemma')}` ({r['answer'].get('gloss')}), truth `{tap['unit']}`")
    print()


def nas_table() -> None:
    path = RUNS / "nas-bench.out"
    if not path.exists():
        return
    parts = [part.strip() for part in path.read_text().split("=====SPLIT=====") if part.strip()]
    print("## RapidOCR on the NAS\n")
    for part in parts:
        try:
            bench = json.loads(part)
        except json.JSONDecodeError:
            continue
        print(f"{bench.get('cpuModel')} · {bench['cpus']} logical CPUs · peak RSS {bench['peakRssMb']} MB\n")
        print("| Preset | Threads | Size | Median OCR per image | Slowest image |")
        print("|---|---|---|---|---|")
        groups = {}
        for run in bench["runs"]:
            size = run["image"].rsplit("-", 1)[1].split(".")[0]
            groups.setdefault((run["preset"], run["threads"], size), []).append(run["median"])
        for (preset, threads, size), values in sorted(groups.items()):
            print(f"| {preset} | {threads} | {size} | {statistics.median(values):.2f} s | {max(values):.2f} s |")
        print()


def main() -> None:
    report = S.run()
    (RUNS / "score.json").write_text(json.dumps(report, ensure_ascii=False))
    ocr_tables(report)
    splitter_table(report)
    edge_table(report)
    quick_table()
    nas_table()


if __name__ == "__main__":
    main()
