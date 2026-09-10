"""Drawing the pictures nobody is watching: a sweep, not a watcher.

**The work is derived from a query, never from a queue.** "Which senses have no live image prompt
with a picture" is a `SELECT`, so a lost event cannot lose work, the sweep being down for a week
costs latency and nothing else, and every run is idempotent by construction. This is the design's
own rule and it is what makes two engines safe: the interface enriches the word you just saved, this
enriches everything else, and because an image prompt's id is derived from its sense id the two
converge on the same row with no coordination at all.

It calls the service's **own routes**, through `acervo.client`, exactly as `anki pull-state` does.
That is the layering rule — a job's write path is a client's write path — and here it earns its keep
twice over: the model call, the media write and the graph write all happen in one place, and the
sweep cannot become a second pipeline because it has no way to draw a picture itself.

Deliberately **no rate limiter of its own**. `acervo.models.pacing` is process-local and the server
is a different process, so there is nothing here to share with it; the chain's fall-through plus a
backoff on exactly the three transient codes *is* the pacing. Building a cross-process limiter would
be inventing a problem.
"""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from acervo.client import AcervoClient, AcervoError
# The one thing shared with the pipeline: which statuses are worth spending a picture on. Cheap to
# import — `acervo.images.article` pulls in no provider library, which is why this job needs neither
# LiteLLM nor Pillow in the worker image. It draws nothing itself; the server does.
from acervo.images.article import GENERATED_STATUSES

DEVICE_ID = "imagesweep0001"
# The three the file ingestion retries on, and for the same reason: a provider that is busy says
# nothing about the request, so waiting is the whole of the response.
TRANSIENT = {"llm_rate_limited", "llm_unavailable", "llm_unreachable"}
RETRY_DELAYS = (30.0, 60.0, 120.0)


@dataclass
class Swept:
    briefed: int = 0
    drawn: int = 0
    refused: int = 0
    skipped: int = 0
    failed: int = 0
    problems: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (
            f"briefed {self.briefed} · drawn {self.drawn} · refused {self.refused} · "
            f"skipped {self.skipped} · failed {self.failed}"
        )


def _live(records: list[dict]) -> list[dict]:
    return [record for record in records if not record.get("deleted")]


def plan(changes: dict[str, list[dict]], *, language: str | None = None) -> list[dict[str, Any]]:
    """One entry per word that still needs something, newest word first.

    Newest first because a word added today is the one being learned today, and a sweep that is
    interrupted should have spent its time on that rather than on the oldest thing in the store.
    """
    words = {word["id"]: word for word in _live(changes.get("lexemes", []))}
    senses = _live(changes.get("senses", []))
    prompts = _live(changes.get("imagePrompts", []))
    by_sense = {row["senseId"]: row for row in prompts if row.get("senseId")}

    wanted: dict[str, dict[str, Any]] = {}
    for sense in senses:
        word = words.get(sense["lexemeId"])
        if word is None or word.get("status") not in GENERATED_STATUSES:
            continue
        if language and word.get("language") != language:
            continue
        row = by_sense.get(sense["id"])
        entry = wanted.setdefault(
            word["id"],
            {"lexemeId": word["id"], "headword": word.get("headword", ""),
             "createdAt": word.get("createdAt", ""), "unbriefed": 0, "drawable": []},
        )
        if row is None:
            entry["unbriefed"] += 1
        elif not row.get("imageRef") and not row.get("suppressed"):
            entry["drawable"].append(row)

    ready = [entry for entry in wanted.values() if entry["unbriefed"] or entry["drawable"]]
    ready.sort(key=lambda entry: (entry["createdAt"], entry["lexemeId"]), reverse=True)
    return ready


def _attempt(call: Callable[[], dict], *, report: Callable[[str], None]) -> dict | None:
    """One route call, waiting out exactly the transient refusals and no others.

    An authentication failure or a rejected configuration is a mistake to fix, not a condition to
    route around — waiting on one would hide it and spend the night doing nothing.
    """
    for index, delay in enumerate((*RETRY_DELAYS, None)):
        try:
            return call()
        except AcervoError as error:
            if error.code not in TRANSIENT or delay is None:
                raise
            report(f"  … {error.code}; waiting {delay:.0f}s (attempt {index + 1})")
            time.sleep(delay)
    return None


def sweep(client: AcervoClient, *, language: str | None = None, limit: int = 0,
          device_id: str = DEVICE_ID, report: Callable[[str], None] = print) -> Swept:
    """Brief and draw what is missing, one model call per request, until the limit is reached.

    `limit` counts *pictures*, not words, because a picture is what costs money and takes a minute.
    A word whose brief is written but whose pictures the limit cut off is not a half-finished write:
    the rows are in the graph saying what to draw, and the next run draws them.
    """
    settings = client.image_settings()
    if not settings.get("sweepEnabled", True):
        report("Unattended drawing is switched off in Settings ▸ Pictures.")
        return Swept()
    if not settings.get("available", False):
        report("This server has no picture provider configured, so there is nothing to draw with.")
        return Swept()

    max_attempts = int(settings.get("maxAttempts") or 4)
    swept = Swept()
    words = plan(client.pull_graph()["changes"], language=language)
    report(f"{len(words)} word(s) still need pictures.")

    for entry in words:
        if limit and swept.drawn + swept.refused >= limit:
            report(f"Reached the limit of {limit}.")
            break

        drawable = list(entry["drawable"])
        if entry["unbriefed"]:
            try:
                answer = _attempt(
                    lambda: client.brief_lexeme(entry["lexemeId"], device_id=device_id),
                    report=report,
                )
            except AcervoError as error:
                swept.failed += 1
                swept.problems.append(f"{entry['headword']}: {error.code}")
                report(f"  ✗ {entry['headword']} · {error.code}")
                continue
            swept.briefed += 1
            written = (answer or {}).get("imagePrompts", [])
            report(f"  ✎ {entry['headword']} · {len(written)} sense(s) described")
            drawable = [
                row for row in written
                if not row.get("imageRef") and not row.get("suppressed") and row.get("prompt")
            ]

        for row in drawable:
            if limit and swept.drawn + swept.refused >= limit:
                break
            # Past the threshold nothing tries again. This is the whole reason `attempts` is a
            # column: without it a permanently blocked sense was retried every night forever.
            if int(row.get("attempts") or 0) >= max_attempts:
                swept.skipped += 1
                continue
            try:
                drawn = _attempt(
                    lambda: client.render_image(row["id"], device_id=device_id), report=report
                )
            except AcervoError as error:
                swept.failed += 1
                swept.problems.append(f"{entry['headword']}: {error.code}")
                report(f"  ✗ {entry['headword']} · {error.code}")
                continue
            if (drawn or {}).get("imageRef"):
                swept.drawn += 1
                report(f"  ✓ {entry['headword']} · {drawn['styleId']} · {drawn['imageModelId']}")
            else:
                # The provider looked at the prompt and declined. Recorded, not raised: the row now
                # says why, and the threshold is what stops it being asked again.
                swept.refused += 1
                report(f"  · {entry['headword']} · {(drawn or {}).get('failureReason') or 'declined'}")

    report(swept.line())
    return swept


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="acervo_worker.py images", description=__doc__)
    parser.add_argument("command", choices=("plan", "sweep"))
    parser.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
    parser.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
    parser.add_argument("--language", default="", help="Only this language. Empty means every one.")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many pictures.")
    parser.add_argument("--device-id", default=DEVICE_ID)
    args = parser.parse_args(argv)

    if not args.server_url or not args.owner_email:
        parser.error("--server-url and --owner-email are required (or set them in the environment)")
    password = os.environ.get("ACERVO_OWNER_PASSWORD", "")
    if not password:
        parser.error("ACERVO_OWNER_PASSWORD is not set")

    client = AcervoClient(args.server_url)
    try:
        client.sign_in(args.owner_email, password)
        if args.command == "plan":
            words = plan(client.pull_graph()["changes"], language=args.language or None)
            for entry in words:
                print(
                    f"{entry['headword']:<24} {entry['unbriefed']} to describe · "
                    f"{len(entry['drawable'])} to draw"
                )
            print(f"{len(words)} word(s).")
            return 0
        result = sweep(
            client,
            language=args.language or None,
            limit=args.limit,
            device_id=args.device_id,
        )
        return 1 if result.problems else 0
    except AcervoError as error:
        print(f"error: {error}", flush=True)
        return 1
