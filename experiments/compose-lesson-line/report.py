#!/usr/bin/env python3
"""The tables the README quotes, printed from a scored run. Spends nothing.

`--pilot` and `--fields` are the two views meant to be read by a person before the long run: one
says whether the candidate prompt changed the shape of an article, the other shows every value of
the two new fields so their quality can be judged directly. The blind screens deliberately hide
those fields, so `--fields` is the only place anything looks at them.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def load(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "summary.json"
    if not path.exists():
        raise SystemExit(f"no summary.json in {run_dir}; run score.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def wilson(hits: int, total: int) -> tuple[float, float]:
    """A 95% interval that stays inside [0, 1] when the rate is 100%, which a normal one does not."""
    if not total:
        return (0.0, 0.0)
    z, p, n = 1.96, hits / total, total
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 2) if values else None


def by_arm_pair(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["arm"], f"{row['provider']}/{row['model'].split('/')[-1]}")].append(row)
    return grouped


def headline(rows: list[dict[str, Any]]) -> None:
    print("\n### The headline\n")
    print("| arm | pair | n | usable | senses | ex/sense | note chars | def chars | opt fields |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for (arm, pair), group in sorted(by_arm_pair(rows).items(), key=lambda kv: (kv[0][1], kv[0][0])):
        built = [r for r in group if r.get("draftBuilt")]
        low, high = wilson(len(built), len(group))
        print(f"| {arm} | {pair} | {len(group)} | {pct(len(built) / len(group))} "
              f"({pct(low)}–{pct(high)}) | {mean([r['senses'] for r in built])} "
              f"| {mean([r['examplesPerSense'] for r in built])} "
              f"| {mean([r['noteChars'] for r in built])} "
              f"| {mean([r['definitionChars'] for r in built])} "
              f"| {mean([r['optionalFields'] for r in built])} |")


def signal_against_noise(summary: dict[str, Any]) -> None:
    print("\n### The between-arm difference, against the within-arm noise\n")
    print("A difference no larger than the noise is not an effect.\n")
    print("| metric | after − before (mean) | median | same-arm noise | reads as |")
    print("| --- | ---: | ---: | ---: | --- |")
    for name, delta in summary["paired"].items():
        noise = summary["noise"].get(name, {})
        floor = noise.get("meanAbsolute")
        value = delta.get("mean")
        if value is None or floor is None:
            verdict = "not enough pairs"
        elif abs(value) <= floor:
            verdict = "**inside the noise**"
        else:
            verdict = "worse" if value < 0 else "better"
        print(f"| {name} | {value} | {delta.get('median')} | {floor} | {verdict} |")


def new_fields(rows: list[dict[str, Any]]) -> None:
    after = [r for r in rows if r["arm"] == "after" and r.get("draftBuilt")]
    if not after:
        return
    print("\n### The two new fields\n")
    print("| pair | n | primary present | single term | copied a list | wrong script | in 1st sense | "
          "emotion present | 3–12 words | = an example |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in after:
        grouped[f"{row['provider']}/{row['model'].split('/')[-1]}"].append(row)
    for pair, group in sorted(grouped.items()):
        n = len(group)
        with_primary = [r for r in group if r["primaryPresent"]]
        with_emotion = [r for r in group if r["emotionPresent"]]
        print(f"| {pair} | {n} | {pct(len(with_primary) / n)} "
              f"| {pct(sum(r['primarySingleTerm'] for r in group) / n)} "
              f"| {pct(sum(r['primaryCopiedList'] for r in group) / n)} "
              f"| {pct(sum(r['primaryWrongScript'] for r in group) / n)} "
              f"| {pct(sum(r['primaryInFirstSenseTerms'] for r in group) / n)} "
              f"| {pct(len(with_emotion) / n)} "
              f"| {pct(sum(1 for r in with_emotion if r['emotionInRange']) / len(with_emotion)) if with_emotion else '—'} "
              f"| {pct(sum(r['emotionEqualsExample'] for r in group) / n)} |")


def judge_table(run_dir: Path) -> None:
    """Layer 2. A pair the two orderings disagree about counts as no difference, and the flip rate
    is reported beside the verdict: it is this instrument's own noise."""
    folder = run_dir / "judged"
    if not folder.exists():
        return
    votes: dict[tuple, dict[str, str | None]] = defaultdict(dict)
    decided: Counter = Counter()
    for path in sorted(folder.rglob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not record.get("ok"):
            continue
        key = (record["provider"], record["model"], record["wordId"], record["repeat"])
        votes[key][record["order"]] = record.get("winnerArm")
        if record.get("decidedBy"):
            decided[record["decidedBy"]] += 1

    print("\n### The judge\n")
    print("| pair | comparisons | before wins | after wins | no difference | flipped |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    grouped: dict[str, list[tuple]] = defaultdict(list)
    for key in votes:
        grouped[f"{key[0]}/{key[1].split('/')[-1]}"].append(key)
    overall = Counter()
    flips = 0
    for pair, keys in sorted(grouped.items()):
        tally, flipped = Counter(), 0
        for key in keys:
            values = [v for v in votes[key].values() if v]
            if len(values) == 2 and values[0] != values[1]:
                tally["same"] += 1
                flipped += 1
            else:
                tally[values[0] if values else "same"] += 1
        overall += tally
        flips += flipped
        n = len(keys)
        low, high = wilson(tally["before"], n)
        print(f"| {pair} | {n} | {pct(tally['before'] / n)} ({pct(low)}–{pct(high)}) "
              f"| {pct(tally['after'] / n)} | {pct(tally['same'] / n)} | {pct(flipped / n)} |")
    total = sum(overall.values())
    low, high = wilson(overall["before"], total)
    print(f"| **all pairs** | {total} | **{pct(overall['before'] / total)}** ({pct(low)}–{pct(high)}) "
          f"| {pct(overall['after'] / total)} | {pct(overall['same'] / total)} "
          f"| {pct(flips / total)} |")
    print(f"\nWhat decided a call, when one was made: "
          + " · ".join(f"{name} {count}" for name, count in decided.most_common()))


def cost(rows: list[dict[str, Any]]) -> None:
    print("\n### Latency and cost\n")
    print("| arm | pair | median s | p90 s | req chars | reply chars | cost |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for (arm, pair), group in sorted(by_arm_pair(rows).items(), key=lambda kv: (kv[0][1], kv[0][0])):
        times = sorted(r["seconds"] for r in group if r.get("seconds"))
        spend = sum(r["costUsd"] or 0 for r in group)
        p90 = times[min(len(times) - 1, int(len(times) * 0.9))] if times else 0
        print(f"| {arm} | {pair} | {statistics.median(times):.1f} | {p90:.1f} "
              f"| {mean([r['requestChars'] for r in group]):.0f} "
              f"| {mean([r['replyChars'] for r in group if r.get('replyChars')]) or 0:.0f} "
              f"| ${spend:.4f} |")


def fields_listing(rows: list[dict[str, Any]]) -> None:
    """Every value of the two new fields, so they can be judged rather than only counted."""
    after = [r for r in rows if r["arm"] == "after" and r.get("draftBuilt")]
    print("\n## The new fields, in full\n")
    for word in sorted({r["wordId"] for r in after}):
        group = [r for r in after if r["wordId"] == word]
        print(f"\n**{word}** — {group[0]['language']}")
        for row in sorted(group, key=lambda r: (r["provider"], r["repeat"])):
            gloss = row.get("primaryGloss") or "—"
            feeling = row.get("emotionText") or ("null" if row.get("emotionNull") else "—")
            flags = "".join([
                "S" if not row["primarySingleTerm"] else " ",
                "L" if row["primaryCopiedList"] else " ",
                "?" if row["primaryWrongScript"] else " ",
                "E" if row["emotionEqualsExample"] else " ",
            ])
            print(f"  {flags} {row['provider'][:11]:11s} r{row['repeat']}  "
                  f"{gloss:28s} | {feeling}")
    print("\n`S` not a single term · `L` copied a multi-meaning shortGloss · "
          "`?` wrong script for the first gloss language · `E` identical to an example's emotion")


def pilot(rows: list[dict[str, Any]]) -> None:
    """Before and after side by side, per word: did the shape of the article change?"""
    print("\n## Pilot · the same words through both prompts\n")
    print("| word | senses b→a | examples b→a | note chars b→a | opt fields b→a | usable |")
    print("| --- | ---: | ---: | ---: | ---: | --- |")
    for word in sorted({r["wordId"] for r in rows}):
        pair = {r["arm"]: r for r in rows if r["wordId"] == word}
        before, after = pair.get("before", {}), pair.get("after", {})
        both = before.get("draftBuilt") and after.get("draftBuilt")
        def arrow(name: str) -> str:
            if not both:
                return "—"
            return f"{before.get(name)}→{after.get(name)}"
        state = "both" if both else f"before={bool(before.get('draftBuilt'))} after={bool(after.get('draftBuilt'))}"
        print(f"| {word} | {arrow('senses')} | {arrow('examples')} | {arrow('noteChars')} "
              f"| {arrow('optionalFields')} | {state} |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--fields", action="store_true", help="every primaryGloss and emotion")
    parser.add_argument("--pilot", action="store_true", help="the per-word before/after comparison")
    args = parser.parse_args()
    run_dir = Path(args.run)
    if not run_dir.is_absolute() and not run_dir.exists():
        run_dir = HERE / args.run
    summary = load(run_dir)
    rows = summary["rows"]

    if args.pilot:
        pilot(rows)
    if args.fields:
        fields_listing(rows)
    if not args.pilot and not args.fields:
        headline(rows)
        signal_against_noise(summary)
        new_fields(rows)
        judge_table(run_dir)
        cost(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
