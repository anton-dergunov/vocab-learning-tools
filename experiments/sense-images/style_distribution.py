#!/usr/bin/env python3
"""How the style distribution moved as the style hints came and went.

Three eras, taken from the prompt version stamped on every record:

    before   the writer chose from styles that carried only their own description
    hints    every style also carried a `when` saying what it was for  (round 5)
    after    the hints were no longer sent, and two styles were broadened

The eras hold very different numbers of images, so everything is a share of its
own era. Reads the run directory; writes a PNG and prints the table.

    .venv/bin/python experiments/sense-images/style_distribution.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]

# The style-table digest is the second field of a prompt version, and it changed at each of these
# points, so it identifies the eras.
FIXED_HINTS = "3f5c6ec25"      # round 5: one `when` sentence per style, sent every time
NO_HINTS = "ab741596e"         # round 6: nothing but each style's own description
SAMPLED_HINTS = "729604463a61" # round 7: three of a style's example subjects, drawn per lexeme

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")   # validated slots 1-4, light mode

ERAS = (
    ("before", "no hints yet"),
    ("fixed", "one fixed hint each"),
    ("none", "hints removed"),
    ("sampled", "three sampled hints"),
)


def era_of(prompt_version: str) -> str:
    if SAMPLED_HINTS in prompt_version:
        return "sampled"
    if NO_HINTS in prompt_version:
        return "none"
    if FIXED_HINTS in prompt_version:
        return "fixed"
    return "before"


def collect(run_dir: Path) -> dict[str, Counter]:
    counts = {era: Counter() for era, _ in ERAS}
    for path in (run_dir / "records").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not (run_dir / "images" / f"{record['id']}.webp").exists():
            continue                                   # rejected or not yet drawn
        counts[era_of(record["promptVersion"])][record["styleId"]] += 1
    return counts


def chart(counts: dict[str, Counter], styles: list[str], output: Path) -> None:
    labels = [
        (era, f"{name} (n={sum(counts[era].values())})", SERIES[index])
        for index, (era, name) in enumerate(ERAS)
    ]
    totals = {era: sum(counts[era].values()) or 1 for era, _, _ in labels}
    even = 100 / len(styles)

    height = 0.21
    fig, axes = plt.subplots(figsize=(11.5, 13.6), facecolor=SURFACE)
    axes.set_facecolor(SURFACE)

    for offset, (era, label, colour) in enumerate(labels):
        centres = [index + (1.5 - offset) * height for index in range(len(styles))]
        shares = [counts[era][style] / totals[era] * 100 for style in styles]
        axes.barh(centres, shares, height=height * 0.92, color=colour, label=label,
                  linewidth=0.8, edgecolor=SURFACE, zorder=3)
        for centre, share in zip(centres, shares):
            if share > 0:
                # A style used twice in 498 is 0.4%, and printing "0" beside a visible bar reads as
                # a bug rather than a rounding.
                text = f"{share:.0f}" if share >= 1 else "<1"
                axes.text(share + 0.35, centre, text, va="center", ha="left",
                          fontsize=7.5, color=INK_2, zorder=4)

    axes.axvline(even, color=INK_2, linewidth=1, linestyle=(0, (4, 3)), zorder=2)
    axes.text(even, len(styles) - 0.35, f"  an even {even:.1f}% each", fontsize=8.5,
              color=INK_2, va="bottom", ha="left")

    axes.set_yticks(range(len(styles)))
    axes.set_yticklabels(styles, fontsize=9.5, color=INK)
    axes.invert_yaxis()
    axes.set_xlabel("share of the images drawn in that era (%)", fontsize=9.5, color=INK_2)
    axes.tick_params(axis="x", labelsize=9, colors=INK_2, length=0)
    axes.tick_params(axis="y", length=0)
    axes.xaxis.grid(True, color=GRID, linewidth=1, zorder=0)
    axes.set_axisbelow(True)
    for side in ("top", "right", "left", "bottom"):
        axes.spines[side].set_visible(False)

    axes.set_title("Which style the brief writer chose", fontsize=15, color=INK,
                   loc="left", pad=26, fontweight="semibold")
    axes.text(0, 1.012, "Sense images · a share of each era, because the eras differ in size",
              transform=axes.transAxes, fontsize=10, color=INK_2, va="bottom")
    axes.legend(loc="lower right", frameon=False, fontsize=9.5, labelcolor=INK_2)

    fig.tight_layout()
    fig.savefig(output, dpi=170, facecolor=SURFACE)
    print(f"wrote {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, default=REPO_ROOT / "output" / "images")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).parent / "results" / "style-distribution.png")
    args = parser.parse_args()

    counts = collect(args.run_dir)
    styles = sorted(
        {style for era in counts.values() for style in era},
        key=lambda style: -sum(era[style] for era in counts.values()),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    chart(counts, styles, args.out)

    totals = {era: sum(value.values()) or 1 for era, value in counts.items()}
    print("\n" + f"{'style':<24}" + "".join(f"{era:>16}" for era, _ in ERAS))
    for style in styles:
        cells = "".join(
            f"{counts[era][style]:>9} {counts[era][style] / totals[era] * 100:>5.1f}%"
            for era, _ in ERAS
        )
        print(f"{style:<24}{cells}")
    print(f"{'TOTAL':<24}" + "".join(f"{totals[era]:>9} {'100.0':>5}%" for era, _ in ERAS))
    print()
    for era, name in ERAS:
        used = len(counts[era])
        top = counts[era].most_common(2)
        share = sum(count for _, count in top) / totals[era] * 100
        print(f"{name:>22}: {used}/{len(styles)} styles used, top two = {share:.0f}%  "
              f"({', '.join(style for style, _ in top)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
