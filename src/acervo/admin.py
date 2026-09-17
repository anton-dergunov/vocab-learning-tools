"""The management CLI.

Registration is closed, so this is the only way an account comes into being. It writes through the
service layer rather than over HTTP, which is why it needs no password of its own and no superuser:
there is no superuser to have.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from collections import defaultdict
from typing import Any

from acervo import seed_data
from acervo.domain.projection import COLLECTION_BY_NAME, projected
from acervo.models import journal
from acervo.repository import accounts, graph, jobs
from acervo.repository.session import open_database
from acervo.settings import Settings, settings as read_settings

SEED_DEVICE = "acervoseed"


def _read_password(prompt: str) -> str:
    """The password, from a terminal or from a pipe, but always after saying it wants one.

    `docker exec -i` without `-t` gives a pipe, not a terminal — so echo cannot be suppressed and
    `getpass` is not an option. Printing the prompt anyway is what separates "waiting for you" from
    "hung": without it the command sits silent with the cursor on a blank line, which is exactly what
    it looks like when something has locked up.
    """
    print(prompt, end="", file=sys.stderr, flush=True)
    if sys.stdin.isatty():
        # A terminal, so the typing can be hidden. `getpass` writes its own prompt; ours has already
        # gone to stderr, so it is given an empty one.
        password = getpass.getpass("")
    else:
        password = sys.stdin.readline().rstrip("\n")
    print(file=sys.stderr)
    return password


def create_account(settings: Settings, email: str) -> int:
    open_database(settings.database_path)
    password = _read_password(f"Password for {email}: ")
    if sys.stdin.isatty():
        if password != getpass.getpass("Repeat it: "):
            print("The passwords do not match.", file=sys.stderr)
            return 2
    try:
        created = accounts.create(email, password)
    except (ValueError, accounts.AccountExists) as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    # Deliberately not the record id. It is the `ownerId` on every record this account will hold,
    # not a secret — but an unexplained 15-character string next to a password prompt reads like one,
    # and nobody typing this command has a use for it.
    print(f"Created {created['email']}.")
    return 0


def seed(settings: Settings, email: str) -> int:
    open_database(settings.database_path)
    owner = accounts.by_email(email)
    if owner is None:
        print(f"No account for {email}. Create one first with `accounts create`.", file=sys.stderr)
        return 2

    held = graph.held_ids(owner["id"])
    changes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for name, row in seed_data.demo_records(owner["id"]):
        if row["id"] in held:
            # The graph route is not the old per-record create: re-posting a stored record at
            # revision zero is a stale write, not a no-op. Skipping by id is what makes a second run
            # harmless.
            skipped += 1
            continue
        collection = COLLECTION_BY_NAME[name]
        changes[collection.key].append(projected(collection, {**row, "revision": 0}))

    written = sum(len(records) for records in changes.values())
    if written:
        # Disposable demonstration words: enriching them would spend the owner's allowances on
        # vocabulary nobody meant to keep.
        graph.merge_graph(owner["id"], SEED_DEVICE, changes, enqueue=None)
    print(f"Seeded {written} records for {email}; {skipped} already held.")
    return 0


def serve(settings: Settings, host: str, port: int) -> int:
    import uvicorn

    from acervo.api.app import create_app

    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
    return 0


def providers() -> int:
    """Print which providers this machine can use, and whose account each one spends.

    The same reading on a laptop and inside the server container, so "am I about to spend my work
    Google account?" has one answer arrived at one way. It calls nothing and spends nothing: every
    line comes from the catalogue and the environment.
    """
    from acervo.models import load_catalogue
    from acervo.models.catalogue import identity, key_hint, reason, row_settings

    for row in load_catalogue():
        why = reason(row)
        print(f"{'yes' if why is None else 'no ':>3}  {row.label}")
        print(f"     kinds     {', '.join(row.kinds)}")
        for kind in row.kinds:
            print(f"     {kind:<9} {', '.join(row.models_for(kind))}")
        # The same three facts Settings ▸ Providers renders, so the terminal reading and the pane
        # cannot disagree about which credential is deployed. Four characters at each end of a key
        # is the whole disclosure, here as there.
        if row.keyEnv:
            print(f"     key       {row.keyEnv} {key_hint(row) or '(not set)'}")
        elif row.authEnv:
            print(f"     key       {row.authEnv} (a credentials file)")
        for name, value in row_settings(row):
            print(f"     setting   {name}={value or '(not set)'}")
        if (account := identity(row)) is not None:
            print(f"     account   {account}")
        if why is not None:
            print(f"     why not   {why}")
    return 0


def call_timings(settings: Settings) -> int:
    """How long each job actually takes, per model, from the call log.

    The reading a timeout should be set from. A bound picked by feel is either so long that a dead
    connection reads as a hung page — two minutes of "Writing a brief…" for a brief that takes two
    seconds — or so short that a legitimately slow answer is thrown away. The durations have been
    recorded all along; this is the part that was missing.
    """
    path = settings.call_log_path
    if not path or not path.exists():
        print(f"No call log at {path or '(disabled)'}.")
        return 1
    # Rotated files too, oldest first, so a summary is not silently a summary of the last few hours.
    lines: list[str] = []
    for backup in sorted(path.parent.glob(f"{path.name}.*"), reverse=True):
        lines.extend(backup.read_text(encoding="utf-8", errors="replace").splitlines())
    lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())

    rows = journal.summarise(lines)
    if not rows:
        print(f"{len(lines)} line(s) in {path}, none of them a model call.")
        return 1
    print(f"{'job':10} {'provider:model':46} {'ok':>4} {'fail':>5} "
          f"{'median':>7} {'p95':>7} {'worst':>7} {'lost':>8}")
    for row in rows:
        print(f"{row.caller:10} {row.pair:46} {row.answered:4d} {row.failed:5d} "
              f"{row.at(.5):6.2f}s {row.at(.95):6.2f}s {row.at(1):6.2f}s {row.lost:7.2f}s")
    slowest = max(row.at(1.0) for row in rows)
    print(f"\nSlowest answer seen: {slowest:.2f}s. A timeout wants headroom over that, not over a "
          f"guess — and a call past it is not slow, it is gone.")
    return 0


def open_jobs(settings: Settings, as_json: bool) -> int:
    """What a deploy reads before it touches anything: how many jobs are open, and of what kind."""
    open_database(settings.database_path)
    held = jobs.open_jobs()
    by_kind: dict[str, int] = defaultdict(int)
    for job in held:
        by_kind[job["kind"]] += 1
    if as_json:
        print(json.dumps({"open": len(held), "byKind": dict(sorted(by_kind.items()))}))
    elif not held:
        print("No jobs are open.")
    else:
        kinds = ", ".join(f"{count} {kind}" for kind, count in sorted(by_kind.items()))
        print(f"{len(held)} job(s) open ({kinds}).")
    return 0


def list_jobs(settings: Settings) -> int:
    open_database(settings.database_path)
    for job in jobs.open_jobs():
        subject = job["subject"] or {}
        print(f"{job['id']}  {job['state']:<9} {job['kind']:<16} "
              f"{subject.get('kind', '')}:{subject.get('id', '')}  {job['createdAt']}")
    return 0


def cancel_jobs(settings: Settings, job_id: str | None, wait: float) -> int:
    """Cancel every open job (or one), and wait for the runner to let go of the running ones.

    Cancellation is cooperative: the runner stops at its next check, between model calls. A call
    already in flight is abandoned rather than waited out — after `wait` seconds the job is closed
    as cancelled whether or not the runner has agreed, because the process is about to stop anyway.
    """
    open_database(settings.database_path)
    if job_id is None:
        running = jobs.cancel_all()
    else:
        job = next((j for j in jobs.open_jobs() if j["id"] == job_id), None)
        if job is None:
            print(f"No open job {job_id}.", file=sys.stderr)
            return 2
        jobs.request_cancel(job["ownerId"], job_id)
        running = [job] if job["state"] == "running" else []
    deadline = time.monotonic() + max(0.0, wait)
    while running and time.monotonic() < deadline:
        still = {j["id"] for j in jobs.open_jobs() if j["state"] == "running"}
        running = [j for j in running if j["id"] in still]
        if running:
            time.sleep(0.5)
    if running:
        abandoned = jobs.abandon_running()
        print(f"Abandoned {abandoned} job(s) still in a model call.")
    print("Cancelled." if job_id else "Every open job is cancelled.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="acervo.admin", description="Manage an Acervo server.")
    commands = parser.add_subparsers(dest="command", required=True)

    account_parser = commands.add_parser("accounts", help="accounts")
    account_commands = account_parser.add_subparsers(dest="account_command", required=True)
    create = account_commands.add_parser("create", help="create an account, reading the password from stdin")
    create.add_argument("--email", required=True)

    seed_parser = commands.add_parser("seed", help="insert disposable demonstration vocabulary")
    seed_parser.add_argument("--owner-email", required=True)

    commands.add_parser("providers", help="what this machine can call, and as whom")

    commands.add_parser("calls", help="how long each job takes per model, from the call log")

    jobs_parser = commands.add_parser("jobs", help="the work the server is doing")
    job_commands = jobs_parser.add_subparsers(dest="job_command", required=True)
    open_parser = job_commands.add_parser("open", help="how many jobs are open")
    open_parser.add_argument("--json", action="store_true")
    job_commands.add_parser("list", help="every open job")
    cancel_parser = job_commands.add_parser("cancel", help="cancel open jobs")
    which = cancel_parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true")
    which.add_argument("job_id", nargs="?")
    cancel_parser.add_argument(
        "--wait", type=float, default=30.0,
        help="seconds to wait for the runner before abandoning a job still in a model call",
    )

    serve_parser = commands.add_parser("serve", help="run the HTTP service")
    serve_parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - the container's own port
    serve_parser.add_argument("--port", type=int, default=8000)

    arguments = parser.parse_args(argv)
    settings = read_settings()
    if arguments.command == "calls":
        return call_timings(settings)
    if arguments.command == "accounts":
        return create_account(settings, arguments.email)
    if arguments.command == "seed":
        return seed(settings, arguments.owner_email)
    if arguments.command == "providers":
        return providers()
    if arguments.command == "jobs":
        if arguments.job_command == "open":
            return open_jobs(settings, arguments.json)
        if arguments.job_command == "list":
            return list_jobs(settings)
        return cancel_jobs(settings, None if arguments.all else arguments.job_id, arguments.wait)
    return serve(settings, arguments.host, arguments.port)


if __name__ == "__main__":
    raise SystemExit(main())
