from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from .manifest import SyncManifest
from .robot import AnkiRobot, RobotSettings, result_json


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
        else:
            result = robot.export_state()
        print(result_json(result))
        return 0
    except Exception as exc:
        print(f"Acervo Anki robot failed: {exc}", file=sys.stderr)
        return 2
