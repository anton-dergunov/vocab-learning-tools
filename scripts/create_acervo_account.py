#!/usr/bin/env python3
"""Create one Acervo account on a PocketBase server.

Accounts are administrator-created by design (§04): there is no sign-up route, and nothing else in
the repository makes one. Rebuilding the database with `./deploy.sh --reset-pocketbase` empties the
`users` collection along with everything else, so this is the first step after every rebuild and
before the seeder, which only ever attaches records to an account that already exists.

    scripts/create_acervo_account.py --server-url https://acervo.example.com \
        --owner-email learner@account.example.com
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.seed_acervo_demo import PocketBase, normalize_server_url  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--owner-email", required=True, help="the account to create")
    parser.add_argument("--superuser-email", default=os.getenv("ACERVO_PB_SUPERUSER_EMAIL", ""))
    args = parser.parse_args()

    server = normalize_server_url(args.server_url)
    owner_email = args.owner_email.strip()
    admin_email = args.superuser_email.strip() or input("PocketBase superuser email: ").strip()
    admin_password = os.getenv("ACERVO_PB_SUPERUSER_PASSWORD") or getpass.getpass("PocketBase superuser password: ")

    client = PocketBase(server)
    auth = client.request("POST", "/api/collections/_superusers/auth-with-password", {
        "identity": admin_email, "password": admin_password,
    })
    client.token = auth["token"]

    owner_filter = urllib.parse.quote(f'email="{owner_email}"')
    existing = client.request("GET", f"/api/collections/users/records?perPage=2&filter={owner_filter}").get("items", [])
    if existing:
        print(f"{owner_email} already exists; nothing to do.")
        return 0

    password = os.getenv("ACERVO_OWNER_PASSWORD") or getpass.getpass(f"Password for {owner_email}: ")
    confirmation = os.getenv("ACERVO_OWNER_PASSWORD") or getpass.getpass("Repeat the password: ")
    if password != confirmation:
        print("The passwords do not match.", file=sys.stderr)
        return 2
    if len(password) < 8:
        print("PocketBase requires at least 8 characters.", file=sys.stderr)
        return 2

    client.request("POST", "/api/collections/users/records", {
        "email": owner_email, "password": password, "passwordConfirm": password, "verified": True,
    })
    print(f"Created {owner_email}. Sign in to Acervo with it, or seed it with scripts/seed_acervo_demo.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
