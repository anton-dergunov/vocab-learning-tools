"""The management CLI.

Registration is closed, so this is the only way an account comes into being. It writes through the
service layer rather than over HTTP, which is why it needs no password of its own and no superuser:
there is no superuser to have.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections import defaultdict
from typing import Any

from acervo import seed_data
from acervo.domain.projection import COLLECTION_BY_NAME, projected
from acervo.repository import accounts, graph
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
        graph.merge_graph(owner["id"], SEED_DEVICE, changes)
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

    serve_parser = commands.add_parser("serve", help="run the HTTP service")
    serve_parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - the container's own port
    serve_parser.add_argument("--port", type=int, default=8000)

    arguments = parser.parse_args(argv)
    settings = read_settings()
    if arguments.command == "accounts":
        return create_account(settings, arguments.email)
    if arguments.command == "seed":
        return seed(settings, arguments.owner_email)
    if arguments.command == "providers":
        return providers()
    return serve(settings, arguments.host, arguments.port)


if __name__ == "__main__":
    raise SystemExit(main())
