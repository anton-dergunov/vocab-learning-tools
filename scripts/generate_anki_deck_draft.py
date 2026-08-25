#!/usr/bin/env python3
"""Build an Anki deck or a standalone HTML preview from ArticleExtended JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.resolve()
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vocabgen.anki.preview import render_preview
from vocabgen.config import load_config
from vocabgen.data.article_extended import ArticleExtended
from vocabgen.fileops import slugify_filename


def resolve_project_path(value: str | Path, project_root: Path = _REPO_ROOT) -> Path:
    """Resolve configured and CLI paths consistently from the project root."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else project_root / path


def _load_settings(config_path: Optional[Path]):
    override_path = resolve_project_path(config_path) if config_path else None
    return load_config(_REPO_ROOT / "config" / "defaults.yaml", override_path)


def _common_paths(config):
    anki = config.anki
    template_dir = resolve_project_path(anki.template_dir)
    cache_dir = resolve_project_path(anki.cache_dir)
    output_dir = resolve_project_path(anki.output_dir)
    return anki, template_dir, cache_dir, output_dir


def _default_output(article: ArticleExtended, output_dir: Path, suffix: str) -> Path:
    return output_dir / f"{slugify_filename(article.word)}{suffix}"


def preview_command(args: argparse.Namespace) -> Path:
    article = ArticleExtended.load_from_file(resolve_project_path(args.input))
    config = _load_settings(args.config)
    _, template_dir, cache_dir, output_dir = _common_paths(config)
    output_path = (
        resolve_project_path(args.output)
        if args.output
        else _default_output(article, output_dir, ".html")
    )
    result = render_preview(article, template_dir, cache_dir, output_path)
    print(f"HTML preview written to {result}")
    return result


def build_command(args: argparse.Namespace) -> Path:
    # These imports deliberately happen only for a real deck build. Previewing
    # does not load genanki or either heavyweight media backend.
    try:
        from vocabgen.anki.builder import build_deck, write_package
        from vocabgen.anki.media import generate_article_media
        from vocabgen.provider.factory import create_provider
    except ImportError as exc:
        raise RuntimeError(
            "Anki/media dependencies are missing. Install them with "
            "'pip install -r requirements/media.txt'."
        ) from exc

    article = ArticleExtended.load_from_file(resolve_project_path(args.input))
    config = _load_settings(args.config)
    anki, template_dir, cache_dir, output_dir = _common_paths(config)
    output_path = (
        resolve_project_path(args.output)
        if args.output
        else _default_output(article, output_dir, ".apkg")
    )

    tts_provider = create_provider("tts", config.tts.to_dict())
    image_provider = create_provider("vision", config.image.to_dict())
    media = generate_article_media(
        article,
        cache_dir,
        image_provider,
        tts_provider,
        force=args.force_media,
    )
    deck, media_files = build_deck(
        article,
        media,
        template_dir,
        model_id=int(anki.model_id),
        deck_id=int(anki.deck_id),
        deck_name=args.deck_name or str(anki.deck_name),
    )
    result = write_package(deck, media_files, output_path)
    print(f"Anki deck written to {result}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Anki study material from validated extended-article JSON."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    preview = commands.add_parser(
        "preview",
        help="Render standalone HTML without generating media or loading Anki.",
    )
    preview.add_argument("input", type=Path, help="ArticleExtended JSON file")
    preview.add_argument("--config", type=Path, help="Optional local YAML overlay")
    preview.add_argument("--output", type=Path, help="HTML output path")
    preview.set_defaults(handler=preview_command)

    build = commands.add_parser(
        "build",
        help="Generate/reuse media and build an Anki package.",
    )
    build.add_argument("input", type=Path, help="ArticleExtended JSON file")
    build.add_argument("--config", type=Path, help="Optional local YAML overlay")
    build.add_argument("--output", type=Path, help=".apkg output path")
    build.add_argument("--deck-name", help="Override the configured Anki deck name")
    build.add_argument(
        "--force-media",
        action="store_true",
        help="Regenerate media even when deterministic cache files already exist.",
    )
    build.set_defaults(handler=build_command)
    return parser


def main(argv: Optional[list[str]] = None) -> Path:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    main()
