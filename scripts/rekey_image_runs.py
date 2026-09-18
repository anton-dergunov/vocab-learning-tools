#!/usr/bin/env python3
"""Re-key a laptop image run onto the senses this account holds now.

**A throwaway, deliberately outside the pipeline.** It exists because of one accident of history:
the ~2,285 pictures under `output/images*` were drawn against sense ids from a database that has
since been rebuilt. `transfer.ts` mints fresh ids on import — a bundle carries no sense ids at all —
so every `senseId` in those run directories names a sense nobody holds, and because an image prompt
id is *derived from* its sense id, every filename and every `imageRef` is wrong too.

`verify` cannot see this: a run directory is internally consistent either way. `publish` can, and
refuses the whole run rather than writing half of it. So the ids have to be re-derived first, from
something that survived the round trip — the language, the headword, and the sense's order within
the word, all three of which the run records already carry in their `run` block.

Two rules, and both are about not losing 500 MB of unrepeatable work:

- **It writes a new run directory and never edits the old one.** A bad match is then a directory you
  delete, not a picture you have lost.
- **It refuses to guess.** A word it cannot find, or a word whose sense count has changed, is
  reported and skipped. A wrong match puts somebody else's picture on your word, which is worse than
  a missing picture and much harder to notice.

Once it has run, the ordinary path takes over:

    scripts/generate_images.py verify  --output output/images-rekeyed
    scripts/generate_images.py publish --output output/images-rekeyed --media <media dir> \\
        --server-url https://acervo.example.com --owner-email learner@account.example.com

Delete this file once the backlog has landed. It has no second use.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from acervo.client import AcervoClient, AcervoError  # noqa: E402
from acervo.images.ids import image_prompt_id, image_reference  # noqa: E402


@dataclass
class Rekeyed:
    matched: int = 0
    skipped: int = 0
    problems: list[str] = field(default_factory=list)

    def fault(self, subject: str, why: str) -> None:
        self.skipped += 1
        self.problems.append(f"{subject}: {why}")


def _live(records: list[dict]) -> list[dict]:
    return [record for record in records if not record.get("deleted")]


def _index(changes: dict[str, list[dict]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Words by (language, lowercased headword), each with its senses in order.

    Lowercased because the store holds `Picar` about as often as `picar`, and a case difference is
    not a different word. A headword held twice in one language is dropped from the index rather
    than resolved: there is no way to tell which of them a picture was drawn for.
    """
    words = _live(changes.get("lexemes", []))
    senses = _live(changes.get("senses", []))
    examples = _live(changes.get("examples", []))

    by_lexeme: dict[str, list[dict]] = defaultdict(list)
    for sense in senses:
        by_lexeme[sense["lexemeId"]].append(sense)
    for group in by_lexeme.values():
        group.sort(key=lambda sense: (sense.get("order", 0), sense.get("id", "")))

    by_sense: dict[str, list[dict]] = defaultdict(list)
    for example in examples:
        by_sense[example["senseId"]].append(example)

    found: dict[tuple[str, str], dict[str, Any] | None] = {}
    for word in words:
        key = (word.get("language", ""), (word.get("headword") or "").strip().lower())
        if key in found:
            found[key] = None       # ambiguous: two words under one headword
            continue
        found[key] = {
            "lexemeId": word["id"],
            "senses": by_lexeme.get(word["id"], []),
            "examples": by_sense,
        }
    return {key: value for key, value in found.items() if value is not None}


def _anchor(examples: list[dict], wanted: dict | None) -> str | None:
    """The example the brief was written from, matched on its text.

    Exact text, not a similarity: an example's wording is content and survives the round trip
    unchanged, so anything looser would be guessing about the one field that decides where the
    picture is shown.
    """
    if not wanted or not wanted.get("text"):
        return None
    text = str(wanted["text"]).strip()
    for example in examples:
        if (example.get("text") or "").strip() == text:
            return example["id"]
    return None


def rekey(source: Path, destination: Path, changes: dict[str, list[dict]], *,
          language: str | None = None, report=print) -> Rekeyed:
    words = _index(changes)
    result = Rekeyed()
    (destination / "records").mkdir(parents=True, exist_ok=True)
    (destination / "images").mkdir(parents=True, exist_ok=True)

    for path in sorted((source / "records").glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result.fault(path.name, "the record could not be read")
            continue

        run = record.get("run") or {}
        headword = (run.get("headword") or "").strip()
        found = words.get((run.get("language", ""), headword.lower()))
        if language and run.get("language") != language:
            continue
        if found is None:
            result.fault(headword or path.stem, "no word with that headword in this account")
            continue

        order = run.get("senseOrder")
        senses = found["senses"]
        if not isinstance(order, int) or order >= len(senses):
            # A word whose senses were re-numbered or re-written since. Positional matching is the
            # only key that survived, so when it does not resolve there is nothing else to try.
            result.fault(headword, f"sense {order} of {len(senses)} no longer exists")
            continue
        sense = senses[order]

        # The definition is not the key — it is the check on the key. A picture landing on the
        # wrong sense of the right word is the failure this is here to catch.
        stored = (sense.get("definition") or "").strip()
        drawn_for = (run.get("definition") or "").strip()
        if stored and drawn_for and stored != drawn_for:
            result.fault(headword, f"sense {order} now reads differently ({stored[:40]!r})")
            continue

        picture = source / "images" / f"{record['id']}.webp"
        if record.get("imageRef") and not (picture.is_file() and picture.stat().st_size):
            result.fault(headword, "the record claims a picture that is not on disk")
            continue

        prompt_id = image_prompt_id(sense["id"])
        # Recomputed from the bytes being copied rather than rewritten from the old string: a source
        # run drawn before references carried a digest has none to carry over, and this mints the
        # correct one from the file it is about to copy.
        data = picture.read_bytes() if record.get("imageRef") else None
        reference = image_reference(found["lexemeId"], prompt_id, data) if data is not None else None
        rewritten = {
            **record,
            "id": prompt_id,
            "lexemeId": found["lexemeId"],
            "senseId": sense["id"],
            "exampleId": _anchor(found["examples"].get(sense["id"], []), run.get("anchorExample")),
            "imageRef": reference,
            # A refusal by the image provider is a finished outcome, and `publish` turns `blocked`
            # into a suppressed row. Kept as it was rather than reset: it is still true.
            "run": {**run, "rekeyedFrom": record["id"]},
        }
        (destination / "records" / f"{prompt_id}.json").write_text(
            json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if reference:
            shutil.copy2(picture, destination / "images" / f"{prompt_id}.webp")
        result.matched += 1

    # Writer refusals carry no picture and no sense of their own to re-key onto, and `publish`
    # ignores the directory entirely, so they are deliberately left behind.
    report(f"Re-keyed {result.matched} record(s); {result.skipped} skipped.")
    for problem in result.problems[:40]:
        report(f"  · {problem}")
    if len(result.problems) > 40:
        report(f"  … and {len(result.problems) - 40} more")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="A run directory as drawn.")
    parser.add_argument("--output", type=Path, required=True, help="Where the re-keyed run goes.")
    parser.add_argument("--server-url", default=os.environ.get("ACERVO_SERVER_URL", ""), required=False)
    parser.add_argument("--owner-email", default=os.environ.get("ACERVO_OWNER_EMAIL", ""), required=False)
    parser.add_argument("--language", default="", help="Only records drawn for this language.")
    args = parser.parse_args(argv)

    if not args.server_url or not args.owner_email:
        parser.error("--server-url and --owner-email are required")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error(f"{args.output} is not empty; re-keying never writes into an existing run")

    password = os.environ.get("ACERVO_PASSWORD") or getpass.getpass("Acervo password: ")
    client = AcervoClient(args.server_url)
    try:
        client.sign_in(args.owner_email, password)
        changes = client.pull_graph()["changes"]
    except AcervoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    result = rekey(args.source, args.output, changes, language=args.language or None)
    if not result.matched:
        print("Nothing matched, so nothing was written.", file=sys.stderr)
        return 1
    print(
        f"\nNext: scripts/generate_images.py verify --output {args.output}\n"
        f"      scripts/generate_images.py publish --output {args.output} --media <media dir> "
        f"--server-url {args.server_url} --owner-email {args.owner_email}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
