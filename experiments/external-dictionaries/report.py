#!/usr/bin/env python3
"""Rebuild the markdown tables from a results JSON file.

Separate from `spike.py` so presentation can be reworked without re-running hours of measurement.

  experiments/external-dictionaries/report.py results/pilot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def kib(value: int) -> str:
    return f"{value / 1024:,.0f} KiB" if value else "—"


def mib(value: int) -> str:
    return f"{value / 1048576:,.1f}" if value else "0.0"


def representation(reports: list[dict]) -> str:
    lines = ["### Representation — is the mapper worth writing?", "",
             "| Source | Entries | Source MiB | fields MiB | html MiB | html ÷ fields | Mapped | Invented | Unmapped POS kinds |",
             "|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for report in reports:
        if report.get("error"):
            lines.append(f"| `{report['source']}` | — | — | — | — | — | — | {report['error']} | — |")
            continue
        ratio = (report["html_bytes"] / report["fields_bytes"]) if report["fields_bytes"] else 0
        lines.append(
            f"| `{report['source']}` | {report['entries']:,} | {mib(report['source_bytes'])} | "
            f"{mib(report['fields_bytes'])} | {mib(report['html_bytes'])} | "
            f"{ratio:.2f}× | {report['fidelity'] * 100:.1f} % | "
            f"{', '.join(report['invented_fields']) or '—'} | {len(report['unmapped_pos'])} |")
    return "\n".join(lines)


def containers(report: dict, tier: str, top: int | None = None) -> str:
    table = report["containers"].get(tier)
    if not table:
        return ""
    best = min(row["total"] for row in table)
    lines = [f"#### `{report['source']}` · `{tier}` payload", "",
             "| Container | Codec | Blob | Index | Dict | Library | **Total device** | vs best | RAM held | RAM/lookup | exact p95 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    rows = sorted(table, key=lambda item: item["total"])
    if top:
        rows = rows[:top]
    for row in rows:
        extra = row.get("extra") or {}
        blob = extra.get("blob", row["artifact"])
        index = extra.get("index", 0)
        lines.append(
            f"| {row['container']} | {row['codec']} | {mib(blob)} | {mib(index)} | "
            f"{kib(row['dictionary'])} | {kib(row['engine_bytes'])} | **{mib(row['total'])} MiB** | "
            f"{row['total'] / best:.2f}× | {kib(row.get('resident', 0))} | "
            f"{kib(row.get('transient', 0))} | {row.get('exact_p95', '—')} ms |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--top", type=int, default=None, help="show only the N smallest per tier")
    args = parser.parse_args()

    reports = json.loads(args.path.read_text(encoding="utf-8"))
    blocks = [representation(reports), ""]
    for report in reports:
        if report.get("error"):
            continue
        for tier in ("fields", "html"):
            block = containers(report, tier, args.top)
            if block:
                blocks += [block, ""]
    text = "\n".join(blocks)
    args.path.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
