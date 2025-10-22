#!/usr/bin/env python3
"""
CLI script to clean vocabulary inbox and append generated articles into topic files.

Behavior highlights:
- Adds project/src to sys.path so the script can be run without PYTHONPATH or installing package.
- Loads .env (if python-dotenv installed) from project root.
- Loads defaults from config/defaults.toml (optional).
- CLI args override config values.
- Pre-scans topic files for existing entries and does exact & fuzzy duplicate checking.
- Processes inbox in batches; commits per batch using atomic writes and backups.
- Safe on interrupts; partial progress preserved.

Usage:
    python scripts/clean_vocab.py              # uses config/defaults.toml or CLI overrides
    python scripts/clean_vocab.py --inbox /path/to/inbox.md --batch-size 2 --show-items
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import tomllib  # Python 3.11+
from dotenv import load_dotenv
from tqdm import tqdm

# Make sure we can import local package without installing by adding repo src to sys.path.
# We assume this script lives in scripts/ under repository root.
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.resolve()
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Now import local package
from vocabgen.vocab_processor import (
    split_sections,
    join_sections_for_batch,
    split_llm_response_into_articles,
    extract_topic_from_article,
    remove_topic_line,
    parse_article_title,
    scan_topic_files_for_titles,
    find_fuzzy_matches,
    topic_filename_for_inbox,
)
from vocabgen.fileops import read_text, backup_file, atomic_write, append_to_file
from vocabgen import llm_client

logger = logging.getLogger("vocabgen.clean_vocab")


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {}
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    return cfg


def load_prompt(prompt_path: Path) -> str:
    return read_text(prompt_path).strip()


def default_model_params_from_str(s: Optional[str]) -> Dict[str, Any]:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception as e:
        raise ValueError("model-params must be a JSON string") from e


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


def scan_existing_titles(base_dir: Path) -> Dict[str, List[Tuple[Path, int, str]]]:
    return scan_topic_files_for_titles(base_dir)


def write_articles_atomic(
    inbox_path: Path,
    topic_map: Dict[str, Path],
    articles: List[str],
    existing_map: Dict[str, List[Tuple[Path, int, str]]],
    show_items: bool,
    dry_run: bool,
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
        title = parse_article_title(art)
        existing_titles = list(existing_map.keys())

        if title and title in existing_map:
            # exact match exists -> treat as conflict
            conflicts.append((title, cleaned, existing_map[title]))
            continue

        # fuzzy match
        fuzzy = []
        if title:
            fuzzy = find_fuzzy_matches(title, existing_titles, n=2, cutoff=0.85)
        if fuzzy:
            # treat as potential duplicate but still append; report
            for f in fuzzy:
                conflicts.append((title or "(no title)", cleaned, existing_map.get(f, [])))
            # still append, but mark summary accordingly

        # append
        target_file = topic_map.get(topic)
        if not target_file:
            target_file = topic_map["Misc"]
        if dry_run:
            tqdm.write(f"[dry-run] Would append to {target_file}: {cleaned.splitlines()[0]}")
        else:
            append_to_file(target_file, cleaned)
        appended += 1
        new_items.append(f"{topic}: {title or cleaned.splitlines()[0][:60]}")
        # also update existing_map so duplicates in same run are caught
        if title:
            existing_map.setdefault(title, []).append((target_file, -1, cleaned.splitlines()[0]))
    return appended, new_items, conflicts


def handle_interrupt(signum, frame):
    tqdm.write("Interrupted (signal). Will stop after current batch.")
    raise KeyboardInterrupt()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Process vocabulary inbox and generate structured vocabulary articles.")
    p.add_argument("--config", type=Path, default=Path("config/defaults.toml"), help="Path to defaults TOML config")
    p.add_argument("--inbox", type=Path, help="Inbox markdown file (overrides config)")
    p.add_argument("--prompt", type=Path, help="Prompt file with cleaning instructions")
    p.add_argument("--provider", type=str, help="LLM provider (gemini|openai|ollama)")
    p.add_argument("--model", type=str, help="LLM model name")
    p.add_argument("--batch-size", type=int, default=None, help="How many inbox sections to send per LLM call")
    p.add_argument("--model-params", type=str, default=None, help="JSON string with model params")
    p.add_argument("--max-retries", type=int, default=None)
    p.add_argument("--rate-limit", type=int, default=None, help="Requests per minute")
    p.add_argument("--show-items", action="store_true", help="Show produced items in summary")
    p.add_argument("--dry-run", action="store_true", help="Don't modify files; just show actions")
    p.add_argument("--no-dotenv", action="store_true", help="Do not auto-load .env")
    return p


def main(argv: Optional[List[str]] = None):
    signal.signal(signal.SIGINT, handle_interrupt)
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.no_dotenv:
        # load .env from repo root if present
        load_dotenv(Path(_REPO_ROOT / ".env"))

    cfg = load_config(args.config)

    # resolution order: CLI arg -> config file -> hardcoded default
    inbox_path = args.inbox or Path(cfg.get("inbox", {}).get("path")) if cfg.get("inbox") else None
    if not inbox_path:
        raise SystemExit("Inbox path must be provided by CLI or config file.")
    inbox_path = Path(inbox_path)

    prompt_path = args.prompt or Path(cfg.get("processing", {}).get("prompt", "prompts/vocabulary_prompt.txt"))
    provider = args.provider or cfg.get("llm", {}).get("provider", "gemini")
    model = args.model or cfg.get("llm", {}).get("model", "gemini-2.5-pro")
    model_params = args.model_params or cfg.get("llm", {}).get("model_params", {})
    if isinstance(model_params, str):
        model_params = default_model_params_from_str(model_params)
    max_retries = args.max_retries or cfg.get("llm", {}).get("max_retries", 2)
    rate_limit = args.rate_limit or cfg.get("llm", {}).get("rate_limit_per_minute", None)
    batch_size = args.batch_size or cfg.get("processing", {}).get("batch_size", 1)
    show_items = args.show_items or cfg.get("processing", {}).get("show_items", False)
    dry_run = args.dry_run or cfg.get("processing", {}).get("dry_run", False)

    system_prompt = load_prompt(prompt_path)
    inbox_text = read_text(inbox_path)
    sections = split_sections(inbox_text)
    total = len(sections)
    if total == 0:
        print("No sections found in inbox.")
        return

    topic_map = topic_filename_for_inbox(inbox_path)
    # Backup inbox
    bak = backup_file(inbox_path)
    logger.info("Backup created: %s", bak)

    # Pre-scan existing topic files for exact matching
    existing_map = scan_existing_titles(inbox_path.parent)

    pbar = tqdm(total=total, desc="Processing sections")
    i = 0
    new_items_all: List[str] = []
    summary: Dict[str, int] = {t: 0 for t in topic_map.keys()}

    try:
        while i < total:
            batch = sections[i : i + batch_size]
            try:
                articles = process_batch_with_llm(
                    provider=provider,
                    model=model,
                    system_prompt=system_prompt,
                    sections=batch,
                    model_params=model_params,
                    max_retries=max_retries,
                    rate_limit_per_minute=rate_limit,
                )
            except KeyboardInterrupt:
                tqdm.write("Interrupted by user before sending batch.")
                break
            except Exception as e:
                tqdm.write(f"LLM request failed for batch starting at {i}: {e}")
                pbar.update(len(batch))
                i += batch_size
                continue

            appended, new_items, conflicts = write_articles_atomic(
                inbox_path=inbox_path,
                topic_map=topic_map,
                articles=articles,
                existing_map=existing_map,
                show_items=show_items,
                dry_run=dry_run,
            )
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
                remaining = "\n\n---\n\n".join(sections[i + batch_size :])
                if dry_run:
                    tqdm.write("[dry-run] Would update inbox to remove processed sections")
                else:
                    atomic_write(inbox_path, remaining)
            pbar.update(len(batch))
            i += batch_size

    except KeyboardInterrupt:
        tqdm.write("Interrupted by user. Partial progress preserved.")
    finally:
        pbar.close()

    # Summary
    tqdm.write("Processing complete. Summary of additions:")
    for t, cnt in summary.items():
        if cnt:
            tqdm.write(f"  {t}: {cnt}")
    if show_items and new_items_all:
        tqdm.write("\nNew items produced:")
        for it in new_items_all:
            tqdm.write("  " + it)
    # Report conflicts
    if conflicts:
        tqdm.write("\nConflicts found (existing matches):")
        for title, new_art, existing_entries in conflicts:
            tqdm.write(f"Title: {title}")
            for p, lineno, snippet in existing_entries:
                tqdm.write(f"  Existing in {p} at line {lineno}: {snippet[:120]}")
            tqdm.write("  New article preview: " + new_art.splitlines()[0][:120])

    return


if __name__ == "__main__":
    main()
