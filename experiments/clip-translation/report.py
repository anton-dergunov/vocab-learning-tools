"""The tables the write-up quotes, out of `summary.json`.

The before/after claim rests on the **paired** table, not on two unpaired rates: the same passage,
the same pair, the same repeat index, under both prompts. With thirty-odd rows per cell, unpaired
percentages cannot carry it.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence


def wilson(hits: int, total: int) -> tuple[float, float]:
    """A 95% interval that stays inside [0, 1] when the rate is 100%, which a normal one does not."""
    if not total:
        return (0.0, 0.0)
    z = 1.96
    phat = hits / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def median(values: Sequence[float]) -> float:
    return round(statistics.median(values), 2) if values else 0.0


def coverage_table(rows: Sequence[dict]) -> str:
    # `severe` is the column that matches the product failure rather than the metric: a translation
    # missing under half its passage is not a slightly worse translation, it is a different passage
    # put under the reader's eyes.
    out = ["| arm | pair | n picked | pick rate | mean coverage | fully covered (95% CI) | "
           "severe (<0.6) | wrong language | median rel. length | p10 rel. length | numerals kept |",
           "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row["status"] != "ok" or row["expect"] != "usable" or row.get("mode") != "translate":
            continue
        groups[(row["arm"], f"{row['provider']}/{row['model'].split('/')[-1]}")].append(row)
        groups[(row["arm"], "all pairs")].append(row)
    for (arm, pair), group in sorted(groups.items(), key=lambda kv: (kv[0][1] == "all pairs", kv[0])):
        picked = [r for r in group if r.get("picked")]
        if not picked:
            out.append(f"| {arm} | {pair} | 0 | 0% | — | — | — | — | — | — | — |")
            continue
        full = sum(1 for r in picked if r["full"])
        low, high = wilson(full, len(picked))
        rel = sorted(r["relativeLength"] for r in picked if r.get("relativeLength"))
        p10 = rel[max(0, int(len(rel) * 0.1) - 1)] if rel else 0.0
        numerals = [r for r in picked if r.get("numeralsKept") is not None]
        out.append(
            f"| {arm} | {pair} | {len(picked)} | {pct(len(picked) / len(group))} | "
            f"{statistics.mean(r['score'] for r in picked):.3f} | "
            f"{pct(full / len(picked))} ({pct(low)}–{pct(high)}) | "
            f"{sum(1 for r in picked if r['score'] < 0.6)} | "
            f"{sum(1 for r in picked if r.get('inTargetScript') is False)} | "
            f"{median(rel):.2f} | {p10:.2f} | "
            f"{pct(sum(1 for r in numerals if r['numeralsKept']) / len(numerals)) if numerals else '—'} |")
    return "\n".join(out)


def paired_table(rows: Sequence[dict]) -> str:
    """The same cell under both prompts. McNemar's exact test, which is what a paired 2×2 asks for."""
    by_cell: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        if row["status"] != "ok" or row["expect"] != "usable" or row.get("mode") != "translate":
            continue
        key = (row["provider"], row["model"], row["passageId"], row["targetLang"], row["repeat"])
        by_cell[key][row["arm"]] = row

    # Only cells where **both** arms picked. A cell where one arm refused is not a cell where it
    # translated badly — refusing is the prompt's first rule and a success — and counting a refusal
    # as an incomplete translation was quietly charging the rewrite for doing the right thing.
    # Refusal movement is Table 2's question and is reported there.
    both = {k: v for k, v in by_cell.items()
            if "before" in v and "after" in v and v["before"].get("picked")
            and v["after"].get("picked")}

    def complete(row: dict) -> bool:
        return bool(row.get("full"))

    fixed = sum(1 for v in both.values() if not complete(v["before"]) and complete(v["after"]))
    broke = sum(1 for v in both.values() if complete(v["before"]) and not complete(v["after"]))
    kept = sum(1 for v in both.values() if complete(v["before"]) and complete(v["after"]))
    neither = len(both) - fixed - broke - kept

    discordant = fixed + broke
    p = (sum(math.comb(discordant, i) for i in range(min(fixed, broke) + 1))
         / 2 ** discordant * 2) if discordant else 1.0
    p = min(1.0, p)

    return (f"Paired on {len(both)} cells where both arms picked (same passage, pair and "
            f"repeat):\n\n"
            f"| | after complete | after incomplete |\n| --- | ---: | ---: |\n"
            f"| **before complete** | {kept} | {broke} |\n"
            f"| **before incomplete** | {fixed} | {neither} |\n\n"
            f"{fixed} cells fixed, {broke} broken. McNemar exact p = {p:.4f}.")


def selection_table(rows: Sequence[dict]) -> str:
    """Did the rewrite make the selector pick more? Paired, on select-mode requests only.

    Paired for the reason the coverage table is: Cloudflare reached its daily allowance part way
    through this run and was parked, which left it with more `before` requests than `after` ones.
    Comparing those two rates directly would be comparing different question sets. Only cells
    answered under **both** prompts count, and the rest are reported as the gap they are.
    """
    cells: dict[tuple, dict[str, dict]] = defaultdict(dict)
    dropped = 0
    for row in rows:
        # Select mode only. A translate-mode request offers one candidate for one sense, so its pick
        # rate says nothing about whether the selector has become less willing to refuse.
        if row.get("mode") != "select":
            continue
        if row["status"] != "ok":
            dropped += 1
            continue
        key = (row["provider"], row["model"], row["passageId"], row["repeat"])
        cells[key][row["arm"]] = row

    paired = {k: v for k, v in cells.items() if "before" in v and "after" in v}
    unpaired = len(cells) - len(paired)

    groups: dict[str, list[dict[str, dict]]] = defaultdict(list)
    for key, arms in paired.items():
        groups[f"{key[0]}/{key[1].split('/')[-1]}"].append(arms)
        groups["all pairs"].append(arms)

    out = ["| pair | paired requests | picked before | picked after | Δ | "
           "the passage the off-by-default rule rejects, refused | invented ids |",
           "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for pair, group in sorted(groups.items(), key=lambda kv: kv[0] == "all pairs"):
        before = sum(1 for a in group if a["before"].get("picked"))
        after = sum(1 for a in group if a["after"].get("picked"))
        # The one passage the prompt argues should be refused — but only in the section that ships
        # off, so this is a reading of that rule rather than a score.
        unusable = [a for a in group if a["before"]["passageId"] == "puertita-quedar"]
        refused_after = sum(1 for a in unusable if not a["after"].get("picked"))
        out.append(
            f"| {pair} | {len(group)} | {pct(before / len(group))} | {pct(after / len(group))} | "
            f"{(after - before) / len(group) * 100:+.0f} pp | "
            f"{f'{refused_after}/{len(unusable)}' if unusable else '—'} | "
            f"{sum((a['before']['dropped'] or 0) + (a['after']['dropped'] or 0) for a in group)} |")
    note = ""
    if unpaired or dropped:
        note = (f"\n\n{unpaired} request(s) answered under only one prompt and {dropped} that did "
                f"not answer are excluded: Cloudflare reached its daily allowance during the second "
                f"repeat and was parked.")
    return "\n".join(out) + note


def cost_table(rows: Sequence[dict]) -> str:
    out = ["| arm | pair | calls | median s | p90 s | median prompt chars | median reply chars | "
           "reported cost |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row["status"] != "ok":
            continue
        groups[(row["arm"], f"{row['provider']}/{row['model'].split('/')[-1]}")].append(row)
    for (arm, pair), group in sorted(groups.items()):
        seconds = sorted(r["seconds"] for r in group if r.get("seconds"))
        p90 = seconds[min(len(seconds) - 1, int(len(seconds) * 0.9))] if seconds else 0
        cost = sum(r["costUsd"] or 0 for r in group)
        out.append(
            f"| {arm} | {pair} | {len(group)} | {median(seconds):.2f} | {p90:.2f} | "
            f"{median([r['promptChars'] for r in group]):.0f} | "
            f"{median([r['replyChars'] for r in group]):.0f} | "
            f"{('$%.4f' % cost) if cost else 'not reported'} |")
    return "\n".join(out)


def disagreements(rows: Sequence[dict]) -> str:
    """Rows where the two metrics disagree. If this list is long, the anchors are wrong."""
    out = []
    for row in rows:
        if not row.get("picked") or row["status"] != "ok":
            continue
        rel = row.get("relativeLength")
        if row["full"] and rel is not None and rel < 0.8:
            out.append(f"- `{row['passageId']}` {row['targetLang']} ({row['arm']}, "
                       f"{row['provider']}): fully covered but only {rel:.2f} of normal length")
        if not row["full"] and rel is not None and rel > 0.95:
            out.append(f"- `{row['passageId']}` {row['targetLang']} ({row['arm']}, "
                       f"{row['provider']}): normal length ({rel:.2f}) but coverage "
                       f"{row['score']:.2f}")
        if row.get("shared"):
            out.append(f"- `{row['passageId']}` {row['targetLang']} ({row['arm']}, "
                       f"{row['provider']}): a repetition scored only by sharing one occurrence")
    return "\n".join(out) or "- none: the anchors and the length prior agree on every row."


def worst(rows: Sequence[dict], limit: int = 3) -> str:
    picked = [r for r in rows if r.get("picked") and r["status"] == "ok"]
    out = []
    for row in sorted(picked, key=lambda r: r["score"])[:limit]:
        out.append(f"**`{row['passageId']}` → {row['targetLang']}, {row['arm']} prompt, "
                   f"{row['provider']}** — coverage {row['score']:.2f}, "
                   f"{row['ratio']:.2f} of the source's length:\n\n"
                   f"> {row['translation']}\n")
    return "\n".join(out)


def main(argv: Sequence[str]) -> int:
    if not argv:
        print("usage: report.py <run directory> [<run directory> …]")
        return 2
    rows: list[dict] = []
    reference: dict[str, float] = {}
    modes: set[str] = set()
    for name in argv:
        summary = json.loads((Path(name) / "summary.json").read_text(encoding="utf-8"))
        rows += summary["rows"]
        reference.update(summary["referenceRatios"])
    translate = [r for r in rows if r.get("status") is not None and "score" in r or True]

    print("## Translation coverage\n")
    print(coverage_table(rows))
    print(f"\nReference ratios (median length ratio of complete translations, per target "
          f"language): {reference}\n")
    print("## The paired comparison\n")
    print(paired_table(rows))
    print("\n## Selection health\n")
    print(selection_table(rows))
    print("\n## Latency and cost\n")
    print(cost_table(rows))
    print("\n## Where the two metrics disagree\n")
    print(disagreements(rows))
    print("\n## The worst translations in the run\n")
    print(worst(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
