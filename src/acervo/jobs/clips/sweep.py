"""Finding clips for the words nobody is watching: a sweep, not a watcher.

**The work is derived from a query, never from a queue.** "Which words have never been consulted"
is `clipsSearchedAt IS NULL`, so a lost event cannot lose work, the sweep being down for a week
costs latency and nothing else, and every run is idempotent by construction. That is the same rule
the picture sweep lives by, and it is what makes two engines safe: the interface searches the word
you just saved, this searches everything else, and because a clip example's id is derived from its
sense and the segment it quotes, the two converge on one row with no coordination at all.

It calls the service's **own route**, through `acervo.client`. That is the layering rule — a job's
write path is a client's write path — and it earns its keep here twice over: the corpus search, the
model call and the graph write all happen in one place, and this cannot become a second pipeline
because it has no way to search or to write by itself.

**One word is one unit.** Unlike pictures, where a word is a brief plus a picture per sense, a clip
search is one search and one text call covering every sense at once, so `--limit` counts words and
a word is either done or untouched.
"""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from acervo.article import GENERATED_STATUSES
from acervo.client import AcervoClient, AcervoError

DEVICE_ID = "clipsweep00001"
# The three the file ingestion retries on, plus the two the corpus can raise for the same reason: a
# service that is busy or briefly down says nothing about the request, so waiting is the whole of
# the response. `corpus_unconfigured` is deliberately absent — that is a deployment to fix.
TRANSIENT = {
    "llm_rate_limited", "llm_unavailable", "llm_unreachable",
    "corpus_unreachable", "corpus_unavailable",
}
RETRY_DELAYS = (30.0, 60.0, 120.0)


@dataclass
class Swept:
    searched: int = 0
    found: int = 0
    empty: int = 0
    skipped: int = 0
    dropped: int = 0
    failed: int = 0
    problems: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (
            f"searched {self.searched} · with clips {self.found} · empty {self.empty} · "
            f"skipped {self.skipped} · dropped ids {self.dropped} · failed {self.failed}"
        )


def _live(records: list[dict]) -> list[dict]:
    return [record for record in records if not record.get("deleted")]


def plan(changes: dict[str, list[dict]], *, language: str | None = None) -> list[dict[str, Any]]:
    """Every word never consulted, newest first.

    Newest first because a word added today is the one being learned today, and a sweep that is
    interrupted should have spent its time on that rather than on the oldest thing in the store.

    A word with `clipsSearchedAt` set is **not** here even when it holds no clips, and that is the
    whole point of the field being a date rather than a flag: consulted-and-found-nothing is the
    common answer, and re-asking it would spend a model call to re-learn that the corpus is thin.
    """
    senses = {sense["lexemeId"] for sense in _live(changes.get("senses", []))}
    wanted = [
        word for word in _live(changes.get("lexemes", []))
        if word.get("status") in GENERATED_STATUSES
        and word.get("clipsSearchedAt") is None
        and word["id"] in senses            # a word with no senses has nothing to illustrate
        and (not language or word.get("language") == language)
    ]
    wanted.sort(key=lambda word: (word.get("createdAt", ""), word["id"]), reverse=True)
    return wanted


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
    settings = client.clip_settings()
    if not settings.get("searchEnabled", True):
        report("Looking for clips is switched off in Settings ▸ Clips.")
        return Swept()
    corpus = settings.get("corpus") or {}
    if not corpus.get("configured"):
        report("This server has no spoken-usage corpus configured, so there is nothing to search.")
        return Swept()
    if not corpus.get("reachable") or not corpus.get("ready"):
        report("The corpus is not answering with an index yet, so nothing can be searched.")
        return Swept()

    # A language the corpus does not index is skipped without being marked, so the sweep would ask
    # for it every night forever. Filtering here costs one round trip instead of one per word.
    indexed = set(corpus.get("indexedLanguages") or ())
    swept = Swept()
    words = plan(client.pull_graph()["changes"], language=language)
    report(f"{len(words)} word(s) have never been searched.")

    for word in words:
        if limit and swept.searched >= limit:
            report(f"Reached the limit of {limit}.")
            break
        if word.get("language") not in indexed:
            swept.skipped += 1
            continue
        try:
            answer = _attempt(
                lambda: client.find_clips(word["id"], device_id=device_id), report=report
            ) or {}
        except AcervoError as error:
            swept.failed += 1
            swept.problems.append(f"{word.get('headword', '')}: {error.code}")
            report(f"  ✗ {word.get('headword', '')} · {error.code}")
            continue

        swept.dropped += int(answer.get("dropped") or 0)
        if not answer.get("searched"):
            swept.skipped += 1
            continue
        swept.searched += 1
        found = len(answer.get("examples") or [])
        if found:
            swept.found += 1
            report(f"  ✓ {word.get('headword', '')} · {found} clip(s)")
        else:
            # Nothing was good enough, which is the expected outcome for most words and is recorded
            # rather than retried: the word is marked and this sweep will not see it again.
            swept.empty += 1

    report(swept.line())
    return swept


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="acervo_worker.py clips", description=__doc__)
    parser.add_argument("command", choices=("plan", "sweep"))
    parser.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
    parser.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
    parser.add_argument("--language", default="", help="Only this language. Empty means every one.")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many words.")
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
            for word in words:
                print(f"{word.get('headword', ''):<24} {word.get('language', '')}")
            print(f"{len(words)} word(s) have never been searched.")
            return 0
        result = sweep(
            client, language=args.language or None, limit=args.limit, device_id=args.device_id
        )
        return 1 if result.problems else 0
    except AcervoError as error:
        print(f"error: {error}", flush=True)
        return 1
