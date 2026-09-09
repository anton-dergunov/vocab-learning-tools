from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from .manifest import SyncManifest
from .robot import AnkiRobot, RobotSettings, result_json
from .state import held_by_lexeme, study_states


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize Acervo-rendered notes through a headless Anki client."
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("ACERVO_ANKI_SYNC_ENDPOINT"),
        help="Self-hosted Anki base URL, including trailing slash",
    )
    parser.add_argument(
        "--collection",
        type=Path,
        default=Path(
            os.environ.get(
                "ACERVO_ANKI_COLLECTION",
                "/var/lib/acervo/worker/collection.anki2",
            )
        ),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "ACERVO_ANKI_BACKUP_DIR",
                "/var/lib/acervo/worker/backups",
            )
        ),
    )
    parser.add_argument(
        "--template-dir",
        type=Path,
        default=Path(os.environ.get("ACERVO_ANKI_TEMPLATE_DIR", _repository_root() / "templates")),
    )
    parser.add_argument(
        "--media-timeout",
        type=float,
        default=float(os.environ.get("ACERVO_ANKI_MEDIA_TIMEOUT", "120")),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap-upload")
    bootstrap.add_argument("manifest", type=Path)
    adopt = commands.add_parser("adopt-server")
    adopt.add_argument("--confirm-no-other-clients", action="store_true")
    push = commands.add_parser("push")
    push.add_argument("manifest", type=Path)
    commands.add_parser("export-state")
    # The write half. `export-state` stays the read-only diagnostic it has always been; this is the
    # one that puts the answer where the interface can show it.
    pull = commands.add_parser(
        "pull-state", help="Write Anki's review state into Acervo as study states"
    )
    pull.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""))
    pull.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""))
    pull.add_argument("--device-id", default="ankiworker0001")
    pull.add_argument("--dry-run", action="store_true", help="Report what would be written.")
    return parser


def _settings(args: argparse.Namespace) -> RobotSettings:
    endpoint = args.endpoint
    if not endpoint:
        raise ValueError("Set --endpoint or ACERVO_ANKI_SYNC_ENDPOINT")
    return RobotSettings(
        endpoint=endpoint,
        username=os.environ.get("ACERVO_ANKI_SYNC_USERNAME", ""),
        password=os.environ.get("ACERVO_ANKI_SYNC_PASSWORD", ""),
        collection_path=args.collection.expanduser().resolve(),
        backup_dir=args.backup_dir.expanduser().resolve(),
        template_dir=args.template_dir.expanduser().resolve(),
        media_timeout_seconds=args.media_timeout,
    )


def pull_state(args: argparse.Namespace, robot: AnkiRobot) -> dict:
    """Sync down, read the scheduling, and write it through the graph route like any other client.

    A job's write path is a client's write path: same route, same validation, same revision
    allocation as a phone. The credential is the owner's own account, because every record is
    owner-scoped and a second account could not write against the owner's lexemes at all.
    """
    from acervo.client import AcervoClient

    password = os.environ.get("ACERVO_OWNER_PASSWORD", "")
    if not args.server_url or not args.owner_email or not password:
        raise ValueError(
            "Set --server-url, --owner-email and ACERVO_OWNER_PASSWORD to write study state"
        )
    exported = robot.export_state()
    with AcervoClient(args.server_url) as client:
        client.sign_in(args.owner_email, password)
        changes = client.pull_graph().get("changes") or {}
        live = {
            str(lexeme["id"]) for lexeme in changes.get("lexemes") or [] if not lexeme.get("deleted")
        }
        rows, skipped = study_states(
            exported, held_by_lexeme(changes), live, device_id=args.device_id
        )
        if args.dry_run:
            return {"operation": "pull-state", "written": 0, "would_write": len(rows),
                    "skipped": skipped, "dry_run": True}
        if rows:
            client.push_graph({"studyStates": rows}, device_id=args.device_id)
    return {"operation": "pull-state", "written": len(rows), "skipped": skipped}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        robot = AnkiRobot(_settings(args))
        if args.command in ("bootstrap-upload", "push"):
            manifest, manifest_dir = SyncManifest.load(args.manifest)
            result = (
                robot.bootstrap_upload(manifest, manifest_dir)
                if args.command == "bootstrap-upload"
                else robot.push(manifest, manifest_dir)
            )
        elif args.command == "adopt-server":
            result = robot.adopt_server(
                confirm_no_other_clients=args.confirm_no_other_clients
            )
        elif args.command == "pull-state":
            result = pull_state(args, robot)
        else:
            result = robot.export_state()
        print(result_json(result))
        return 0
    except Exception as exc:
        print(f"Acervo Anki robot failed: {exc}", file=sys.stderr)
        return 2
