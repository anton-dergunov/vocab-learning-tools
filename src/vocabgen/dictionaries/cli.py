"""Command line for the dictionary compiler.

Runs the same way in three places — a laptop, the `acervo-worker` container, and eventually a job
started from the interface — because everything it does is `build.build`, which takes a progress
callback rather than printing.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import build as builder
from .catalogue import load_catalogue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dictionary",
        description="Compile an external dictionary from the catalogue into Acervo's artifact format.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    compile_command = subcommands.add_parser("build", help="compile one dictionary, or many")
    what = compile_command.add_mutually_exclusive_group(required=True)
    what.add_argument("--id", help="catalogue id, e.g. cc-cedict")
    what.add_argument("--all", action="store_true",
                      help="every offline row, or every one matching --language")
    compile_command.add_argument(
        "--language",
        help="comma-separated source languages to build, e.g. es,en,zh. Matches the primary subtag, "
             "so `zh` covers zh-Hans and zh-Hant.",
    )
    compile_command.add_argument("--out", help="where to write the artifact (default: the served directory)")
    compile_command.add_argument("--limit", type=int, help="stop after this many entries")
    compile_command.add_argument(
        "--discard-source", action="store_true",
        help="delete each download afterwards. The default keeps it, because re-running a changed "
             "converter should not mean fetching a gigabyte again.",
    )

    verify_command = subcommands.add_parser(
        "verify", help="compile a sample into a temporary directory and report what came out")
    target = verify_command.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", help="catalogue id")
    target.add_argument("--all", action="store_true", help="every offline row in the catalogue")
    verify_command.add_argument("--limit", type=int, default=5000)

    subcommands.add_parser("list", help="show the catalogue")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "list":
        return _list()
    if arguments.command == "build":
        return _build(arguments)
    return _verify(arguments)


def _list() -> int:
    for row in load_catalogue():
        size = f"{row.approxDownloadBytes / 2**20:,.0f} MiB" if row.approxDownloadBytes else "—"
        print(f"{row.id:24} {row.kind:8} {row.sourceLang:>7}→{row.targetLang:<7} "
              f"{(row.format or ''):14} {size:>10}  {row.name}")
    return 0


def _build(arguments) -> int:
    from pathlib import Path

    destination = Path(arguments.out) if arguments.out else None
    identifiers = _selected(arguments)
    if not identifiers:
        print("Nothing in the catalogue matches that.", file=sys.stderr)
        return 1

    if len(identifiers) > 1:
        total = sum(row.approxDownloadBytes or 0 for row in load_catalogue()
                    if row.id in set(identifiers))
        print(f"Building {len(identifiers)} dictionaries, about {total / 2**30:.1f} GiB to download "
              f"(downloads already cached are reused).\n")

    failures: list[tuple[str, Exception]] = []
    for position, identifier in enumerate(identifiers, start=1):
        if len(identifiers) > 1:
            print(f"[{position}/{len(identifiers)}] {identifier}", flush=True)
        try:
            result = builder.build(
                identifier,
                destination=destination,
                limit=arguments.limit,
                discard_source=arguments.discard_source,
                progress=lambda message: print(f"  · {message}", flush=True),
            )
        except Exception as error:                              # noqa: BLE001 — a batch keeps going
            # One source moving must not abandon the ten gigabytes already downloaded behind it.
            failures.append((identifier, error))
            print(f"  ! failed: {type(error).__name__}: {error}\n", file=sys.stderr, flush=True)
            continue
        _report(result)
        print(f"  → {result.destination}\n", flush=True)

    if failures:
        print(f"{len(failures)} of {len(identifiers)} did not build:", file=sys.stderr)
        for identifier, error in failures:
            print(f"  {identifier}: {error}", file=sys.stderr)
    return 1 if failures else 0


def _selected(arguments) -> list[str]:
    """Which rows this invocation names: one id, or every offline row a language filter allows."""
    rows = [row for row in load_catalogue() if row.kind == "offline"]
    if arguments.id:
        if arguments.language:
            print("--language filters --all; it does nothing beside --id.", file=sys.stderr)
        return [arguments.id]
    if arguments.language:
        wanted = {code.strip().split("-")[0] for code in arguments.language.split(",") if code.strip()}
        rows = [row for row in rows if row.sourceLang.split("-")[0] in wanted]
    return [row.id for row in rows]


def _verify(arguments) -> int:
    identifiers = ([row.id for row in load_catalogue() if row.kind == "offline"]
                   if arguments.all else [arguments.id])
    failures = 0
    for identifier in identifiers:
        try:
            result = builder.verify(identifier, limit=arguments.limit)
        except Exception as error:                                  # noqa: BLE001 — reported, not raised
            failures += 1
            print(f"{identifier:24} FAILED  {type(error).__name__}: {error}", flush=True)
            continue
        report = result.report
        print(f"{identifier:24} ok      {report.entry_count:>7,} entries  "
              f"{report.key_count:>7,} keys  {result.total_bytes / 2**20:>6.1f} MiB  "
              f"{report.skipped:>6,} skipped", flush=True)
    if failures:
        print(f"\n{failures} of {len(identifiers)} rows could not be built.", file=sys.stderr)
    return 1 if failures else 0


def _report(result: builder.BuildResult) -> None:
    report = result.report
    print(f"{result.row.id}: {report.entry_count:,} entries, {report.key_count:,} lookup keys, "
          f"{report.frame_count:,} frames")
    print(f"  {report.blob_bytes / 2**20:.1f} MiB payloads + {report.index_bytes / 2**20:.1f} MiB "
          f"index = {result.total_bytes / 2**20:.1f} MiB in {result.seconds:.0f}s")
    if report.merged_entries:
        print(f"  {report.merged_entries:,} source entries folded into a headword already seen")
    if report.skipped:
        print(f"  {report.skipped:,} source entries had nothing renderable and were left out")
    if report.dropped_fields:
        print(f"  dropped fields with no home: {', '.join(sorted(report.dropped_fields))}")
    if report.unmapped_pos:
        print(f"  parts of speech kept as the source's own words: "
              f"{', '.join(sorted(report.unmapped_pos))}")
