#!/usr/bin/env python3
"""What the reply actually contains. Pure measurement, no model call.

Adapted from `experiments/compose-lesson-line/score.py`, which already tracked `primarySingleTerm`
and `primaryLengthRatio` for these same two fields but never thresholded them — this experiment adds
the checks that were missing: whether `primaryGloss`'s word count is proportional to a multi-word
headword's, and `emotion` coverage broken out by whether the word is expected to carry a feeling at
all (`words.yaml`'s `category`), so a coverage gain can't be claimed if it came from the null-control
set now failing.

Scoring never spends anything, so correcting a metric and re-scoring a whole run is free — which is
why `run.py` stores the raw reply rather than a summary.
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
ARTICLES_ES = {"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"}
# `category` values in words.yaml that expect a real feeling versus expect `null`. Anything else
# (e.g. a plain regression word with no strong opinion either way) is left out of the stratified
# coverage table, so it can't dilute either side.
EXPECT_FEELING = {"primary_multiword", "primary_singleword", "emotion_random"}
EXPECT_NULL = {"emotion_null_control"}


def words_of(value: str) -> list[str]:
    return [part for part in re.split(r"\s+", (value or "").strip()) if part]


def has_emoji(value: str) -> bool:
    return any(unicodedata.category(ch) in ("So", "Sk") for ch in value or "")


def fold(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())


SCRIPT_FOR = {"ru": "cyrillic", "uk": "cyrillic", "zh": "han", "ja": "han", "el": "greek"}


def script_of(value: str) -> str:
    """The dominant script of a string, by majority of its letters. A proxy, not an identifier."""
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
    """One term, not a list. A comma, semicolon or slash is the failure this is looking for."""
    return bool(value) and ";" not in value and "," not in value and "/" not in value


def content_words(headword: str, language: str) -> list[str]:
    """`headword`'s words, minus a leading Spanish article — `el disfraz` is 1 content word, not 2.

    Chinese carries no whitespace-separated words at all, so this only means anything for a
    space-separated language; callers must not use it as a Chinese word count.
    """
    parts = words_of(headword)
    if language == "es" and parts and parts[0].casefold() in ARTICLES_ES:
        return parts[1:]
    return parts


def primary_shape(headword: str, primary: str, language: str) -> str | None:
    """`auto_fail` / `review` / `ok` — a 2-word collapse is a judgement call, not a clean boolean.

    Only meaningful for a whitespace-separated headword; Chinese returns `None` and is left to the
    review pass, since character count isn't the same measure as word count.
    """
    if language.split("-")[0] == "zh" or not primary:
        return None
    hw = len(content_words(headword, language))
    pw = len(words_of(primary))
    if hw >= 3 and pw == 1:
        return "auto_fail"
    if hw == 2 and pw == 1:
        return "review"
    return "ok"


def measure(record: dict[str, Any], word: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "wordId": record["wordId"], "arm": record["arm"], "repeat": record["repeat"],
        "provider": record["provider"], "model": record["model"], "language": record["language"],
        "category": record.get("category"), "source": record.get("source"),
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
        "glossComplete": all(lang in present for lang in gloss_langs),
    }

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
        # word with one meaning the two SHOULD agree.
        "primaryEqualsShortGloss": bool(primary) and fold(primary) == fold(short),
        "shortGlossIsList": bool(re.search(r"[;,]", short)),
        "primaryCopiedList": bool(primary) and fold(primary) == fold(short) and bool(re.search(r"[;,]", short)),
        "primaryScript": script_of(primary) if primary else None,
        "primaryWrongScript": bool(primary) and script_of(primary) not in (
            expected_script(gloss_langs[0]), "none"),
        "primaryInFirstSenseTerms": bool(primary) and fold(primary) in first_terms,
        "primaryLengthRatio": round(len(primary) / len(word["headword"]), 2) if primary else None,
        "primaryContentWords": len(content_words(word["headword"], word["language"])),
        "primaryWords": len(words_of(primary)) if primary else None,
        "primaryShape": primary_shape(word["headword"], primary, word["language"]),
        "emotionText": emotion or None,
        "emotionPresent": bool(emotion),
        "emotionWords": len(words_of(emotion)),
        "emotionInRange": 3 <= len(words_of(emotion)) <= 12 if emotion else None,
        "emotionHasEmoji": has_emoji(emotion),
        "emotionEqualsExample": bool(emotion) and fold(emotion) in example_emotions,
        "emotionNull": reply.get("emotion", "__absent__") is None,
        "emotionExpect": (
            "feeling" if word.get("category") in EXPECT_FEELING
            else "null" if word.get("category") in EXPECT_NULL
            else None
        ),
    }
    return out


def score_run(run_dir: Path) -> dict[str, Any]:
    by_id = {word["id"]: word for word in dataset.words()}
    rows = []
    for path in sorted(run_dir.rglob("*.json")):
        if path.name in ("manifest.json", "summary.json"):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if "wordId" not in record:
            continue
        rows.append(measure(record, by_id[record["wordId"]]))
    summary = {
        "rows": rows,
        "byArm": {arm: arm_summary(rows, arm) for arm in ("before", "after")},
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _rate(rows: list[dict[str, Any]], predicate) -> dict[str, Any]:
    eligible = [r for r in rows if r.get("draftBuilt")]
    if not eligible:
        return {"n": 0, "rate": None}
    hits = sum(1 for r in eligible if predicate(r))
    return {"n": len(eligible), "rate": round(hits / len(eligible), 3)}


def arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    arm_rows = [r for r in rows if r["arm"] == arm]
    return {
        "calls": len(arm_rows),
        "usable": _rate(arm_rows, lambda r: True),
        "primaryAutoFail": _rate(arm_rows, lambda r: r.get("primaryShape") == "auto_fail"),
        "primaryReview": _rate(arm_rows, lambda r: r.get("primaryShape") == "review"),
        "primaryWrongScript": _rate(arm_rows, lambda r: r.get("primaryWrongScript")),
        "emotionOverall": _rate(arm_rows, lambda r: r.get("emotionPresent")),
        "emotionOnExpectFeeling": _rate(
            [r for r in arm_rows if r.get("emotionExpect") == "feeling"],
            lambda r: r.get("emotionPresent")),
        "emotionFalsePositiveOnNullControl": _rate(
            [r for r in arm_rows if r.get("emotionExpect") == "null"],
            lambda r: r.get("emotionPresent")),
        "emotionOutOfRange": _rate(
            [r for r in arm_rows if r.get("emotionPresent")],
            lambda r: r.get("emotionInRange") is False),
    }


def selftest() -> int:
    """Check the metric against the failures it exists to catch, before anything is spent."""
    word = {"id": "encender-la-computadora", "language": "es", "headword": "encender la computadora",
            "lemma": "encender", "pos": "verb", "category": "primary_multiword", "source": "real"}
    base = {
        "wordId": word["id"], "arm": "after", "repeat": 0, "provider": "p", "model": "m",
        "language": "es", "category": word["category"], "source": word["source"],
        "ok": True, "parsedJson": True,
    }
    good_reply = {
        "headword": "encender la computadora", "lemma": "encender", "pos": "verb",
        "shortGloss": "to turn on the computer",
        "primaryGloss": "turn on the computer",
        "emotion": "brisk and purposeful, getting down to business",
        "notes": [],
        "senses": [{"definition": "Poner en funcionamiento el ordenador.",
                    "glosses": [{"lang": "en", "terms": ["turn on the computer"]}],
                    "examples": []}],
    }
    good = measure({**base, "reply": good_reply}, word)
    assert good["draftBuilt"] and good["primaryShape"] == "ok", good
    assert good["emotionExpect"] == "feeling" and good["emotionPresent"], good

    # The exact reported bug: a 3-content-word headword collapsed to one English word.
    bad_reply = {**good_reply, "primaryGloss": "turn"}
    bad = measure({**base, "reply": bad_reply}, word)
    assert bad["primaryShape"] == "auto_fail", bad

    # `el disfraz` is 1 content word (the article doesn't count); `costume` matching it is fine.
    disfraz = {"id": "el-disfraz", "language": "es", "headword": "el disfraz", "lemma": "disfraz",
               "pos": "noun", "category": "primary_singleword", "source": "synthetic"}
    fine = measure({**base, "wordId": "el-disfraz", "reply": {
        **good_reply, "headword": "el disfraz", "lemma": "disfraz", "pos": "noun",
        "primaryGloss": "costume", "shortGloss": "costume; disguise",
        "senses": [{"definition": "d.", "glosses": [{"lang": "en", "terms": ["costume"]}], "examples": []}],
    }}, disfraz)
    assert fine["primaryShape"] == "ok", fine

    # A null-control word (a preposition) that still gets a forced feeling is the over-firing failure
    # the reworded `emotion` bullet must not introduce.
    control = {"id": "de", "language": "es", "headword": "de", "lemma": "de", "pos": "phrase",
               "category": "emotion_null_control", "source": "synthetic"}
    forced = measure({**base, "wordId": "de", "category": "emotion_null_control", "reply": {
        **good_reply, "headword": "de", "lemma": "de", "pos": "phrase", "primaryGloss": "of",
        "shortGloss": "of; from", "emotion": "brisk and cheerful, glad to connect two things",
        "senses": [{"definition": "d.", "glosses": [{"lang": "en", "terms": ["of"]}], "examples": []}],
    }}, control)
    assert forced["emotionExpect"] == "null" and forced["emotionPresent"], forced

    # A reply with no senses is what the shipped path refuses, and that is a datum, not a crash.
    empty = measure({**base, "reply": {**good_reply, "senses": []}}, word)
    assert empty["draftBuilt"] is False and empty["refusal"] == "llm_unusable", empty

    # An unparseable reply never reaches draft_from at all.
    broken = measure({**base, "parsedJson": False, "reply": "not json"}, word)
    assert broken["draftBuilt"] is False, broken

    print("selftest ok: the reported turn/turn-on-the-computer shape, the disfraz non-failure,\n"
          "              a forced emotion on a null control, the no-senses refusal and an\n"
          "              unparseable reply are all detected")
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
    for arm, stats in summary["byArm"].items():
        print(f"  {arm}: {json.dumps(stats, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
