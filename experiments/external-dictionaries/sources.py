#!/usr/bin/env python3
"""Readers and mappers for the external-dictionary spike.

One reader per source *format family*, each yielding `Entry` records grouped by headword. Two
mappers per entry: `fields` (an ArticleDraft, the shape `web/src/yaml.ts` parses) and `html` (a
display fragment, the guaranteed fallback). Keeping both on the same entries is what makes the
size and fidelity columns comparable.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import tarfile
from collections import defaultdict
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Iterator

SRC = Path(__file__).resolve().parents[2] / "data" / "dictionaries" / "src"

# Acervo's closed part-of-speech enum (web/src/domain.ts). Anything outside it has no home.
ACERVO_POS = {"noun", "verb", "adj", "adv", "phrase", "idiom", "expression"}

# What a source POS becomes. Absent -> the entry has no representable POS.
POS_MAP = {
    "noun": "noun", "name": "noun", "proper noun": "noun", "propn": "noun",
    "verb": "verb", "adj": "adj", "adjective": "adj", "adv": "adv", "adverb": "adv",
    "phrase": "phrase", "prep_phrase": "phrase", "proverb": "phrase", "prepositional phrase": "phrase",
    "idiom": "idiom", "intj": "expression", "interjection": "expression",
}
# The lenient policy: everything else becomes "expression" and the loss is recorded.
LENIENT_POS = "expression"

REGISTER_TAGS = {
    "colloquial": "colloquial", "informal": "colloquial", "slang": "slang",
    "vulgar": "vulgar", "formal": "formal", "literary": "formal",
}


@dataclass
class Entry:
    """One headword, with every part-of-speech sub-entry the source holds for it."""
    key: str
    lemma: str
    fields: dict | None = None            # ArticleDraft, or None when nothing representable
    html: str = ""
    dropped: set[str] = field(default_factory=set)
    pos_unmapped: set[str] = field(default_factory=set)
    invented: set[str] = field(default_factory=set)


def _open(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "rt", encoding="utf-8")


# --------------------------------------------------------------------------- wiktextract (kaikki)

# Top-level keys wiktextract emits that Acervo's model has nowhere to put.
WIKTEXTRACT_DROP = {
    "etymology_text", "etymology_templates", "etymology_number", "head_templates", "hyphenation",
    "hyphenations", "forms", "categories", "topics", "wikipedia", "redirects", "descendants",
    "derived", "related", "synonyms", "antonyms", "hypernyms", "hyponyms", "holonyms", "meronyms",
    "coordinate_terms", "proverbs", "abbreviations", "translations", "inflection_templates",
    "info_templates", "instances", "troponyms", "form_of", "alt_of", "senseid", "wikidata",
}
SENSE_DROP = {
    "links", "categories", "id", "topics", "wikipedia", "derived", "related", "synonyms",
    "antonyms", "hypernyms", "hyponyms", "coordinate_terms", "form_of", "alt_of", "senseid",
    "wikidata", "qualifier", "raw_glosses", "instances", "info_templates", "head_nr",
}


def read_kaikki(path: Path, lang_code: str | None, limit: int | None) -> Iterator[list[dict]]:
    """Group raw wiktextract lines by headword, streaming.

    One JSONL line is one (word, pos) pair, so `gratis` arrives as separate adj and adv lines and a
    lookup wants all of them. The dumps are not sorted, but every occurrence of a word *is*
    contiguous (verified: 0 non-contiguous reappearances in a 119k-line sample), so grouping
    adjacent runs is exact and keeps memory flat over a 1 GB file.
    """
    group: list[dict] = []
    current: str | None = None
    produced = 0
    with _open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if lang_code and record.get("lang_code") != lang_code:
                continue
            word = record.get("word")
            if not word:
                continue
            if word != current:
                if group:
                    yield group
                    produced += 1
                    if limit and produced >= limit:
                        return
                group, current = [], word
            group.append(record)
    if group and not (limit and produced >= limit):
        yield group


def _ipa_of(record: dict) -> str | None:
    for sound in record.get("sounds") or []:
        raw = sound.get("ipa")
        if raw and raw.startswith("/"):
            return raw
    for sound in record.get("sounds") or []:
        if sound.get("ipa"):
            return sound["ipa"]
    return None


def kaikki_fields(group: list[dict], language: str, definition_lang: str, lenient: bool) -> Entry:
    """Map a headword group onto an ArticleDraft.

    `definition_lang` is the honest part: the English edition's `glosses` are English, so they are
    written as an English definition rather than pretending to be a Spanish one. Nothing is
    invented; a sense with no gloss text simply does not survive.
    """
    head = group[0]
    entry = Entry(key=head["word"], lemma=head["word"])
    for record in group:
        entry.dropped |= (set(record) & WIKTEXTRACT_DROP)

    pos_source = head.get("pos", "")
    pos = POS_MAP.get(pos_source)
    if pos is None:
        entry.pos_unmapped.add(pos_source)
        if not lenient:
            return entry
        pos = LENIENT_POS

    senses: list[dict] = []
    for record in group:
        for raw in record.get("senses") or []:
            entry.dropped |= (set(raw) & SENSE_DROP)
            glosses = raw.get("glosses") or []
            if not glosses:
                continue
            tags = [tag.lower() for tag in (raw.get("tags") or [])]
            sense: dict = {
                "order": len(senses),
                "definition": glosses[0],
                "definitionLang": definition_lang,
            }
            domain = None
            for tag in tags:
                if tag in REGISTER_TAGS:
                    continue
                if tag in {"transitive", "intransitive", "reflexive", "pronominal"}:
                    domain = domain or tag
            if domain:
                sense["domain"] = domain
            # An example the source carries, kept with the origin the model already has a value for.
            examples = []
            for sample in (raw.get("examples") or [])[:3]:
                text = sample.get("text")
                if not text:
                    continue
                item = {"text": text, "textLang": language, "origin": "wiktionary"}
                english = sample.get("english")
                if english:
                    item["translation"] = english
                    item["translationLang"] = "en"
                examples.append(item)
            if examples:
                sense["examples"] = examples
            senses.append(sense)

    if not senses:
        return entry

    draft: dict = {
        "language": language,
        "headword": head["word"],
        "lemma": head["word"],
        "pos": pos,
        "status": "inbox",
        "senses": senses,
    }
    ipa = _ipa_of(head)
    if ipa:
        draft["ipa"] = ipa
    register = next((REGISTER_TAGS[t] for record in group for raw in (record.get("senses") or [])
                     for t in [x.lower() for x in (raw.get("tags") or [])] if t in REGISTER_TAGS), None)
    if register:
        draft["register"] = register
    entry.fields = draft
    return entry


def kaikki_html(group: list[dict]) -> str:
    head = group[0]
    out = [f"<h1>{escape(head['word'])}</h1>"]
    ipa = _ipa_of(head)
    if ipa:
        out.append(f"<p class=ipa>{escape(ipa)}</p>")
    for record in group:
        out.append(f"<h2>{escape(record.get('pos', ''))}</h2><ol>")
        for raw in record.get("senses") or []:
            glosses = raw.get("glosses") or []
            if not glosses:
                continue
            tags = raw.get("tags") or []
            label = f"<em>{escape(', '.join(tags))}</em> " if tags else ""
            out.append(f"<li>{label}{escape(glosses[0])}")
            for sample in (raw.get("examples") or [])[:3]:
                if sample.get("text"):
                    out.append(f"<blockquote>{escape(sample['text'])}</blockquote>")
            out.append("</li>")
        out.append("</ol>")
    return "".join(out)


# ------------------------------------------------------------------------------------ CC-CEDICT

CEDICT_LINE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]*)\]\s+/(.*)/\s*$")


def read_cc_cedict(path: Path, limit: int | None) -> Iterator[tuple[str, str, str, list[str]]]:
    count = 0
    with _open(path) as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            match = CEDICT_LINE.match(line.strip())
            if not match:
                continue
            traditional, simplified, pinyin, body = match.groups()
            senses = [part for part in body.split("/") if part]
            yield traditional, simplified, pinyin, senses
            count += 1
            if limit and count >= limit:
                return


def cedict_fields(row: tuple[str, str, str, list[str]]) -> Entry:
    traditional, simplified, pinyin, senses = row
    entry = Entry(key=simplified, lemma=simplified)
    if traditional != simplified:
        entry.dropped.add("traditional")   # variant axis, no home on a single lexeme
    entry.fields = {
        "language": "zh-Hans",
        "headword": simplified,
        "lemma": simplified,
        "reading": pinyin,                  # Chinese lexemes require a reading (domain.ts)
        "pos": "noun",                      # CC-CEDICT carries no POS at all
        "status": "inbox",
        # One English text per sense: writing it as definition *and* gloss would store it twice.
        "senses": [{
            "order": index,
            "definition": text,
            "definitionLang": "en",
        } for index, text in enumerate(senses)],
    }
    entry.invented.add("pos")               # nothing in the source supports this
    return entry


def cedict_html(row: tuple[str, str, str, list[str]]) -> str:
    traditional, simplified, pinyin, senses = row
    variant = f" <span class=variant>{escape(traditional)}</span>" if traditional != simplified else ""
    items = "".join(f"<li>{escape(text)}</li>" for text in senses)
    return f"<h1>{escape(simplified)}</h1>{variant}<p class=reading>{escape(pinyin)}</p><ol>{items}</ol>"


# ------------------------------------------------------------------------ jmdict-simplified JSON

def read_jmdict(path: Path, limit: int | None) -> Iterator[dict]:
    with tarfile.open(path, "r:gz") as archive:
        member = next(m for m in archive.getmembers() if m.name.endswith(".json"))
        payload = json.load(archive.extractfile(member))
    for index, word in enumerate(payload.get("words", [])):
        if limit and index >= limit:
            return
        yield word


JMDICT_POS = {
    "n": "noun", "v1": "verb", "v5u": "verb", "v5k": "verb", "v5s": "verb", "v5t": "verb",
    "v5n": "verb", "v5b": "verb", "v5m": "verb", "v5r": "verb", "v5g": "verb", "vs": "verb",
    "vk": "verb", "vi": "verb", "vt": "verb", "adj-i": "adj", "adj-na": "adj", "adj-no": "adj",
    "adv": "adv", "exp": "expression", "int": "expression",
}


def jmdict_fields(word: dict, lenient: bool) -> Entry:
    kanji = [k["text"] for k in word.get("kanji", []) if k.get("text")]
    kana = [k["text"] for k in word.get("kana", []) if k.get("text")]
    headword = kanji[0] if kanji else (kana[0] if kana else "")
    entry = Entry(key=headword, lemma=headword)
    if not headword:
        return entry
    entry.dropped |= {"priority", "common", "appliesToKanji", "related", "antonym", "field",
                      "dialect", "languageSource"} & _jmdict_keys(word)

    senses = []
    pos_seen: list[str] = []
    for index, sense in enumerate(word.get("sense", [])):
        glosses = [g["text"] for g in sense.get("gloss", []) if g.get("text")]
        if not glosses:
            continue
        pos_seen.extend(sense.get("partOfSpeech", []))
        senses.append({
            "order": len(senses),
            "definition": glosses[0],
            "definitionLang": "en",
            "glosses": [{"lang": "en", "terms": glosses}],
        })
    if not senses:
        return entry

    pos = next((JMDICT_POS[p] for p in pos_seen if p in JMDICT_POS), None)
    if pos is None:
        entry.pos_unmapped |= set(pos_seen)
        if not lenient:
            return entry
        pos = LENIENT_POS

    draft = {
        "language": "ja",
        "headword": headword,
        "lemma": headword,
        "pos": pos,
        "status": "inbox",
        "senses": senses,
    }
    if kana and kanji:
        draft["reading"] = kana[0]
    entry.fields = draft
    return entry


def _jmdict_keys(word: dict) -> set[str]:
    keys = set(word)
    for sense in word.get("sense", []):
        keys |= set(sense)
    return keys


def jmdict_html(word: dict) -> str:
    kanji = [k["text"] for k in word.get("kanji", []) if k.get("text")]
    kana = [k["text"] for k in word.get("kana", []) if k.get("text")]
    headword = kanji[0] if kanji else (kana[0] if kana else "")
    reading = f"<p class=reading>{escape(kana[0])}</p>" if kana and kanji else ""
    items = []
    for sense in word.get("sense", []):
        glosses = [g["text"] for g in sense.get("gloss", []) if g.get("text")]
        if not glosses:
            continue
        tags = sense.get("partOfSpeech", [])
        label = f"<em>{escape(', '.join(tags))}</em> " if tags else ""
        items.append(f"<li>{label}{escape('; '.join(glosses))}</li>")
    return f"<h1>{escape(headword)}</h1>{reading}<ol>{''.join(items)}</ol>"


# ------------------------------------------------------------------------------- FreeDict TEI P5

TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def read_freedict_tei(path: Path, limit: int | None) -> Iterator[tuple[str, str, list[str]]]:
    """Stream <entry> elements out of the TEI source tarball."""
    import xml.etree.ElementTree as ET

    with tarfile.open(path, "r:xz") as archive:
        member = next(m for m in archive.getmembers() if m.name.endswith(".tei"))
        stream = archive.extractfile(member)
        count = 0
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag != f"{TEI_NS}entry":
                continue
            orth = element.find(f"{TEI_NS}form/{TEI_NS}orth")
            headword = (orth.text or "").strip() if orth is not None else ""
            pos_el = element.find(f"{TEI_NS}gramGrp/{TEI_NS}pos")
            pos = (pos_el.text or "").strip() if pos_el is not None else ""
            quotes = [(q.text or "").strip() for q in element.iter(f"{TEI_NS}quote") if (q.text or "").strip()]
            element.clear()
            if not headword or not quotes:
                continue
            yield headword, pos, quotes
            count += 1
            if limit and count >= limit:
                return


TEI_POS = {"n": "noun", "pn": "noun", "v": "verb", "adj": "adj", "adv": "adv",
           "int": "expression", "interjection": "expression",
           "phraseologicalUnit": "phrase", "proverb": "phrase", "idiom": "idiom"}


def tei_fields(row: tuple[str, str, list[str]], lenient: bool) -> Entry:
    headword, pos_source, quotes = row
    entry = Entry(key=headword, lemma=headword)
    pos = TEI_POS.get(pos_source)
    if pos is None:
        entry.pos_unmapped.add(pos_source or "(none)")
        if not lenient:
            return entry
        pos = LENIENT_POS
    entry.fields = {
        "language": "en",
        "headword": headword,
        "lemma": headword,
        "pos": pos,
        "status": "inbox",
        "senses": [{
            "order": index,
            "definition": text,
            "definitionLang": "ru",
        } for index, text in enumerate(quotes)],
    }
    return entry


def tei_html(row: tuple[str, str, list[str]]) -> str:
    headword, pos, quotes = row
    label = f"<h2>{escape(pos)}</h2>" if pos else ""
    items = "".join(f"<li>{escape(text)}</li>" for text in quotes)
    return f"<h1>{escape(headword)}</h1>{label}<ol>{items}</ol>"


# ------------------------------------------------------------------- StarDict, through PyGlossary

def read_stardict(path: Path, limit: int | None) -> Iterator[tuple[str, str]]:
    """Read the opaque binary tier. The payload arrives as markup; there is nothing to map."""
    import tempfile

    from pyglossary.glossary_v2 import Glossary

    Glossary.init()
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(path, "r:xz") as archive:
            archive.extractall(tmp, filter="data")
        ifo = next(Path(tmp).rglob("*.ifo"))
        glossary = Glossary()
        if not glossary.directRead(str(ifo)):
            raise RuntimeError(f"pyglossary could not read {ifo.name}")
        for index, item in enumerate(glossary):
            if limit and index >= limit:
                return
            words = item.l_word
            if not words:
                continue
            yield words[0], item.defi
