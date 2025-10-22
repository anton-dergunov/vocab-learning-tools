#!/usr/bin/env python3
"""
scripts/clean_vocab.py

Usage examples:

# basic run (uses defaults / environment)
python scripts/clean_vocab.py \
  --inbox "/Users/anton/Dropbox/notes/obsidian/Languages/Spanish/Vocabulary/Spanish vocab - Inbox.md"

# with explicit prompt file and batch size 3
python scripts/clean_vocab.py \
  --inbox "/path/Spanish vocab - Inbox.md" \
  --prompt "prompts/vocabulary_prompt.txt" \
  --batch-size 3 \
  --show-items

Notes:
- This script reads your prompt file (default 'prompts/vocabulary_prompt.txt') and
  uses the LLM via vocabgen.llm_client.generate_text to convert inbox sections into
  structured vocabulary articles.
- It will write topic files named <Topic>.md to the same directory as the inbox file.
- It commits progress in chunks (batch-size) so that partial progress is preserved.
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import signal
from pathlib import Path
from typing import List, Optional, Dict, Any

from tqdm import tqdm

from vocabgen.vocab_processor import (
    split_sections,
    join_sections_for_batch,
    split_llm_response_into_articles,
    extract_topic_from_article,
    remove_topic_line,
)
from vocabgen.fileops import read_text, backup_file, atomic_write, append_to_file
from vocabgen import llm_client

logger = logging.getLogger("vocabgen.clean_vocab")


def load_prompt(prompt_path: Path) -> str:
    txt = read_text(prompt_path)
    return txt.strip()


def default_model_params_from_str(s: Optional[str]) -> Dict[str, Any]:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception as e:
        raise ValueError("model-params must be a JSON string") from e


def process_inbox_chunk(
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


def topic_filename_for_inbox(inbox_path: Path) -> Dict[str, Path]:
    """
    Map topic names to filenames in the inbox directory.
    By default, topic files are named "<base name> - <Topic>.md" if such files exist,
    otherwise fallback to "<Topic>.md".
    """
    inbox_dir = inbox_path.parent
    out: Dict[str, Path] = {}
    for t in [
        "Emotions",
        "Actions",
        "Nature",
        "Culture",
        "Food",
        "Health",
        "Appearance",
        "Technology",
        "Travel",
        "Slang",
        "Misc",
    ]:
        # prefer files that follow pattern like 'Spanish vocab - Food.md'
        pattern = f"* - {t}.md"
        found = list(inbox_dir.glob(pattern))
        if found:
            out[t] = found[0]
        else:
            out[t] = inbox_dir / f"{t}.md"
    return out


def run(
    inbox: Path,
    prompt_path: Path,
    provider: str,
    model: str,
    model_params: Dict[str, Any],
    batch_size: int,
    max_retries: int,
    rate_limit_per_minute: Optional[int],
    show_items: bool,
    dry_run: bool,
):
    # Load prompt and inbox
    system_prompt = load_prompt(prompt_path)
    text = read_text(inbox)
    sections = split_sections(text)
    total = len(sections)
    if total == 0:
        logger.info("No sections found in inbox: %s", inbox)
        return

    topic_map = topic_filename_for_inbox(inbox)
    # Backup inbox
    bak = backup_file(inbox)
    logger.info("Backup created: %s", bak)

    # We'll process sections in batches
    indices = list(range(0, total, batch_size))
    summary = {t: 0 for t in topic_map.keys()}
    new_items: List[str] = []
    remaining_sections = sections.copy()

    try:
        pbar = tqdm(total=total, desc="Processing sections")
        # We will iterate through batches; but since we will remove processed items from remaining_sections,
        # better to process via while loop
        i = 0
        while i < len(sections):
            # compute current batch: next batch_size unprocessed sections
            batch_sections = sections[i : i + batch_size]
            # Send to LLM
            try:
                articles = process_inbox_chunk(
                    provider=provider,
                    model=model,
                    system_prompt=system_prompt,
                    sections=batch_sections,
                    model_params=model_params,
                    max_retries=max_retries,
                    rate_limit_per_minute=rate_limit_per_minute,
                )
            except KeyboardInterrupt:
                # Let user terminate gracefully
                tqdm.write("Interrupted by user; stopping before committing this batch.")
                break
            except Exception as e:
                tqdm.write(f"LLM call failed for batch starting at section {i}: {e}")
                # skip this batch but don't delete original sections
                pbar.update(len(batch_sections))
                i += batch_size
                continue

            # Parse and distribute articles
            # For each article returned, attempt to find Topic, and append to corresponding file
            committed = []  # which input indices were committed
            for art in articles:
                topic = extract_topic_from_article(art)
                if topic is None:
                    # skip or treat as failed
                    tqdm.write("Failed to extract topic for article; logging and skipping.\n" + art[:200])
                    continue
                # remove Topic line from article content
                content = remove_topic_line(art)
                # ensure no leading separators
                content = content.strip() + "\n\n"
                # write to appropriate topic file (atomic append)
                target = topic_map.get(topic)
                if not target:
                    tqdm.write(f"No file mapping for topic {topic}; using Misc")
                    target = topic_map["Misc"]
                if dry_run:
                    tqdm.write(f"[dry-run] Would append to {target}: \n{content[:200]}")
                else:
                    append_to_file(target, content)
                summary[topic] = summary.get(topic, 0) + 1
                new_items.append(f"{topic}: {content.splitlines()[0][:80]}")
                committed.append(True)

            # If any article was committed, remove the corresponding input sections from the inbox.
            # We assume one-to-one mapping between input sections and produced articles is not strict,
            # so we will remove the input batch sections if at least one article successfully appended.
            if any(committed):
                # Remove first len(batch_sections) from sections list and update the inbox file atomically
                # Reconstruct remaining text
                remaining = "\n\n---\n\n".join(sections[i + batch_size :])
                if dry_run:
                    tqdm.write("[dry-run] Would update inbox by removing processed sections")
                else:
                    atomic_write(inbox, remaining)
                pbar.update(len(batch_sections))
            else:
                # If nothing committed (LLM failed to parse), skip removal but advance progress so we don't loop forever
                pbar.update(len(batch_sections))

            i += batch_size

    except KeyboardInterrupt:
        tqdm.write("Interrupted by user. Partial progress is saved (processed batches committed).")
    finally:
        pbar.close()

    # Summary
    tqdm.write("Processing complete. Summary:")
    for t, cnt in summary.items():
        if cnt:
            tqdm.write(f"  {t}: {cnt}")
    if show_items:
        tqdm.write("\nNew items produced:")
        for it in new_items:
            tqdm.write("  " + it)
