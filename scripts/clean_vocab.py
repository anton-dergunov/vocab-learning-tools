#!/usr/bin/env python3
"""
CLI script to clean vocabulary inbox and append generated articles into topic files.

Usage:
    python scripts/clean_vocab.py              # uses config/defaults.toml or CLI overrides
    python scripts/clean_vocab.py --inbox /path/to/inbox.md --batch-size 2 --show-items
"""

from __future__ import annotations
import argparse
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import tomllib
from box import Box
from jinja2 import Environment
from dotenv import load_dotenv
from tqdm import tqdm

# Make sure we can import local package without installing by adding repo src to sys.path.
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.resolve()
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Now import local package
from vocabgen.vocab_processor import (
    split_sections,
    join_sections_for_batch,    # TODO should not be shared
    split_llm_response_into_articles,   # TODO should not be shared
    extract_topic_from_article,
    remove_topic_line,
    parse_article_title,
    scan_topic_files_for_titles,
    find_fuzzy_matches
)
from vocabgen.fileops import read_text, backup_file, atomic_write, append_to_file
from vocabgen import llm_client

logger = logging.getLogger("vocabgen.clean_vocab")


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


def load_config(path: Union[str, Path]) -> Box:
    """Load TOML config with dot notation access."""
    with open(path, 'rb') as f:
        config_dict = tomllib.load(f)

    return Box(config_dict)


def process_batch_with_llm(
    provider: str,
    model: str,
    system_prompt: str,
    sections: List[str],
    model_params: Dict[str, Any],
    max_retries: int,
    rate_limit_per_minute: Optional[int],
    batch_sep: str = "\n\n---\n\n",
) -> List[str]:
    """
    Send batch to LLM and return raw text response.
    """
    user_prompt = join_sections_for_batch(sections, sep=batch_sep)
    # Compose full prompt by putting system prompt into the system and user content in call
    # Our generate_text expects system_prompt and user_prompt separately
    resp = llm_client.generate_text(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_params=model_params,
        max_retries=max_retries,
        rate_limit_per_minute=rate_limit_per_minute,
    )
    # split into articles by '---'
    articles = split_llm_response_into_articles(resp)
    return articles


def write_articles_atomic(
    topic_map: Dict[str, Path],
    articles: List[str],
    existing_map: Dict[str, List[Tuple[Path, int, str]]]
) -> Tuple[int, List[str], List[Tuple[str, str, List[Tuple[Path, int, str]]]]]:
    """
    Append articles to topic files while checking for duplicates.
    Returns (num_appended, new_item_summaries, conflicts)
    conflicts: list of tuples (title, new_article, existing_entries)
    """
    appended = 0
    new_items = []
    conflicts = []

    for art in articles:
        topic = extract_topic_from_article(art) or "Misc"
        cleaned = remove_topic_line(art).strip() + "\n\n"
        existing_titles = list(existing_map.keys())

        title = parse_article_title(art)
        if not title:
            # TODO Display error if title failed to parse
            continue

        if title in existing_map:
            # exact match exists -> treat as conflict
            conflicts.append((title, cleaned, existing_map[title]))
            continue

        # Fuzzy match
        # TODO make these parameters configurable
        fuzzy = find_fuzzy_matches(title, existing_titles, n=2, cutoff=0.85)
        if fuzzy:
            # treat as potential duplicate but still append; report
            for f in fuzzy:
                conflicts.append((title, cleaned, existing_map.get(f, [])))
            # still append, but mark summary accordingly

        # append
        target_file = topic_map.get(topic)
        if not target_file:
            target_file = topic_map["Misc"]
        # TODO Put a warning in this case
        append_to_file(target_file, cleaned)
        appended += 1
        new_items.append(f"{topic}: {title}")
        # also update existing_map so duplicates in same run are caught
        existing_map.setdefault(title, []).append((target_file, -1, cleaned.splitlines()[0]))
    return appended, new_items, conflicts


def handle_interrupt(signum, frame):
    tqdm.write("Interrupted (signal). Will stop after current batch.")
    raise KeyboardInterrupt()


def main(argv: Optional[List[str]] = None):
    signal.signal(signal.SIGINT, handle_interrupt)

    p = argparse.ArgumentParser(description="Process vocabulary inbox and generate structured vocabulary articles.")
    p.add_argument("--config", type=Path, default=_REPO_ROOT / "config/defaults.toml", help="Path to defaults TOML config")
    args = p.parse_args(argv)

    load_dotenv(Path(_REPO_ROOT / ".env"))

    config = load_config(args.config)

    system_prompt = render_prompt(resolve_path(config.llm.prompt_path), config)

    inbox_text = read_text(config.files.inbox)
    sections = split_sections(inbox_text)
    total = len(sections)
    if total == 0:
        print("No sections found in inbox.")
        return

    topic_map = {}
    for topic in config.vocabulary.topics:
        topic_file = config.files.output_pattern.replace('%topic', topic)
        topic_map[topic] = Path(topic_file)

    # Backup inbox
    bak = backup_file(config.files.inbox)
    logger.info("Backup created: %s", bak)

    # Pre-scan existing topic files for exact matching
    existing_map = scan_topic_files_for_titles(list(topic_map.values()))

    pbar = tqdm(total=total, desc="Processing sections")
    i = 0
    new_items_all: List[str] = []
    summary: Dict[str, int] = {t: 0 for t in topic_map.keys()}
    all_conflicts = []

    try:
        while i < total:
            batch = sections[i : i + config.processing.batch_size]
            articles = process_batch_with_llm(
                provider=config.llm.provider,
                model=config.llm.model,
                system_prompt=system_prompt,
                sections=batch,
                model_params=config.llmmodel_params,
                max_retries=config.llmmax_retries,
                rate_limit_per_minute=config.llmrate_limit,
            )

            appended, new_items, conflicts = write_articles_atomic(
                topic_map=topic_map,
                articles=articles,
                existing_map=existing_map
            )
            all_conflicts.extend(conflicts)
            for it in new_items:
                # increment summary based on topic prefix
                if ":" in it:
                    topic = it.split(":", 1)[0].strip()
                    summary[topic] = summary.get(topic, 0) + 1
            new_items_all.extend(new_items)
            # If appended >= 0 (we append when at least some article was processed),
            # we remove the processed input batch from the inbox file to avoid losing
            # unprocessed ones: we remove the first i+batch_size sections.
            if appended > 0:
                # TODO Should probably reuse join_sections_for_batch
                remaining = "\n\n---\n\n".join(sections[i + config.processing.batch_size :])
                atomic_write(config.files.inbox, remaining)

            pbar.update(len(batch))
            i += config.processing.batch_size

    except KeyboardInterrupt:
        tqdm.write("Interrupted by user. Partial progress preserved.")
    except Exception as e:
        tqdm.write(f"Encountered exception: {e}")
    finally:
        pbar.close()

    # TODO Probably no sense to use tqdm.write any more, since progress bar is closed
    # Summary
    tqdm.write("Processing complete. Summary of additions:")
    for t, cnt in summary.items():
        if cnt:
            tqdm.write(f"  {t}: {cnt}")
    if config.processing.show_items and new_items_all:
        tqdm.write("\nNew items produced:")
        for it in new_items_all:
            tqdm.write("  " + it)

    # Report conflicts
    if all_conflicts:
        tqdm.write("\nConflicts found (existing matches):")
        for title, new_art, existing_entries in all_conflicts:
            tqdm.write(f"Title: {title}")
            for p, lineno, snippet in existing_entries:
                tqdm.write(f"  Existing in {p} at line {lineno}: {snippet[:120]}")
            tqdm.write("  New article preview: " + new_art.splitlines()[0][:120])

    return


if __name__ == "__main__":
    main()
