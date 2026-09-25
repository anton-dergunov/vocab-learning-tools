#!/usr/bin/env python3
"""Fold eleven old exports, and two laptop image runs, into one importable bundle.

**A throwaway, deliberately outside the pipeline.** It
exists because of one accident of history: `~/__acervo_data` holds eleven exports taken while the
data model was still moving, across schema versions 5 to 10. They overlap heavily, the old ones lack
fields the current schema carries, and the ~2,286 sense pictures drawn in early September live
outside them in `output/images` and `output/images-en`.

Three subcommands, three stages, each reading the previous one and never editing it — so a bad run
is a directory you delete rather than work you have lost:

    dedupe    every word once, under a stable slug, conflicts held back for a person
    backfill  the fields the current schema wants, one model call per few words
    images    the pictures attached, and the zip the Transfer panel reads

The contract the output must satisfy is `web/src/transfer.ts` and `web/src/yaml.ts`, and the three
things easiest to get wrong are written down where they are done:

- the zip has **no wrapper directory** (`TransferPanel.filesIn` sorts pictures by a `media/` prefix);
- the manifest says **schemaVersion 12**, because `READABLE` is `{12, 9, 8, 7, 6}` and a bundle
  stamped 10 or 11 is refused outright;
- **unknown keys are a hard parse error**, so `approved:` and `audioRef:` must be gone — declaring
  12 means `upgradeBundle` will not strip them for us.

Delete this file, and `scripts/check_bundle_yaml.mts`, once the import has landed. Neither has a
second use.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import random
import re
import shutil
import string
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

BUNDLE_FORMAT = "acervo-export/1"
SCHEMA_VERSION = 12
"""`web/src/api.ts:9`. Not the version the sources were written under — the version we now emit."""

MANIFEST_FILE = "acervo.yaml"
VOCABULARIES_FILE = "vocabularies.yaml"
TOPICS_FILE = "topics.yaml"
RESERVED = (MANIFEST_FILE, VOCABULARIES_FILE, TOPICS_FILE)
NOT_A_LANGUAGE = {"markdown", "media", "audio", "__pycache__"}

# `web/src/yaml.ts:549-569`, verbatim. Unknown keys are refused rather than ignored, so every stage
# checks its own output against these before writing.
EXAMPLE_KEYS = [
    "id", "text", "textLang", "translation", "translationLang", "origin", "sourceAttestationId",
    "modelId", "videoRef", "videoTitle", "videoChannel", "videoStart", "videoEnd", "clipRef",
    "imageRef", "emotion", "note", "matchedForm", "matchedTranslationForm",
]
PROMPT_KEYS = [
    "id", "exampleId", "prompt", "styleId", "seed", "modelId", "promptVersion", "imageRef",
    "imageModelId",
]
SENSE_KEYS = [
    "id", "order", "definition", "definitionLang", "domain", "emoji", "glosses", "examples",
    "imagePrompts",
]
ATTESTATION_KEYS = ["id", "text", "translation", "sourceKind", "sourceTitle", "sourceUrl", "capturedAt"]
ARTICLE_KEYS = [
    "id", "language", "headword", "lemma", "reading", "ipa", "pos", "gender", "register", "dialect",
    "emoji", "status", "topics", "shortGloss", "primaryGloss", "emotion", "notes", "senses",
    "attestations", "imagePrompts",
]

# Write order, from `yamlForDraft` and the three `*Fields` helpers. It differs from the key lists
# above in two places (`status` before `topics`; example `emotion` last), so it is written out
# rather than derived.
ARTICLE_ORDER = ARTICLE_KEYS
SENSE_ORDER = ["id", "order", "definition", "definitionLang", "domain", "emoji", "glosses",
               "examples", "imagePrompts"]
EXAMPLE_ORDER = [
    "id", "text", "textLang", "translation", "translationLang", "origin", "sourceAttestationId",
    "modelId", "videoRef", "videoTitle", "videoChannel", "videoStart", "videoEnd", "clipRef",
    "imageRef", "note", "matchedForm", "matchedTranslationForm", "emotion",
]
ATTESTATION_ORDER = ["id", "text", "translation", "sourceKind", "sourceTitle", "sourceUrl", "capturedAt"]
PROMPT_ORDER = ["id", "exampleId", "prompt", "styleId", "seed", "modelId", "promptVersion",
                "imageRef", "imageModelId"]

OBSOLETE = ("approved", "audioRef")
"""What `upgradeBundle` strips for a bundle stamped 6-9. We stamp 12, so we strip them ourselves."""

ID_FIELDS = ("id", "sourceAttestationId", "exampleId")
ID_SHAPE = re.compile(r"^[a-z0-9]{15}$")
ALPHABET = string.ascii_lowercase + string.digits

LANGUAGE_NAMES = {
    "es": "Spanish", "en": "English", "ru": "Russian", "zh-Hans": "Chinese (Simplified)",
}


def mint() -> str:
    """A client-minted id: 15 lowercase alphanumerics, the shape the parser demands."""
    return "".join(random.choices(ALPHABET, k=15))


# ── reading ──────────────────────────────────────────────────────────────────────────────────────

# `web/src/yaml.ts:203`. A term that is not plain under this is double-quoted on the way out — and
# five real files are unreadable by every Python YAML parser because an older writer did not.
PLAIN_IN_FLOW = re.compile(r"^[^\W_](?:[^\W_]|[ ().'’/–-])*$", re.UNICODE)
FLOW_GLOSS = re.compile(r"^(?P<lead>\s*-\s*\{lang:\s*)(?P<lang>[^,}]+),\s*terms:\s*\[(?P<terms>.*)\]\}\s*$")


def plain_in_flow(text: str) -> bool:
    return bool(PLAIN_IN_FLOW.match(text)) and not text.endswith(" ")


def split_flow(inner: str) -> list[str]:
    """`a, "b, c", d` → `['a', 'b, c', 'd']`. Commas inside double quotes are not separators."""
    terms: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for character in inner:
        if escaped:
            current.append(character)
            escaped = False
        elif quoted and character == "\\":
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif character == "," and not quoted:
            terms.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    tail = "".join(current).strip()
    if tail or terms:
        terms.append(tail)
    return [term for term in terms if term]


def repair_flow(text: str) -> str:
    """Re-quote gloss terms so PyYAML can open the file.

    `terms: [who is calling?]` round-tripped perfectly through Acervo's own reader and could not be
    opened by any Python tool at all — five of the real word files are in that state. Quoting is the
    rule AGENTS.md already states; this applies it on the way in so the rest of the script can use
    an ordinary parser.
    """
    out = []
    for line in text.splitlines():
        match = FLOW_GLOSS.match(line)
        if match:
            terms = split_flow(match.group("terms"))
            rendered = ", ".join(term if plain_in_flow(term) else quoted(term) for term in terms)
            line = f'{match.group("lead")}{match.group("lang")}, terms: [{rendered}]}}'
        out.append(line)
    return "\n".join(out)


class Loader(yaml.SafeLoader):
    """YAML 1.1 reads `no`, `on` and `~` as booleans and nulls. No field here is either.

    `fiel` glosses as `true` and `catorce` as `14`, and both are the English words. Left to the
    default resolvers the first comes back as `True` — whose `str()` is not what the file said —
    and the second as an integer. Numbers stay resolved because `order`, `seed` and the two video
    offsets really are numbers; `NUMERIC` below says which those are, and every other scalar is
    read as the text it is.
    """


Loader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers
            if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:null")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

NUMERIC = {"order", "seed", "videoStart", "videoEnd"}


def read_document(path: Path) -> dict[str, Any]:
    document = yaml.load(repair_flow(path.read_text(encoding="utf-8")), Loader=Loader)
    if not isinstance(document, dict):
        raise ValueError(f"{path} is not a mapping")
    return clean(document)


def clean(document: dict[str, Any]) -> dict[str, Any]:
    """Drop the obsolete keys and anything the parser would now refuse, everywhere."""
    def value_of(key: str, value: Any) -> Any:
        if key in NUMERIC or isinstance(value, (dict, list)):
            return value
        return str(value)

    def strip(fields: dict[str, Any], allowed: Sequence[str]) -> dict[str, Any]:
        return {key: value_of(key, value) for key, value in fields.items()
                if key in allowed and value is not None and value != []}

    article = strip(document, ARTICLE_KEYS)
    for name in ("topics", "notes"):
        if name in article:
            article[name] = [str(one) for one in article[name]]
    senses = []
    for sense in document.get("senses") or []:
        kept = strip(sense, SENSE_KEYS)
        kept["glosses"] = [
            {"lang": str(gloss.get("lang", "")),
             "terms": [str(term) for term in gloss.get("terms") or []]}
            for gloss in sense.get("glosses") or []
        ]
        kept["examples"] = [strip(example, EXAMPLE_KEYS) for example in sense.get("examples") or []]
        kept["imagePrompts"] = [strip(prompt, PROMPT_KEYS) for prompt in sense.get("imagePrompts") or []]
        senses.append({key: value for key, value in kept.items() if value != []})
    article["senses"] = senses
    if document.get("attestations"):
        article["attestations"] = [strip(one, ATTESTATION_KEYS) for one in document["attestations"]]
    if document.get("imagePrompts"):
        article["imagePrompts"] = [strip(one, PROMPT_KEYS) for one in document["imagePrompts"]]
    return article


def unknown_keys(document: dict[str, Any]) -> list[str]:
    """What `parseArticle` would refuse. Every stage runs this over its own output."""
    faults = []
    def check(fields: dict[str, Any], allowed: Sequence[str], path: str) -> None:
        faults.extend(f"{path}.{key}" for key in fields if key not in allowed)
    check(document, ARTICLE_KEYS, "document")
    for index, sense in enumerate(document.get("senses") or []):
        check(sense, SENSE_KEYS, f"senses[{index}]")
        for position, example in enumerate(sense.get("examples") or []):
            check(example, EXAMPLE_KEYS, f"senses[{index}].examples[{position}]")
        for position, prompt in enumerate(sense.get("imagePrompts") or []):
            check(prompt, PROMPT_KEYS, f"senses[{index}].imagePrompts[{position}]")
    for index, one in enumerate(document.get("attestations") or []):
        check(one, ATTESTATION_KEYS, f"attestations[{index}]")
    for index, one in enumerate(document.get("imagePrompts") or []):
        check(one, PROMPT_KEYS, f"imagePrompts[{index}]")
    return faults


# ── writing ──────────────────────────────────────────────────────────────────────────────────────

YAML_SPECIALS = set("-?:,[]{}#&*!|>'\"%@`")
NOT_PLAIN = {"true", "false", "yes", "no", "on", "off", "null", "~", "y", "n"}
NUMBERISH = re.compile(r"^[-+]?(\d[\d_]*(\.\d*)?|\.\d+)([eE][-+]?\d+)?$")


def quoted(value: str) -> str:
    body = value.replace("\\", "\\\\").replace('"', '\\"')
    body = "".join(character if character >= " " else f"\\x{ord(character):02x}" for character in body)
    return f'"{body}"'


def scalar(value: Any) -> str:
    """A value as YAML. Over-quoting costs two characters; under-quoting costs a readable file."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if (
        text
        and text.strip() == text
        and text[0] not in YAML_SPECIALS
        and text.lower() not in NOT_PLAIN
        and not NUMBERISH.match(text)
        and ": " not in text
        and " #" not in text
        and not text.endswith(":")
        and not any(character < " " for character in text)
    ):
        return text
    return quoted(text)


def flow_terms(terms: Sequence[Any]) -> str:
    rendered = []
    for term in terms:
        text = str(term)
        # A term that reads back as a number or a boolean must be quoted, or the file no longer
        # says what it said: `14` is the English word, not the integer.
        plain = plain_in_flow(text) and text.lower() not in NOT_PLAIN and not NUMBERISH.match(text)
        rendered.append(text if plain else quoted(text))
    return ", ".join(rendered)


def block(fields: dict[str, Any], order: Sequence[str], indent: str, lines: list[str]) -> None:
    """One mapping as `- key: value` lines, first key on the dash line the caller already wrote."""
    first = True
    for key in order:
        if key not in fields:
            continue
        prefix = "" if first else indent
        first = False
        lines.append(f"{prefix}{key}: {scalar(fields[key])}")


def write_document(document: dict[str, Any]) -> str:
    language = document.get("language", "")
    head = [
        f'# {document.get("headword", "")} — {LANGUAGE_NAMES.get(language, language)}',
        "# No ids here: everything in this document is created when you save.",
        "",
    ]
    lines: list[str] = []
    for key in ARTICLE_ORDER:
        if key not in document:
            continue
        value = document[key]
        if key == "topics":
            lines.append(f"topics: [{flow_terms(value)}]")
        elif key == "notes":
            lines.append("notes:")
            lines.extend(f"  - {scalar(note)}" for note in value)
        elif key == "senses":
            lines.append("senses:")
            for sense in value:
                entry: list[str] = []
                block({k: v for k, v in sense.items()
                       if k not in ("glosses", "examples", "imagePrompts")},
                      SENSE_ORDER, "    ", entry)
                if sense.get("glosses"):
                    entry.append("    glosses:")
                    for gloss in sense["glosses"]:
                        terms = flow_terms(gloss.get("terms") or [])
                        entry.append(f'      - {{lang: {gloss["lang"]}, terms: [{terms}]}}')
                if sense.get("examples"):
                    entry.append("    examples:")
                    for example in sense["examples"]:
                        inner: list[str] = []
                        block(example, EXAMPLE_ORDER, "        ", inner)
                        entry.append(f"      - {inner[0]}")
                        entry.extend(inner[1:])
                if sense.get("imagePrompts"):
                    entry.append("    imagePrompts:")
                    for prompt in sense["imagePrompts"]:
                        inner = []
                        block(prompt, PROMPT_ORDER, "        ", inner)
                        entry.append(f"      - {inner[0]}")
                        entry.extend(inner[1:])
                lines.append(f"  - {entry[0]}")
                lines.extend(entry[1:])
        elif key in ("attestations", "imagePrompts"):
            order = ATTESTATION_ORDER if key == "attestations" else PROMPT_ORDER
            lines.append(f"{key}:")
            for one in value:
                inner = []
                # An instant must survive as the string the validator expects, never as a date.
                one = dict(one)
                if "capturedAt" in one:
                    one["capturedAt"] = Quoted(one["capturedAt"])
                block(one, order, "    ", inner)
                lines.append(f"  - {inner[0]}")
                lines.extend(inner[1:])
        else:
            lines.append(f"{key}: {scalar(value)}")
    return "\n".join(head + lines) + "\n"


class Quoted(str):
    """A string that must be emitted double-quoted whatever it looks like."""


_plain_scalar = scalar


def scalar(value: Any) -> str:  # noqa: F811 — the Quoted case, layered over the plain rule
    if isinstance(value, Quoted):
        return quoted(str(value))
    return _plain_scalar(value)


def save_document(path: Path, document: dict[str, Any]) -> None:
    """Write it, then read it back and insist it says the same thing.

    The emitter is hand-rolled because this environment has no round-tripping YAML library, so it is
    verified per file rather than trusted. A quoting bug that silently changes a definition is the
    one failure that would survive every later check.
    """
    faults = unknown_keys(document)
    if faults:
        raise ValueError(f"{path}: keys the parser would refuse: {', '.join(faults)}")
    text = write_document(document)
    back = yaml.safe_load(text)
    if clean(back) != strip_quoted(document):
        raise ValueError(f"{path}: did not survive its own round trip")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def strip_quoted(value: Any) -> Any:
    if isinstance(value, Quoted):
        return str(value)
    if isinstance(value, dict):
        return {key: strip_quoted(item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_quoted(item) for item in value]
    return value


# ── identity ─────────────────────────────────────────────────────────────────────────────────────

CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def latinise(value: str) -> str:
    """`web/src/transfer.ts:81`, character for character."""
    folded = unicodedata.normalize("NFD", value)
    folded = "".join(one for one in folded if not unicodedata.combining(one)).lower()
    folded = "".join(CYRILLIC.get(one, one) for one in folded)
    folded = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:60]
    return folded.rstrip("-")


def slug_for(document: dict[str, Any]) -> str:
    return (latinise(document.get("lemma") or "")
            or latinise(document.get("headword") or "")
            or latinise(document.get("reading") or "")
            or "word")


def identity(document: dict[str, Any]) -> tuple[str, str]:
    """What import keys on: `(language, trimmed lowercased headword)`. Never the filename."""
    return document["language"], str(document["headword"]).strip().lower()


def fingerprint(document: dict[str, Any]) -> str:
    """The document with every minted id replaced by its position, so a re-mint is not a change.

    375 of the 388 byte-level conflicts across these exports are nothing but re-minted attestation
    ids — import re-mints them by design, so two exports of one unchanged word never match on bytes.
    """
    seen: dict[str, str] = {}

    def rename(value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {name: rename(item, name) for name, item in sorted(value.items())}
        if isinstance(value, list):
            return [rename(item) for item in value]
        if key in ID_FIELDS and isinstance(value, str) and ID_SHAPE.match(value):
            return seen.setdefault(value, f"ID{len(seen)}")
        return value

    # Two passes: the first assigns placeholders in document order, the second (sorted) serialises.
    def walk(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for name, item in value.items():
                walk(item, name)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif key in ID_FIELDS and isinstance(value, str) and ID_SHAPE.match(value):
            seen.setdefault(value, f"ID{len(seen)}")

    walk(document)
    return json.dumps(rename(document), sort_keys=True, ensure_ascii=False)


# ── stage 1: dedupe ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Variant:
    export: str
    path: Path
    document: dict[str, Any]
    text: str


def exports_in(source: Path, skip: Sequence[str]) -> list[Path]:
    found = sorted(one for one in source.iterdir()
                   if one.is_dir() and one.name.startswith("acervo-all-") and one.name not in skip)
    return found


def word_files(export: Path) -> Iterable[tuple[str, Path]]:
    for language in sorted(export.iterdir()):
        if not language.is_dir() or language.name in NOT_A_LANGUAGE or language.name.startswith("."):
            continue
        for path in sorted(language.glob("*.yaml")):
            yield language.name, path


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [one for one in (loaded or []) if isinstance(one, dict)]


def dedupe(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    out = Path(args.out).expanduser()
    conflicts_dir = Path(args.conflicts).expanduser()

    exports = exports_in(source, args.skip)
    print(f"reading {len(exports)} exports from {source}")
    for one in args.skip:
        print(f"  skipping {one} (asked for, or unreadable by import)")

    groups: dict[tuple[str, str], list[Variant]] = {}
    unreadable: list[str] = []
    for export in exports:
        for _, path in word_files(export):
            try:
                document = read_document(path)
                text = path.read_text(encoding="utf-8")
            except Exception as error:  # noqa: BLE001 — reported, never guessed at
                unreadable.append(f"{export.name}/{path.parent.name}/{path.name}: {error}")
                continue
            groups.setdefault(identity(document), []).append(
                Variant(export.name, path, document, text))

    # Slugs are recomputed from the chosen document, never inherited: one export files *asustado*
    # under `asustar.yaml`, so a filename is not an identity. Deterministic order, so a re-run of
    # this script produces the same names.
    chosen: list[tuple[tuple[str, str], Variant]] = []
    held: list[tuple[tuple[str, str], list[Variant]]] = []
    for key in sorted(groups):
        variants = groups[key]
        distinct = {fingerprint(one.document) for one in variants}
        if len(distinct) == 1:
            chosen.append((key, variants[-1]))  # newest export carrying it
        else:
            held.append((key, variants))

    taken: dict[str, int] = {}
    names: dict[tuple[str, str], str] = {}
    for key, variant in sorted(chosen, key=lambda pair: (pair[0][0], slug_for(pair[1].document), pair[0][1])):
        base = slug_for(variant.document)
        seen = taken.get(f"{key[0]}/{base}", 0)
        taken[f"{key[0]}/{base}"] = seen + 1
        names[key] = base if seen == 0 else f"{base}-{seen + 1}"

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    refused: list[str] = []
    used_topics: set[str] = set()
    languages: set[str] = set()
    for key, variant in chosen:
        document = variant.document
        try:
            save_document(out / key[0] / f"{names[key]}.yaml", document)
        except Exception as error:  # noqa: BLE001
            refused.append(f"{key[0]}/{names[key]}.yaml: {error}")
            continue
        used_topics.update(document.get("topics") or [])
        languages.add(key[0])

    # Topics and vocabularies: union across exports, the newest record for a name or a language
    # winning, so `es` and `en` keep the `notesLang` only the later exports carry.
    topics: dict[str, dict[str, Any]] = {}
    vocabularies: dict[str, dict[str, Any]] = {}
    for export in exports:
        for record in read_records(export / TOPICS_FILE):
            if record.get("name"):
                topics[record["name"]] = record
        for record in read_records(export / VOCABULARIES_FILE):
            if record.get("language"):
                vocabularies[record["language"]] = record

    missing_topics = sorted(used_topics - set(topics))
    ordered_topics = sorted(topics.values(), key=lambda one: (one.get("order", 0), one.get("name", "")))
    write_records(out / TOPICS_FILE, ordered_topics, ["name", "icon", "order"])
    ordered_vocabularies = sorted(
        (one for one in vocabularies.values() if one["language"] in languages),
        key=lambda one: (one.get("order", 0), one["language"]))
    write_records(out / VOCABULARIES_FILE, ordered_vocabularies,
                  ["language", "definitionLang", "glossLangs", "notesLang", "displayName", "flag", "order"])
    write_manifest(out, sorted(languages), len(ordered_vocabularies), len(ordered_topics), len(chosen))

    if conflicts_dir.exists():
        shutil.rmtree(conflicts_dir)
    if held:
        conflicts_dir.mkdir(parents=True)
        notes = ["# Words that changed between exports", "",
                 "One directory per word, one file per export that carries it. Pick a variant, drop it",
                 f"into `{out}/<lang>/<slug>.yaml` under the slug named below, and re-run `backfill`.", ""]
        for key, variants in held:
            language, headword = key
            base = slug_for(variants[-1].document)
            folder = conflicts_dir / language / base
            folder.mkdir(parents=True, exist_ok=True)
            for variant in variants:
                (folder / f"{variant.export.removeprefix('acervo-all-')}.yaml").write_text(
                    variant.text, encoding="utf-8")
            notes.append(f"## {language} · {headword} → `{language}/{base}.yaml`")
            notes.append("")
            oldest, newest = variants[0], variants[-1]
            if oldest.export != newest.export:
                diff = difflib.unified_diff(
                    oldest.text.splitlines(), newest.text.splitlines(),
                    fromfile=oldest.export, tofile=newest.export, lineterm="", n=1)
                notes.append("```diff")
                notes.extend(list(diff)[:80])
                notes.append("```")
            notes.append("")
        (conflicts_dir / "README.md").write_text("\n".join(notes) + "\n", encoding="utf-8")

    print(f"\n{len(chosen)} words written to {out}")
    print(f"{len(held)} words held back in {conflicts_dir} for you to resolve")
    for key, variants in held:
        print(f"    {key[0]} {key[1]} — {len(variants)} variants, "
              f"{len({fingerprint(one.document) for one in variants})} distinct")
    print(f"{len(ordered_topics)} topics, {len(ordered_vocabularies)} vocabularies")
    if missing_topics:
        print(f"!! topics named by a word but not defined: {', '.join(missing_topics)}")
    for fault in unreadable + refused:
        print(f"!! {fault}")
    return 1 if refused or missing_topics else 0


def write_records(path: Path, records: Sequence[dict[str, Any]], order: Sequence[str]) -> None:
    if not records:
        path.write_text("[]\n", encoding="utf-8")
        return
    lines: list[str] = []
    for record in records:
        rendered = []
        for key in order:
            if key not in record or record[key] is None:
                continue
            value = record[key]
            if isinstance(value, list):
                rendered.append(f"{key}: [{flow_terms([str(one) for one in value])}]")
            else:
                rendered.append(f"{key}: {scalar(value)}")
        lines.append(f"- {rendered[0]}")
        lines.extend(f"  {one}" for one in rendered[1:])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(out: Path, languages: Sequence[str], vocabularies: int, topics: int,
                   lexemes: int) -> None:
    stamped = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"
    (out / MANIFEST_FILE).write_text(
        f"format: {BUNDLE_FORMAT}\n"
        f"schemaVersion: {SCHEMA_VERSION}\n"
        f'exportedAt: "{stamped}"\n'
        f"languages: [{', '.join(languages)}]\n"
        "counts:\n"
        f"  vocabularies: {vocabularies}\n"
        f"  topics: {topics}\n"
        f"  lexemes: {lexemes}\n",
        encoding="utf-8")


def copy_frame(source: Path, out: Path) -> None:
    """The three top-level files, carried across a stage unchanged."""
    out.mkdir(parents=True, exist_ok=True)
    for name in RESERVED:
        if (source / name).exists():
            shutil.copy2(source / name, out / name)


# ── stage 2: backfill ────────────────────────────────────────────────────────────────────────────

EMOTION_LIMIT = 300
"""`services/capture/draft.py`. A direction is a short phrase, not an essay."""

BACKFILL_PROMPT = """\
You are completing vocabulary entries for a language-learning app. Each entry below already has its
definitions, glosses and examples — they are correct and you must not restate or change them. Some
fields were added to the format after these entries were written, and your only job is to supply
those missing fields.

For every word you are given, return an object with the same `i`. Inside it, return only the fields
that word's `missing` list names. Same for each sense (`j`) and each example (`k`): return only what
its own `missing` list names, and omit a sense or example that needs nothing.

What each field is:

- `primaryGloss` — the ONE term a spoken drill says for this word, written in {gloss_lang}. Normally
  the first term of the first sense's glosses. One term only: never a list, never containing a comma
  or a semicolon. `house`, not `house, home`.
- `emotion` (on the word) — how the word ITSELF sounds when spoken, as a short English direction of
  about three to twelve words. This is for a word with a strong inherent colour; the default is the
  opposite of an example's, so return null for most words. Only a word that genuinely carries a
  feeling of its own gets one.
- `emoji` (on a sense) — a single emoji depicting THIS sense. When a word has several senses their
  emoji must differ from each other, because that is what tells them apart in a list.
- `domain` (on a sense) — a one-word label for the field this meaning belongs to, written in
  {gloss_lang}: `cooking`, `law`, `music`, `anatomy`. Only when the sense really is domain-specific;
  return null for an everyday meaning.
- `emotion` (on an example) — how THIS sentence should be read aloud, as a short English direction
  of about three to twelve words naming the feeling and why: `proud and a little smug, showing it
  off`. Read the sentence and its translation and say what the speaker sounds like.

Return one JSON object and nothing else. No prose, no code fences:

{{"words": [{{"i": 0, "primaryGloss": "robbery", "emotion": null,
   "senses": [{{"j": 0, "emoji": "\U0001f4b0", "domain": "crime",
     "examples": [{{"k": 0, "emotion": "tense and urgent, reporting bad news"}}]}}]}}]}}

The entries:
"""


def wanted(document: dict[str, Any]) -> dict[str, Any]:
    """What this word is missing, as the request the model answers — indices are the only join."""
    missing: list[str] = []
    if not document.get("primaryGloss"):
        missing.append("primaryGloss")
    if not document.get("emotion"):
        missing.append("emotion")
    senses = []
    for index, sense in enumerate(document.get("senses") or []):
        sense_missing = [name for name in ("emoji", "domain") if not sense.get(name)]
        examples = []
        for position, example in enumerate(sense.get("examples") or []):
            if not example.get("emotion"):
                examples.append({
                    "k": position,
                    "text": example.get("text"),
                    "translation": example.get("translation"),
                    "missing": ["emotion"],
                })
        if not sense_missing and not examples:
            continue
        senses.append({
            "j": index,
            "definition": sense.get("definition"),
            "glosses": [term for gloss in sense.get("glosses") or [] for term in gloss.get("terms") or []],
            "missing": sense_missing,
            "examples": examples,
        })
    if not missing and not senses:
        return {}
    return {
        "headword": document.get("headword"),
        "pos": document.get("pos"),
        "shortGloss": document.get("shortGloss"),
        "missing": missing,
        "senses": senses,
    }


def one_term(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or ";" in text or "," in text:
        return None
    return text


def one_emoji(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:32] if text else None


def direction(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or text.lower() in ("null", "none"):
        return None
    return text[:EMOTION_LIMIT]


def apply_reply(document: dict[str, Any], request: dict[str, Any], answer: dict[str, Any],
                counts: dict[str, int]) -> None:
    """Merge one word's answer. Only fields that were asked for, only values that pass their rule."""
    def take(fields: dict[str, Any], name: str, value: Any, wanted_here: Sequence[str],
             label: str | None = None) -> None:
        if name not in wanted_here:
            return
        outcome = f"{label or name}: {'left empty' if value is None else 'filled'}"
        counts[outcome] = counts.get(outcome, 0) + 1
        if value is not None:
            fields[name] = value

    take(document, "primaryGloss", one_term(answer.get("primaryGloss")), request["missing"])
    take(document, "emotion", direction(answer.get("emotion")), request["missing"], "word emotion")

    asked = {sense["j"]: sense for sense in request["senses"]}
    for reply in answer.get("senses") or []:
        index = reply.get("j")
        if index not in asked:
            counts["sense: index not asked for"] = counts.get("sense: index not asked for", 0) + 1
            continue
        sense = document["senses"][index]
        take(sense, "emoji", one_emoji(reply.get("emoji")), asked[index]["missing"])
        take(sense, "domain", one_term(reply.get("domain")), asked[index]["missing"])
        positions = {example["k"] for example in asked[index]["examples"]}
        for example_reply in reply.get("examples") or []:
            position = example_reply.get("k")
            if position not in positions:
                counts["example: index not asked for"] = counts.get("example: index not asked for", 0) + 1
                continue
            take(sense["examples"][position], "emotion",
                 direction(example_reply.get("emotion")), ["emotion"], "example emotion")


def gloss_language(vocabularies: Sequence[dict[str, Any]], language: str) -> str:
    for record in vocabularies:
        if record.get("language") == language:
            langs = record.get("glossLangs") or []
            if langs:
                return LANGUAGE_NAMES.get(langs[0], langs[0])
    return "English"


def backfill(args: argparse.Namespace) -> int:
    from acervo.models import ChainExhausted, TextResult, call, chain, load_catalogue
    from acervo.models.errors import ProviderUnavailable

    source = Path(args.source).expanduser()
    out = Path(args.out).expanduser()
    catalogue = load_catalogue()
    chosen = parse_chain(args.chain)

    copy_frame(source, out)
    vocabularies = read_records(source / VOCABULARIES_FILE)
    progress_path = out / ".progress.json"
    progress: dict[str, Any] = json.loads(progress_path.read_text()) if progress_path.exists() else {}

    pending: list[tuple[str, str, Path, dict[str, Any], dict[str, Any]]] = []
    for language_dir in sorted(source.iterdir()):
        if not language_dir.is_dir() or language_dir.name in NOT_A_LANGUAGE:
            continue
        for path in sorted(language_dir.glob("*.yaml")):
            key = f"{language_dir.name}/{path.stem}"
            document = read_document(path)
            if key in progress and not args.redo:
                continue
            request = wanted(document)
            if not request:
                save_document(out / language_dir.name / path.name, document)
                progress[key] = {"filled": [], "note": "nothing missing"}
                continue
            pending.append((key, language_dir.name, path, document, request))

    already = len(progress)
    if args.limit:
        pending = pending[: args.limit]
    # Batched within one language, never across: the prompt names the gloss language once, and a
    # batch straddling en and es would ask for half its answers in the wrong one.
    batches: list[list[tuple[str, str, Path, dict[str, Any], dict[str, Any]]]] = []
    for language in sorted({one[1] for one in pending}):
        same = [one for one in pending if one[1] == language]
        batches.extend(same[at: at + args.batch] for at in range(0, len(same), args.batch))
    print(f"{already} words already done · {len(pending)} to fill in {len(batches)} calls "
          f"(batch {args.batch})")
    if args.dry_run:
        for key, _, _, _, request in pending[:5]:
            print(f"\n--- {key}\n{json.dumps(request, ensure_ascii=False, indent=2)}")
        print(f"\n(dry run — {len(batches)} calls not made)")
        return 0

    counts: dict[str, int] = {}
    failed: list[str] = []
    calls = 0

    def ask_batch(items: Sequence[tuple[str, str, Path, dict[str, Any], dict[str, Any]]]) -> bool:
        nonlocal calls
        language = items[0][1]
        payload = [dict(request, i=index) for index, (_, _, _, _, request) in enumerate(items)]
        prompt = (BACKFILL_PROMPT.format(gloss_lang=gloss_language(vocabularies, language))
                  + json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        expected = set(range(len(items)))

        def ask(candidate: chain.Candidate) -> TextResult:
            answered = call.text(prompt, row=candidate.row, model=candidate.model, as_json=True,
                                 timeout=call.SHORT_TIMEOUT_SECONDS)
            # Judged inside the callback, as `clips/select.py` judges its own, so a model that
            # cannot hold the shape is passed over instead of having its answer accepted.
            words = (answered.parsed or {}).get("words") if isinstance(answered.parsed, dict) else None
            if not isinstance(words, list) or {one.get("i") for one in words if isinstance(one, dict)} != expected:
                raise ProviderUnavailable(
                    "unusable", f"reply did not cover the indices asked for (wanted {sorted(expected)})",
                    provider_id=candidate.row.id, model=candidate.model)
            return answered

        try:
            result: TextResult = chain.walk("text", chosen, catalogue, ask, chain.stamped,
                                            caller="backfill")
        except ChainExhausted as exhausted:
            print(f"  !! {exhausted}")
            return False
        calls += 1
        replies = {one["i"]: one for one in result.parsed["words"] if isinstance(one, dict)}
        for index, (key, language_name, path, document, request) in enumerate(items):
            before = dict(counts)
            apply_reply(document, request, replies[index], counts)
            save_document(out / language_name / path.name, document)
            progress[key] = {"filled": sorted(
                name.split(":")[0] for name in counts if counts[name] != before.get(name))}
        return True

    for number, items in enumerate(batches, 1):
        print(f"[{number}/{len(batches)}] {', '.join(one[0] for one in items)}", flush=True)
        if ask_batch(items):
            progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=1))
            continue
        # A batch the chain could not answer is split, so one bad word does not cost four good ones.
        if len(items) == 1:
            failed.append(items[0][0])
            continue
        for one in items:
            if not ask_batch([one]):
                failed.append(one[0])
        progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=1))

    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=1))
    print(f"\n{calls} calls · {len(progress)} words done in total")
    for name in sorted(counts):
        print(f"  {counts[name]:6d}  {name}")
    for one in failed:
        print(f"!! not filled: {one}")
    remaining = sum(1 for language_dir in source.iterdir() if language_dir.is_dir()
                    and language_dir.name not in NOT_A_LANGUAGE
                    for path in language_dir.glob("*.yaml")
                    if f"{language_dir.name}/{path.stem}" not in progress)
    if remaining:
        print(f"\n{remaining} words still to do — run the same command again "
              "(tomorrow, if the free allowance ran out)")
    return 0


def parse_chain(value: str | None) -> list[Any] | None:
    """`gemini-free,cloudflare` or `gemini-free:gemini/gemini-3.5-flash`. None means the default."""
    if not value:
        return None
    chosen: list[Any] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        chosen.append(tuple(part.split(":", 1)) if ":" in part else part)
    return chosen


# ── stage 3: images ──────────────────────────────────────────────────────────────────────────────

def images(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    out = Path(args.out).expanduser()

    if out.exists():
        shutil.rmtree(out)
    copy_frame(source, out)

    words: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    for language_dir in sorted(source.iterdir()):
        if not language_dir.is_dir() or language_dir.name in NOT_A_LANGUAGE:
            continue
        for path in sorted(language_dir.glob("*.yaml")):
            document = read_document(path)
            words[identity(document)] = (Path(language_dir.name) / path.name, document)

    records: list[tuple[Path, dict[str, Any]]] = []
    for run in args.runs:
        directory = Path(run).expanduser()
        for path in sorted((directory / "records").glob("*.json")):
            records.append((directory, json.loads(path.read_text(encoding="utf-8"))))
    print(f"{len(words)} words · {len(records)} image records from {len(args.runs)} runs")

    placed = 0
    skipped: list[str] = []
    touched: set[tuple[str, str]] = set()
    for directory, record in records:
        run = record.get("run") or {}
        subject = f'{run.get("language")} {run.get("headword")!r} sense {run.get("senseOrder")}'
        if record.get("failureReason"):
            skipped.append(f"{subject}: {record['failureReason']}")
            continue
        bytes_path = directory / "images" / f"{record['id']}.webp"
        if not bytes_path.exists():
            skipped.append(f"{subject}: no image file at {bytes_path}")
            continue
        key = (run.get("language"), str(run.get("headword", "")).strip().lower())
        if key not in words:
            skipped.append(f"{subject}: no word holds that headword")
            continue
        relative, document = words[key]
        senses = document.get("senses") or []
        order = run.get("senseOrder")
        # `senseOrder` indexes the sense list only while `order` is contiguous 0..n-1, which it is in
        # every document these exports contain. Asserted rather than assumed: a wrong match puts
        # somebody else's picture on your word, which is worse than a missing picture.
        if [sense.get("order", index) for index, sense in enumerate(senses)] != list(range(len(senses))):
            skipped.append(f"{subject}: sense order is not 0..n-1, refusing to place by position")
            continue
        if not isinstance(order, int) or not 0 <= order < len(senses):
            skipped.append(f"{subject}: sense {order} is beyond the word's {len(senses)} senses")
            continue
        sense = senses[order]

        prompt: dict[str, Any] = {
            "prompt": record.get("prompt"),
            "styleId": record.get("styleId"),
            "seed": record.get("seed"),
            "modelId": record.get("modelId"),
            "promptVersion": record.get("promptVersion"),
            # Read from the word file and sent as `X-Acervo-Drawn-By`. Omit it and the restored
            # picture is written `suppressed`, and nothing will ever redraw it.
            "imageModelId": record.get("imageModelId"),
        }
        anchor = (run.get("anchorExample") or {}).get("text")
        for example in sense.get("examples") or []:
            if example.get("text") != anchor:
                continue
            # An example carrying a `clipRef` has its id nulled on import, so a reference to it would
            # resolve to nothing. Better no anchor than a dangling one.
            if example.get("clipRef"):
                break
            example.setdefault("id", mint())
            prompt["exampleId"] = example["id"]
            break
        # An image brief with a prompt must name its style and prompt version, or the record
        # validator refuses the save. No `imageRef`: the bytes arrive separately and supply it.
        if prompt["prompt"] and not (prompt["styleId"] and prompt["promptVersion"]):
            skipped.append(f"{subject}: brief names no style or prompt version")
            continue
        if not isinstance(prompt["seed"], int) or not 0 <= prompt["seed"] <= 2147483647:
            prompt.pop("seed")
        sense["imagePrompts"] = [{key: value for key, value in prompt.items() if value is not None}]

        target = out / "media" / relative.parent.name / f"{relative.stem}-{order + 1}.webp"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bytes_path, target)
        placed += 1
        touched.add(key)

    for key, (relative, document) in sorted(words.items()):
        save_document(out / relative, document)

    without = len(words) - len(touched)
    print(f"\n{placed} pictures placed on {len(touched)} words · {without} words left with none")
    for one in skipped:
        print(f"!! {one}")

    if args.zip:
        write_zips(out, Path(args.zip).expanduser(), args.chunk_mb)
    return 0


def carried(out: Path, relative: Path) -> list[Path]:
    """One word: its file, and every picture named after it.

    The suffix must be digits: `valla-*.webp` also catches `valla-publicitaria-1.webp`, which put
    one picture in two chunks and, where both words landed in one, wrote the same entry twice.
    """
    files = [out / relative]
    media = out / "media" / relative.parent.name
    if media.is_dir():
        mine = re.compile(rf"^{re.escape(relative.stem)}-\d+\.webp$")
        files.extend(sorted(one for one in media.glob(f"{relative.stem}-*.webp")
                            if mine.match(one.name)))
    return files


def write_zips(out: Path, archive: Path, chunk_mb: int) -> None:
    """One zip, or several — each a complete bundle the panel can read on its own.

    Half a gigabyte of pictures is a lot to hand a browser: `TransferPanel.filesIn` calls
    `unzipSync` and holds every entry in memory at once, and a tablet is where this vocabulary is
    actually read. So a word and its pictures travel together, and each chunk carries the manifest,
    the topics and the vocabularies — import is by `(language, headword)` and skips what is already
    held, so the chunks may be imported in any order, and a repeat costs nothing.
    """
    words = sorted(
        Path(language.name) / path.name
        for language in out.iterdir()
        if language.is_dir() and language.name not in NOT_A_LANGUAGE
        for path in language.glob("*.yaml"))

    groups: list[list[Path]] = [[]]
    budget = chunk_mb * 1_000_000
    running = 0
    for relative in words:
        size = sum(one.stat().st_size for one in carried(out, relative))
        if budget and running and running + size > budget:
            groups.append([])
            running = 0
        groups[-1].append(relative)
        running += size

    for number, group in enumerate(groups, 1):
        target = archive if len(groups) == 1 else archive.with_name(
            f"{archive.stem}-{number:02d}{archive.suffix}")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            # No wrapper directory: `TransferPanel.filesIn` sorts pictures with a `media/` prefix,
            # and a wrapper makes every one of them land in the word-file pile and be dropped.
            for name in RESERVED:
                if (out / name).exists():
                    bundle.write(out / name, name)
            for relative in group:
                for path in carried(out, relative):
                    if path.stat().st_size:
                        bundle.write(path, path.relative_to(out).as_posix())
        print(f"{target.name} — {len(group)} words, "
              f"{len(zipfile.ZipFile(target).namelist())} entries, "
              f"{target.stat().st_size / 1e6:.0f} MB")
    if len(groups) > 1:
        print(f"\nImport them in any order: a word already held is skipped, so a repeat is free.")


# ── entry ────────────────────────────────────────────────────────────────────────────────────────

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    one = commands.add_parser("dedupe", help="every word once, conflicts held back")
    one.add_argument("--source", default="~/__acervo_data")
    one.add_argument("--out", default="~/__acervo_data/__dedup")
    one.add_argument("--conflicts", default="~/__acervo_data/__conflicts")
    one.add_argument("--skip", nargs="*", default=["acervo-all-2026-09-01"],
                     help="exports to ignore (the schema-5 one is unreadable by import)")
    one.set_defaults(run=dedupe)

    two = commands.add_parser("backfill", help="fill the fields the current schema wants")
    two.add_argument("--source", default="~/__acervo_data/__dedup")
    two.add_argument("--out", default="~/__acervo_data/__filled")
    two.add_argument("--chain", default=None, help="e.g. gemini-free,cloudflare")
    two.add_argument("--batch", type=int, default=5, help="words per model call")
    two.add_argument("--limit", type=int, default=0, help="words this run, for a daily allowance")
    two.add_argument("--redo", action="store_true", help="ignore what is already done")
    two.add_argument("--dry-run", action="store_true", help="print the first requests, call nothing")
    two.set_defaults(run=backfill)

    three = commands.add_parser("images", help="attach the laptop image runs and write the zip")
    three.add_argument("--source", default="~/__acervo_data/__filled")
    three.add_argument("--out", default="~/__acervo_data/__bundle")
    three.add_argument("--runs", nargs="+", default=["output/images", "output/images-en"])
    three.add_argument("--zip", default="~/__acervo_data/acervo-import.zip")
    three.add_argument("--chunk-mb", type=int, default=100,
                       help="split into zips of about this size; 0 for one file")
    three.set_defaults(run=images)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
