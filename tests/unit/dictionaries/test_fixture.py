"""The artifact `web/src/dictionary.test.ts` reads.

The format is written in Python and read in TypeScript, so the only check that means anything is one
where the bytes cross the language boundary. This builds a small artifact from a fixed word list and
asserts it still matches the committed one; the vitest suite opens those same bytes with the real
reader.

It is committed as one base64 JSON file rather than as `.dict` and `.idx`: `web/` has no Node type
definitions, and adding them so that a test could call `readFileSync` would be a dependency bought
to solve a problem that `resolveJsonModule` already solves.

If this fails after a deliberate format change, regenerate with:

    ACERVO_UPDATE_FIXTURES=1 .venv/bin/python -m pytest tests/unit/dictionaries/test_fixture.py

and re-run the web tests, which is exactly the moment both halves should be looked at together.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from vocabgen.dictionaries.container import SourceEntry, build_artifact
from vocabgen.dictionaries.model import Entry, Example, Sense

FIXTURE = (Path(__file__).resolve().parents[3] / "web" / "src" / "testFixtures"
           / "sampleDictionary.json")
DICTIONARY_ID = "sample"

# Enough entries to cross several restart buckets and more than one frame, which is where the bugs
# in a front-coded index live. `frameSize` and `restartInterval` are shrunk for the same reason:
# the production values would need a hundred thousand words to exercise the same code.
FRAME_SIZE = 8
RESTART_INTERVAL = 4


def sample_entries() -> list[SourceEntry]:
    words = [f"palabra{index:03d}" for index in range(40)]
    entries = [
        SourceEntry(key=word, payload=Entry(
            headword=word, language="es", definitionLang="en",
            senses=[Sense(definition=f"the meaning of {word}")],
        ).payload())
        for word in words
    ]
    # The awkward cases, each of which broke something at least once while this was being written.
    entries.append(SourceEntry("picar", Entry(
        headword="picar", lemma="picar", language="es", definitionLang="es", ipa="/piˈkaɾ/",
        pos="verb", posLabel="verb",
        senses=[Sense(definition="Golpear algo con una punta.",
                      examples=[Example(text="Picó la cebolla.", textLang="es")]),
                Sense(definition="Cortar en pedazos muy pequeños.")],
    ).payload()))
    # An accented headword, found through the folded alias the compiler adds.
    entries.append(SourceEntry("Ñandú", Entry(
        headword="Ñandú", language="es", definitionLang="en",
        senses=[Sense(definition="a flightless bird")],
    ).payload()))
    # A part of speech Acervo's enum has no room for: the source's own word is kept, `pos` is absent.
    entries.append(SourceEntry("sobre", Entry(
        headword="sobre", language="es", definitionLang="en", posLabel="preposition",
        senses=[Sense(definition="on, upon")],
    ).payload()))
    # One headword, two articles, plus the traditional spelling as an alias.
    for reading, gloss in (("hang2", "row; line"), ("xing2", "to walk; to go")):
        entries.append(SourceEntry("行", Entry(
            headword="行", language="zh-Hans", definitionLang="en", reading=reading,
            senses=[Sense(definition=gloss)],
        ).payload(), aliases=("行",)))
    # Above the BMP, where UTF-16 order and UTF-8 order disagree.
    entries.append(SourceEntry("\U0001F600", Entry(
        headword="\U0001F600", language="en", definitionLang="en",
        senses=[Sense(definition="a grinning face")],
    ).payload()))
    return entries


def build_into(destination: Path):
    return build_artifact(
        iter(sample_entries()), destination=destination, dictionary_id=DICTIONARY_ID, tier="fields",
        metadata={"id": DICTIONARY_ID, "name": "Sample dictionary", "sourceLang": "es",
                  "targetLang": "en", "licence": "CC BY-SA 4.0",
                  "attribution": "Acervo test fixture.", "sourceDate": "2026-01-01",
                  "builtAt": "2026-01-01T00:00:00Z"},
        frame_size=FRAME_SIZE, restart_interval=RESTART_INTERVAL,
    )


def encoded(tmp_path: Path) -> dict:
    def base64_of(suffix: str) -> str:
        return base64.b64encode((tmp_path / f"{DICTIONARY_ID}{suffix}").read_bytes()).decode("ascii")

    return {
        "id": DICTIONARY_ID,
        "note": "Built by tests/unit/dictionaries/test_fixture.py. Do not edit by hand.",
        "metadata": json.loads((tmp_path / f"{DICTIONARY_ID}.json").read_text()),
        "dict": base64_of(".dict"),
        "idx": base64_of(".idx"),
    }


def test_the_web_reader_fixture_is_current(tmp_path):
    report = build_into(tmp_path)
    assert report.frame_count > 1, "the fixture must span more than one frame to be worth reading"
    assert report.entry_count > 40

    current = encoded(tmp_path)
    if os.environ.get("ACERVO_UPDATE_FIXTURES"):
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pytest.skip("fixture regenerated; run the web tests too")

    assert FIXTURE.is_file(), f"{FIXTURE} is missing; regenerate with ACERVO_UPDATE_FIXTURES=1"
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert committed["dict"] == current["dict"] and committed["idx"] == current["idx"], (
        "the committed fixture no longer matches what the compiler writes. If the format changed on "
        "purpose, regenerate with ACERVO_UPDATE_FIXTURES=1 and update web/src/dictionary.test.ts."
    )
    assert committed["metadata"]["frameSize"] == FRAME_SIZE
    assert committed["metadata"]["restartInterval"] == RESTART_INTERVAL
