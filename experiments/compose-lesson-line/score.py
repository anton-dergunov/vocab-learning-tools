#!/usr/bin/env python3
"""Layer 1: what the reply actually contains. Pure measurement, no model call.

Scoring never spends anything, so correcting a metric and re-scoring a whole run is free — which is
why `run.py` stores the raw reply rather than a summary.

Two sources, deliberately. Everything about the *article* is read from the draft the shipped
`draft_from` builds, so the numbers describe what Acervo would actually have stored. The two new
fields are read from the **raw reply**, because `draft_from` silently ignores keys it does not know:
that is exactly what lets the enlarged prompt be measured before any schema exists for it.

`draft_from` is a measurement here, never allowed to abort a row. What the shipped path would refuse
is one of the things being compared between arms.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path
from typing import Any

import dataset

from acervo.errors import ApiError
from acervo.services.capture.draft import draft_from

HERE = Path(__file__).resolve().parent

OPTIONAL_LEXEME = ("ipa", "gender", "register", "dialect", "emoji")


def words_of(value: str) -> list[str]:
    return [part for part in re.split(r"\s+", (value or "").strip()) if part]


def has_emoji(value: str) -> bool:
    return any(unicodedata.category(ch) in ("So", "Sk") for ch in value or "")


def fold(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())


SCRIPT_FOR = {"ru": "cyrillic", "uk": "cyrillic", "zh": "han", "ja": "han", "el": "greek"}


def script_of(value: str) -> str:
    """The dominant script of a string, by majority of its letters.

    A proxy for "is this in the right language", not a language identifier — but it is the only part
    of the rule that can be checked mechanically, and it catches the failure the pilot found: an
    English `primaryGloss` for a word the vocabulary glosses into Russian first.
    """
    counts: dict[str, int] = {}
    for ch in value or "":
        if not ch.isalpha():
            continue
        code = ord(ch)
        if 0x0400 <= code <= 0x04FF:
            name = "cyrillic"
        elif 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            name = "han"
        elif 0x0370 <= code <= 0x03FF:
            name = "greek"
        elif code < 0x0250:
            name = "latin"
        else:
            name = "other"
        counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.get) if counts else "none"


def expected_script(language: str) -> str:
    return SCRIPT_FOR.get(language.split("-")[0].lower(), "latin")


def single_term(value: str) -> bool:
    """One term, not a list. A comma or a semicolon is the failure this is looking for."""
    return bool(value) and ";" not in value and "," not in value and "/" not in value


def measure(record: dict[str, Any], word: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "wordId": record["wordId"], "arm": record["arm"], "repeat": record["repeat"],
        "provider": record["provider"], "model": record["model"], "language": record["language"],
        "ok": bool(record.get("ok")), "parsedJson": bool(record.get("parsedJson")),
        "seconds": record.get("seconds"), "costUsd": record.get("costUsd"),
        "requestChars": record.get("requestChars"), "replyChars": record.get("replyChars"),
        "reason": record.get("reason"),
    }
    reply = record.get("reply")
    if not out["parsedJson"] or not isinstance(reply, dict):
        out["draftBuilt"] = False
        return out

    vocabulary = dataset.vocabulary_for(word)
    resolution = dataset.resolution_for(word)
    request = dataset.request_for(word)
    try:
        draft = draft_from(reply, resolution, request, vocabulary, dataset.topics(), record["model"])
        out["draftBuilt"] = True
    except ApiError as refusal:
        out |= {"draftBuilt": False, "refusal": refusal.code}
        return out

    senses = draft["senses"]
    examples = [example for sense in senses for example in sense["examples"]]
    gloss_langs = vocabulary["glossLangs"]
    present = {gloss["lang"] for sense in senses for gloss in sense["glosses"]}

    out |= {
        "senses": len(senses),
        "examples": len(examples),
        "examplesPerSense": round(len(examples) / len(senses), 3) if senses else 0.0,
        "noteCount": len(draft["notes"]),
        "noteChars": sum(len(note) for note in draft["notes"]),
        "definitionChars": round(statistics.mean([len(s["definition"]) for s in senses]), 1) if senses else 0,
        "glossComplete": all(lang in present for lang in gloss_langs),
        "termsPerGloss": round(statistics.mean(
            [len(g["terms"]) for s in senses for g in s["glosses"]] or [0]), 3),
        "optionalFields": sum(1 for field in OPTIONAL_LEXEME if draft.get(field)),
        "sensesWithDomain": sum(1 for s in senses if s.get("domain")),
        "examplesWithNote": sum(1 for e in examples if e.get("note")),
        "examplesWithEmotion": sum(1 for e in examples if e.get("emotion")),
        "matchedFormKept": sum(1 for e in examples if e.get("matchedForm")),
        "fromAttestation": sum(1 for e in examples if e["origin"] == "attestation"),
        "topicsChosen": len(draft["topics"]),
    }

    # The new fields, from the raw reply: the shipped parser drops keys it does not know.
    primary = (reply.get("primaryGloss") or "").strip() if isinstance(reply.get("primaryGloss"), str) else ""
    emotion = (reply.get("emotion") or "").strip() if isinstance(reply.get("emotion"), str) else ""
    short = (draft.get("shortGloss") or "").strip()
    first_terms = [fold(t) for t in (senses[0]["glosses"][0]["terms"] if senses and senses[0]["glosses"] else [])]
    example_emotions = {fold(e["emotion"]) for e in examples if e.get("emotion")}
    out |= {
        "primaryGloss": primary or None,
        "primaryPresent": bool(primary),
        "primarySingleTerm": single_term(primary),
        # Equality with `shortGloss` is only a failure when that line carries SEVERAL meanings: for a
        # word with one meaning the two SHOULD agree, and the pilot flagged `el miércoles` →
        # `Wednesday` as a fault when it was the right answer.
        "primaryEqualsShortGloss": bool(primary) and fold(primary) == fold(short),
        "shortGlossIsList": bool(re.search(r"[;,]", short)),
        "primaryCopiedList": bool(primary) and fold(primary) == fold(short) and bool(re.search(r"[;,]", short)),
        "primaryScript": script_of(primary) if primary else None,
        "primaryWrongScript": bool(primary) and script_of(primary) not in (
            expected_script(gloss_langs[0]), "none"),
        "primaryInFirstSenseTerms": bool(primary) and fold(primary) in first_terms,
        "primaryLengthRatio": round(len(primary) / len(word["headword"]), 2) if primary else None,
        "emotionText": emotion or None,
        "emotionPresent": bool(emotion),
        "emotionWords": len(words_of(emotion)),
        "emotionInRange": 3 <= len(words_of(emotion)) <= 12 if emotion else None,
        "emotionHasEmoji": has_emoji(emotion),
        "emotionEqualsExample": bool(emotion) and fold(emotion) in example_emotions,
        "emotionNull": reply.get("emotion", "__absent__") is None,
    }
    return out


def score_run(run_dir: Path) -> dict[str, Any]:
    by_id = {word["id"]: word for word in dataset.words()}
    rows = []
    for path in sorted(run_dir.rglob("*.json")):
        if path.name in ("manifest.json", "summary.json", "judged.json", "ratings.json"):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if "wordId" not in record:
            continue
        rows.append(measure(record, by_id[record["wordId"]]))
    summary = {"rows": rows, "paired": paired(rows), "noise": noise(rows)}
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


NUMERIC = ("senses", "examples", "examplesPerSense", "noteCount", "noteChars",
           "definitionChars", "termsPerGloss", "optionalFields", "seconds", "replyChars")


def _index(rows: list[dict[str, Any]]) -> dict[tuple, dict[str, Any]]:
    return {(r["arm"], r["provider"], r["model"], r["wordId"], r["repeat"]): r for r in rows}


def paired(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """After minus before, on the same word, repeat and pair. Only where both built a draft."""
    index = _index(rows)
    deltas: dict[str, list[float]] = {name: [] for name in NUMERIC}
    for key, row in index.items():
        if key[0] != "after" or not row.get("draftBuilt"):
            continue
        other = index.get(("before",) + key[1:])
        if not other or not other.get("draftBuilt"):
            continue
        for name in NUMERIC:
            if isinstance(row.get(name), (int, float)) and isinstance(other.get(name), (int, float)):
                deltas[name].append(row[name] - other[name])
    return {name: {
        "n": len(values),
        "mean": round(statistics.mean(values), 3) if values else None,
        "median": round(statistics.median(values), 3) if values else None,
    } for name, values in deltas.items()}


def noise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The same arm, two different repeats: how much this metric moves for no reason at all.

    This is the yardstick. A between-arm difference no larger than it is not an effect, and without
    it a delta of 0.1 senses is unreadable.
    """
    index = _index(rows)
    spread: dict[str, list[float]] = {name: [] for name in NUMERIC}
    for key, row in index.items():
        arm, provider, model, word, repeat = key
        if not row.get("draftBuilt"):
            continue
        other = index.get((arm, provider, model, word, repeat + 1))
        if not other or not other.get("draftBuilt"):
            continue
        for name in NUMERIC:
            if isinstance(row.get(name), (int, float)) and isinstance(other.get(name), (int, float)):
                spread[name].append(abs(row[name] - other[name]))
    return {name: {
        "n": len(values),
        "meanAbsolute": round(statistics.mean(values), 3) if values else None,
    } for name, values in spread.items()}


def selftest() -> int:
    """Check the metric against the failures it exists to catch, before anything is spent."""
    word = dataset.words(["asco"])[0]
    base = {
        "wordId": "asco", "arm": "after", "repeat": 0, "provider": "p", "model": "m",
        "language": "es", "ok": True, "parsedJson": True,
    }
    reply = {
        "headword": "el asco", "lemma": "asco", "pos": "noun", "shortGloss": "disgust; revulsion",
        "primaryGloss": "disgust", "emotion": "repulsed, recoiling slightly",
        "notes": ["Stronger than the English."],
        "senses": [{"definition": "Sensación de repugnancia.",
                    "glosses": [{"lang": "en", "terms": ["disgust", "revulsion"]}],
                    "examples": [{"text": "¡Qué asco!", "translation": "How disgusting!",
                                  "emotion": "recoiling, nose wrinkled"}]}],
    }
    good = measure({**base, "reply": reply}, word)
    assert good["draftBuilt"] and good["senses"] == 1 and good["examples"] == 1, good
    assert good["primaryPresent"] and good["primarySingleTerm"], good
    assert not good["primaryEqualsShortGloss"] and good["primaryInFirstSenseTerms"], good
    assert good["emotionInRange"] and not good["emotionEqualsExample"], good

    # The two failures the experiment was built to detect.
    conflated = measure({**base, "reply": {**reply, "primaryGloss": "disgust; revulsion"}}, word)
    assert conflated["primaryEqualsShortGloss"] and not conflated["primarySingleTerm"], conflated
    duplicated = measure({**base, "reply": {**reply, "emotion": "recoiling, nose wrinkled"}}, word)
    assert duplicated["emotionEqualsExample"], duplicated

    # Equality with a single-meaning shortGloss is correct, and must not be counted as copying.
    single = measure({**base, "reply": {**reply, "shortGloss": "disgust", "primaryGloss": "disgust"}}, word)
    assert single["primaryEqualsShortGloss"] and not single["primaryCopiedList"], single

    # An English term where the vocabulary glosses into Russian first is the pilot's real finding.
    chinese = dataset.words(["mafan"])[0]
    wrong = measure({**base, "wordId": "mafan", "language": "zh-Hans", "reply": {
        **reply, "primaryGloss": "troublesome", "reading": "máfan",
        "senses": [{"definition": "Troublesome.",
                    "glosses": [{"lang": "ru", "terms": ["хлопотный"]},
                                {"lang": "en", "terms": ["troublesome"]}],
                    "examples": []}]}}, chinese)
    assert wrong["primaryWrongScript"], wrong
    right = measure({**base, "wordId": "mafan", "language": "zh-Hans", "reply": {
        **reply, "primaryGloss": "хлопотный", "reading": "máfan",
        "senses": [{"definition": "Troublesome.",
                    "glosses": [{"lang": "ru", "terms": ["хлопотный"]},
                                {"lang": "en", "terms": ["troublesome"]}],
                    "examples": []}]}}, chinese)
    assert not right["primaryWrongScript"], right

    # A reply with no senses is what the shipped path refuses, and that is a datum, not a crash.
    empty = measure({**base, "reply": {**reply, "senses": []}}, word)
    assert empty["draftBuilt"] is False and empty["refusal"] == "llm_unusable", empty

    # And an unparseable reply never reaches draft_from at all.
    broken = measure({**base, "parsedJson": False, "reply": "not json"}, word)
    assert broken["draftBuilt"] is False, broken

    print("selftest ok: conflation, duplication, wrong script, single-meaning equality,\n              the no-senses refusal and an unparseable reply are all detected")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", nargs="?", help="a run directory")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not args.run:
        parser.error("a run directory, or --selftest")
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = HERE / run_dir if (HERE / run_dir).exists() else Path.cwd() / run_dir
    summary = score_run(run_dir)
    print(f"{len(summary['rows'])} call(s) scored into {run_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
