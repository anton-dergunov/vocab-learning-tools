#!/usr/bin/env python3
"""Walk a messy vocabulary notes file into Acervo, one entry at a time.

A thin transport against the ingest endpoint (design §05): it holds no prompt and knows nothing
about what an article contains. It submits a window of lines, the server works out which single
entry sits at the front of it and how many lines that entry occupied, and the walk advances by
exactly that much. Everything lands in the Inbox for review in the app.

The source file is never modified unless you ask for it:

    # resumable, and leaves the notes byte-identical
    scripts/ingest_vocabulary_file.py "~/notes/English vocabulary.md" \
        --server-url https://acervo.example.com --owner-email learner@account.example.com

    # cuts each processed entry out of the file, so what is left is the queue
    scripts/ingest_vocabulary_file.py copy-of-notes.md --consume ...
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from vocabgen.provider.rate_limiter import RateLimiter  # noqa: E402

API_PATH = "/api/acervo/v1"
SCHEMA_VERSION = 5
DEVICE_ID = "ingestscript01"
REQUEST_TIMEOUT = 180
DEFAULT_CHECKPOINTS = Path.home() / ".acervo" / "ingest"
SEPARATORS = {"", "---", "***", "___"}


class AcervoError(Exception):
    def __init__(self, message: str, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def call(self, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}{API_PATH}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        request.add_header("Accept", "application/json")
        if data:
            request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read()).get("data") or {}
        except urllib.error.HTTPError as error:
            body = {}
            try:
                body = json.loads(error.read())
            except Exception:  # noqa: BLE001 - the body is diagnostic, not required
                pass
            problem = body.get("error") or {}
            raise AcervoError(
                problem.get("message") or f"The server refused the request ({error.code}).",
                problem.get("code", ""),
                error.code,
            ) from error
        except urllib.error.URLError as error:
            raise AcervoError(f"The Acervo server could not be reached: {error.reason}") from error

    def sign_in(self, email: str, password: str) -> None:
        result = self.call("/session", {"email": email, "password": password})
        self.token = result["token"]


def logical_block(lines: list[str]) -> int:
    """How far to skip when the server could not read the front of the window at all.

    Only a fallback. Blocks in these files are separated by a blank line or a rule often enough
    that this keeps a walk moving past junk without spending a call on every single line.
    """
    for index, line in enumerate(lines):
        if index and line.strip() in SEPARATORS:
            while index < len(lines) and lines[index].strip() in SEPARATORS:
                index += 1
            return index
    return len(lines)


def leading_blanks(lines: list[str]) -> int:
    count = 0
    while count < len(lines) and lines[count].strip() in SEPARATORS:
        count += 1
    return count


def checkpoint_path(directory: Path, source: Path) -> Path:
    return directory / f"{source.resolve().name}.json"


def read_offset(path: Path, source: Path) -> int:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    # A checkpoint against a file that has since changed length is meaningless, and resuming from
    # it would skip or repeat entries silently.
    if state.get("lines") != count_lines(source):
        return 0
    return int(state.get("offset", 0))


def write_offset(path: Path, source: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"file": str(source.resolve()), "lines": count_lines(source), "offset": offset}),
        encoding="utf-8",
    )


def count_lines(source: Path) -> int:
    return len(source.read_text(encoding="utf-8").splitlines())


def capture(client: Client, text: str, language: str, topics: list[str], apply: bool) -> dict:
    return client.call("/capture", {
        "schemaVersion": SCHEMA_VERSION,
        "deviceId": DEVICE_ID,
        "mode": "stream",
        "apply": apply,
        "text": text,
        "language": language or None,
        "topics": topics,
        "sourceKind": "unknown",
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="the notes file to walk")
    parser.add_argument("--server-url", default=os.getenv("ACERVO_SERVER_URL", ""))
    parser.add_argument("--owner-email", default=os.getenv("ACERVO_OWNER_EMAIL", ""))
    parser.add_argument("--window-lines", type=int, default=40,
                        help="how many lines to show the server at a time (default: 40)")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many entries")
    parser.add_argument("--language", default="", help="a hint, verified by the server")
    parser.add_argument("--topic", action="append", default=[],
                        help="the topic this file is already filed under; may be repeated")
    parser.add_argument("--rate-limit", type=int, default=10, help="requests per minute (default: 10)")
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINTS,
                        help="where progress is remembered, outside the notes themselves")
    parser.add_argument("--restart", action="store_true", help="ignore the checkpoint and start again")
    parser.add_argument("--dry-run", action="store_true",
                        help="build entries and show them, but create nothing")
    parser.add_argument("--consume", action="store_true",
                        help="cut each processed entry out of the source file (a .bak is written first)")
    args = parser.parse_args()

    source: Path = args.file.expanduser()
    if not source.is_file():
        print(f"No such file: {source}", file=sys.stderr)
        return 2
    if args.window_lines < 1:
        print("--window-lines must be at least 1", file=sys.stderr)
        return 2

    server_url = args.server_url.strip() or input("Acervo server URL: ").strip()
    email = args.owner_email.strip() or input("Account email: ").strip()
    password = os.getenv("ACERVO_PASSWORD") or getpass.getpass("Account password: ")
    if not server_url or not email or not password:
        print("A server, an account and a password are required", file=sys.stderr)
        return 2

    client = Client(server_url)
    try:
        client.sign_in(email, password)
    except AcervoError as error:
        print(f"Could not sign in: {error}", file=sys.stderr)
        return 1

    if args.consume and not args.dry_run:
        backup = source.with_suffix(source.suffix + ".bak")
        if not backup.exists():
            backup.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  backup written to {backup}")

    marker = checkpoint_path(args.checkpoint_dir, source)
    # In consume mode the file itself is the progress, so an offset would double-count.
    offset = 0 if (args.consume or args.restart) else read_offset(marker, source)
    limiter = RateLimiter(args.rate_limit)
    created = skipped = failed = 0

    while True:
        lines = source.read_text(encoding="utf-8").splitlines()
        if offset >= len(lines):
            break
        if args.limit and created + skipped + failed >= args.limit:
            break

        # Free, and it keeps blank runs and rule lines from costing a model call each.
        blanks = leading_blanks(lines[offset:])
        if blanks:
            offset += blanks
            if args.consume and not args.dry_run:
                source.write_text("\n".join(lines[blanks:]) + "\n", encoding="utf-8")
                offset = 0
            continue

        window = lines[offset:offset + args.window_lines]
        limiter.acquire()
        try:
            result = capture(client, "\n".join(window), args.language, args.topic, not args.dry_run)
        except AcervoError as error:
            if error.code == "language_not_configured":
                # Every entry in the file will hit this, so stopping is kinder than 700 failures.
                print(f"\n{error}", file=sys.stderr)
                return 1
            if error.code in {"capture_unavailable", "prompt_missing", "schema_version_mismatch"}:
                print(f"\n{error}", file=sys.stderr)
                return 1
            step = logical_block(window)
            print(f"  ✗ {error}  — skipping {step} {'line' if step == 1 else 'lines'}")
            failed += 1
            consumed = step
            headword = None
        else:
            resolution = result.get("resolution") or {}
            consumed = max(1, int(resolution.get("consumedLines") or 1))
            headword = resolution.get("headword")
            if result.get("duplicates"):
                names = ", ".join(item["headword"] for item in result["duplicates"])
                print(f"  · {headword or '?'}  already in your vocabulary as {names} — skipped")
                skipped += 1
            elif args.dry_run:
                draft = result.get("draft") or {}
                senses = len(draft.get("senses") or [])
                print(f"  ~ {draft.get('headword', headword)}  ({senses} {'sense' if senses == 1 else 'senses'}, {consumed} lines) — not created")
                created += 1
            else:
                print(f"  ✓ {headword}  ({consumed} {'line' if consumed == 1 else 'lines'})")
                created += 1

        consumed = min(consumed, len(window))
        if args.consume and not args.dry_run:
            remaining = lines[offset + consumed:]
            source.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
        else:
            offset += consumed
            if not args.dry_run:
                write_offset(marker, source, offset)

    total = len(source.read_text(encoding="utf-8").splitlines())
    print(f"\n{created} created, {skipped} already known, {failed} skipped.")
    if args.consume and not args.dry_run:
        print(f"{total} lines left in {source.name}.")
    elif not args.dry_run:
        print(f"At line {offset} of {total} — {source.name} is unchanged; rerun to continue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
