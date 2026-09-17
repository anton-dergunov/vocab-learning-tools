"""A draft as a YAML reading view — what the judge is shown and what you read on screen.

A **reading** view, not a document that round-trips: ids are stripped, and nothing here is a second
writer of Acervo's YAML projection. `web/src/yaml.ts` stays the only place that projection is
understood. The key order follows `yamlForDraft` so the page reads like the editor.

`hide` is what makes the comparison blind. The two new fields exist only in one arm, so leaving them
in would label it.
"""

from __future__ import annotations

from typing import Any

import yaml

HIDE = ("primaryGloss", "emotion")

LEXEME_KEYS = ("language", "headword", "lemma", "reading", "ipa", "pos", "gender", "register",
               "dialect", "emoji", "status", "topics", "shortGloss", "primaryGloss", "emotion", "notes")
SENSE_KEYS = ("order", "definition", "definitionLang", "domain", "emoji", "glosses")
EXAMPLE_KEYS = ("text", "textLang", "translation", "translationLang", "origin", "note", "emotion")


def _compact(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Drop nulls and empty lists, so a sparse record reads as a short one — as the app's writer does."""
    out = {}
    for key in keys:
        value = source.get(key)
        if value in (None, "", [], {}):
            continue
        out[key] = value
    return out


def as_yaml(draft: dict[str, Any], reply: dict[str, Any] | None = None, *, blind: bool = True) -> str:
    body = _compact({**draft, **{k: (reply or {}).get(k) for k in HIDE}},
                    tuple(k for k in LEXEME_KEYS if not (blind and k in HIDE)))
    senses = []
    for sense in draft.get("senses") or []:
        one = _compact(sense, SENSE_KEYS)
        examples = [_compact(example, EXAMPLE_KEYS) for example in sense.get("examples") or []]
        if examples:
            one["examples"] = examples
        senses.append(one)
    if senses:
        body["senses"] = senses
    return yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=88).strip()
