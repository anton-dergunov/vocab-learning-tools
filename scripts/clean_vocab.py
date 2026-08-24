#!/usr/bin/env python3
"""
CLI script to clean vocabulary inbox and append generated articles into topic files.

Usage:
    python scripts/clean_vocab.py
    python scripts/clean_vocab.py --config config/local.yaml
    python scripts/clean_vocab.py --config config/local.yaml --llm-provider ollama
"""

from __future__ import annotations
import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from box import Box
from jinja2 import Environment
from dotenv import load_dotenv
from tqdm import tqdm
from textwrap import indent


# Make sure we can import local package without installing by adding repo src to sys.path.
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.resolve()
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Now import local package
from vocabgen.vocab_processor import (
    join_sections_for_batch,    # TODO should not be shared
    split_llm_response_into_articles,   # TODO should not be shared
    extract_topic_from_article,
    remove_topic_line,
    scan_topic_files_for_titles,
    find_fuzzy_matches
)
# TODO Lots of import above, simplify this
from vocabgen.fileops import backup_file, append_to_file
from vocabgen.provider.factory import create_provider
from vocabgen.llm.base import LLMProvider
from vocabgen.config import load_config, select_llm_provider
from vocabgen.data.article_short import ArticleShort
from vocabgen.data.draft_inbox import DraftInbox


logger = logging.getLogger("vocabgen.clean_vocab")


# ────────────────────────────────
# Helpers
# ────────────────────────────────

# TODO Move to fileops
def resolve_path(path: Union[str, Path], base_dir: Path = _REPO_ROOT) -> Path:
    """
    Resolve a path to an absolute Path object.

    Supports both absolute and relative paths. Relative paths are resolved
    relative to the base_dir (defaults to repo root).

    Args:
        path: Path string or Path object (absolute or relative)
        base_dir: Base directory for resolving relative paths

    Returns:
        Absolute Path object

    Examples:
        >>> resolve_path("/absolute/path/file.txt")
        PosixPath('/absolute/path/file.txt')
        >>> resolve_path("relative/file.txt")  # Resolved from _REPO_ROOT
        PosixPath('/Users/anton/repo/relative/file.txt')
        >>> resolve_path("~/Documents/file.txt")  # Expands ~
        PosixPath('/Users/anton/Documents/file.txt')
    """
    path_obj = Path(path).expanduser()  # Expand ~ to home directory

    if path_obj.is_absolute():
        return path_obj.resolve()  # Resolve symlinks and .. in absolute paths
    else:
        return (base_dir / path_obj).resolve()  # Make relative paths absolute


def render_prompt(template_path: Union[str, Path], config: Box) -> str:
    env = Environment(
        trim_blocks=True,  # removes newline *after* Jinja block
        lstrip_blocks=True # removes leading spaces before blocks
    )
    tpl = env.from_string(Path(template_path).read_text())
    return tpl.render(cfg=config)


# ────────────────────────────────
# Core
# ────────────────────────────────

def ensure_trailing_newlines(path: Path, needed: int = 2):
    """Ensure file ends with at least N newlines."""
    if not path.exists():
        return
    with open(path, "rb+") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 4))
        tail = f.read().decode("utf-8", errors="ignore")
        missing = needed - tail.count("\n")
        if missing > 0:
            f.write(b"\n" * missing)


def process_batch_with_llm(
    llm: LLMProvider,
    system_prompt: str,
    sections: List[str],
) -> List[str]:
    """
    Send a batch to the LLM and return one generated article per inbox section.

    A cardinality mismatch fails the batch so its inbox sections remain available
    for a later run.
    """
    user_prompt = join_sections_for_batch(sections, sep="\n\n---\n\n")
    resp = llm.generate(system_prompt, user_prompt)
    articles = split_llm_response_into_articles(resp)
    if len(articles) != len(sections):
        raise ValueError(
            "Incomplete LLM batch: "
            f"expected {len(sections)} articles, got {len(articles)}"
        )
    return articles


def write_articles_atomic(
    topic_map: Dict[str, Path],
    articles: List[str],
    existing_map: Dict[str, List[Tuple[Path, int, str]]]
) -> Tuple[int, List[str], List[Tuple[str, str, List[Tuple[Path, int, str]]]], List[Tuple[str, str, List[Tuple[Path, int, str]]]]]:
    """
    Append articles to topic files while checking for duplicates.
    Returns (num_appended, new_item_summaries, conflicts)
    conflicts: list of tuples (title, new_article, existing_entries)
    """
    if not articles:
        raise ValueError("LLM returned no vocabulary articles")

    parsed_articles = []
    for index, markdown in enumerate(articles, start=1):
        topic = extract_topic_from_article(markdown) or "Misc"
        try:
            article = ArticleShort.parse_from_markdown(remove_topic_line(markdown))
        except ValueError as exc:
            raise ValueError(f"Malformed LLM article #{index}: {exc}") from exc
        parsed_articles.append((article, topic))

    appended = 0
    new_items = []
    conflicts = []
    fuzzy_conflicts = []

    for article, topic in parsed_articles:
        title = article.headword
        cleaned = article.to_markdown().rstrip() + "\n\n"

        existing_titles = list(existing_map.keys())

        # Exact duplicate
        if title in existing_map:
            conflicts.append((title, cleaned, existing_map[title]))
            continue

        # Fuzzy duplicate
        fuzzy = find_fuzzy_matches(title, existing_titles, n=2, cutoff=0.85)
        if fuzzy:
            fuzzy_conflicts.append((title, cleaned, [existing_map[f] for f in fuzzy if f in existing_map]))

        target_file = topic_map.get(topic, topic_map["Misc"])
        ensure_trailing_newlines(target_file, 2)
        append_to_file(target_file, cleaned)
        appended += 1
        new_items.append(f"{topic}: {title}")
        existing_map.setdefault(title, []).append((target_file, -1, cleaned.splitlines()[0]))

    return appended, new_items, conflicts, fuzzy_conflicts


def handle_interrupt(signum, frame):
    print("\nInterrupted — finishing current batch gracefully.")
    raise KeyboardInterrupt()


# ────────────────────────────────
# Main entry
# ────────────────────────────────

def main(argv: Optional[List[str]] = None):
    signal.signal(signal.SIGINT, handle_interrupt)

    p = argparse.ArgumentParser(description="Process vocabulary inbox and append new items.")
    p.add_argument(
        "--config",
        type=Path,
        help="Optional YAML file merged over config/defaults.yaml"
    )
    p.add_argument(
        "--llm-provider",
        help="LLM provider configured under llm.providers (defaults to llm.default_provider)"
    )
    args = p.parse_args(argv)

    load_dotenv()
    config = load_config(_REPO_ROOT / "config/defaults.yaml", args.config)
    provider_name, prompt_path, llm_config = select_llm_provider(
        config,
        args.llm_provider,
    )

    system_prompt = render_prompt(resolve_path(prompt_path), config)

    inbox = DraftInbox(Path(config.files.inbox))
    total = len(inbox)
    if total == 0:
        print("Inbox empty — nothing to process.")
        return

    topic_map = {t: Path(config.files.output_pattern.replace("%topic", t)) for t in config.vocabulary.topics}

    # Backup inbox
    bak = backup_file(config.files.inbox)
    logger.info("Backup created: %s", bak)

    # Pre-scan existing topic files for exact matching
    existing_map = scan_topic_files_for_titles(list(topic_map.values()))

    new_items_all = []
    summary = {t: 0 for t in topic_map}
    all_conflicts, fuzzy_conflicts = [], []

    llm = create_provider("llm", llm_config)
    logger.info("Using LLM provider: %s", provider_name)

    batch_size = config.processing.batch_size
    if batch_size <= 0:
        raise ValueError("processing.batch_size must be greater than zero")

    with tqdm(total=total, desc="Processing sections") as pbar:
        while len(inbox):
            batch = inbox.get_slice(0, batch_size)
            articles = process_batch_with_llm(
                llm,
                system_prompt=system_prompt,
                sections=batch
            )

            appended, new_items, conflicts, fuzzies = write_articles_atomic(topic_map, articles, existing_map)
            all_conflicts.extend(conflicts)
            fuzzy_conflicts.extend(fuzzies)
            for it in new_items:
                topic = it.split(":", 1)[0].strip()
                summary[topic] += 1
            new_items_all.extend(new_items)

            # Acknowledge drafts only after validation and all article writes succeed.
            inbox.remove_slice(0, len(batch))
            pbar.update(len(batch))

    # ────────────────────────────────
    # Final summary
    # ────────────────────────────────

    print("\nProcessing complete ✅\n")
    print(f"Total inbox entries: {total}")
    print(f"New items added: {len(new_items_all)}")
    print(f"Conflicts (exact, skipped): {len(all_conflicts)}")
    print(f"Conflicts (fuzzy, added): {len(fuzzy_conflicts)}")

    if any(summary.values()):
        print("\nBreakdown by topic:")
        for t, c in summary.items():
            if c:
                print(f"  {t}: {c}")

    if new_items_all:
        print("\nNewly added items:")
        for it in new_items_all:
            print("  " + it)

    # ────────────────────────────────
    # Conflict reports
    # ────────────────────────────────

    def print_conflict_block(idx, title, new_art, existing_entries, status="SKIPPED"):
        print("\n" + "─" * 60)
        print(f"Conflict #{idx}: {title}")
        print("─" * 60)
        for entries in existing_entries:
            for p, lineno, snippet in entries:
                print(f"Existing in: {p} (line {lineno})")
                print("─" * 60)
                print(indent(snippet.strip(), ""))
        print("\nProposed new article:\n" + "─" * 60)
        print(indent(new_art.strip(), ""))
        print("\n" + "─" * 60)
        print(f"Status: {status}")

    if all_conflicts or fuzzy_conflicts:
        print("\n\nConflicts found:")
        idx = 1
        for title, art, entries in all_conflicts:
            print_conflict_block(idx, title, art, [entries], status="SKIPPED")
            idx += 1
        for title, art, entries in fuzzy_conflicts:
            print_conflict_block(idx, title, art, entries, status="ADDED (fuzzy match)")
            idx += 1

if __name__ == "__main__":
    main()
