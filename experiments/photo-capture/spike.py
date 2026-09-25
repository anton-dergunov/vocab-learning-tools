#!/usr/bin/env python3
"""The photo-capture spike. See README.md; its decisions are in docs/photo-capture.md.

    .venv/bin/python spike.py ocr [--engine rapidocr|vision|all] [--only camera-01.jpg]
    .venv/bin/python spike.py report
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import engines as E

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent / "tests" / "fixtures" / "photo-capture"
RUNS = HERE / "runs"

VARIANTS = [E.Variant(crop, edge) for crop in ("centre", "full") for edge in (1280, 2048, None)]
PRESETS = list(E.PRESETS)


def manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text())


def images(only: str | None) -> list[dict]:
    rows = manifest()["images"]
    return [row for row in rows if not only or row["file"] == only]


def cmd_ocr(args: argparse.Namespace) -> None:
    for row in images(args.only):
        path = FIXTURES / row["file"]
        for variant in VARIANTS:
            data, box, scale = E.prepare(path, variant)
            if args.engine in ("rapidocr", "all"):
                for preset in args.presets:
                    for thresh in args.box_thresh:
                        layout = E.rapidocr_read(data, preset, thresh)
                        print(f"{row['file']:14} {variant.name:12} {layout['engine']:30} "
                              f"{layout['timing']['ocr_s']:6.2f}s {len(layout['words']):4} words",
                              flush=True)
            if args.engine in ("vision", "all"):
                layout = E.vision_read(data)
                print(f"{row['file']:14} {variant.name:12} {'vision':30} "
                      f"{layout['timing']['roundtrip_s']:6.2f}s {len(layout['words']):4} words",
                      flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ocr = sub.add_parser("ocr", help="run the engines over every fixture variant (cached)")
    ocr.add_argument("--engine", choices=("rapidocr", "vision", "all"), default="all")
    ocr.add_argument("--presets", nargs="+", default=PRESETS, choices=PRESETS)
    ocr.add_argument("--box-thresh", nargs="+", type=float, default=[0.5])
    ocr.add_argument("--only")
    ocr.set_defaults(func=cmd_ocr)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
