"""The first of the two calls: one text call per lexeme, covering all of its senses at once.

Batched per lexeme on purpose (design §09, and `docs/acervo-sense-images.md` §03). A call that sees
every sense of `venom` at once can deliberately make the two pictures look nothing alike, which is
the only reason per-sense images beat one picture per word.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .graph import ArticleView
from .styles import StyleTable

FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True)
class SenseBrief:
    sense_id: str
    style_id: str
    anchor_example_id: str | None
    subject: str
    brief: str
    refused: bool
    refusal_reason: str | None


def _example_payload(example: dict, anchor_id: str | None) -> dict[str, Any]:
    return {
        "id": example.get("id"),
        "text": example.get("text"),
        "translation": example.get("translation"),
        "origin": example.get("origin"),
        "isAnchor": example.get("id") == anchor_id,
    }


def build_request(article: ArticleView, styles: StyleTable, weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Everything the writer sees about one word, and every style it may choose from."""
    lexeme = article.lexeme
    vocabulary = article.vocabulary or {}
    senses = []
    for sense in article.senses:
        anchor = sense.anchor
        senses.append(
            {
                "senseId": sense.id,
                "definition": sense.definition,
                "domain": sense.domain,
                "glosses": sense.glosses,
                "examples": [_example_payload(example, anchor.get("id") if anchor else None)
                             for example in sense.examples],
            }
        )
    return {
        "headword": lexeme.get("headword"),
        "lemma": lexeme.get("lemma"),
        "language": lexeme.get("language"),
        "pos": lexeme.get("pos"),
        "register": lexeme.get("register"),
        "dialect": lexeme.get("dialect"),
        "shortGloss": lexeme.get("shortGloss"),
        "notes": lexeme.get("notes") or [],
        "topics": article.topics,
        "glossLangs": vocabulary.get("glossLangs") or [],
        "senses": senses,
        "styles": [
            {"styleId": style.id, "label": style.label, "mono": style.mono}
            for style in styles.offer(weights, rotate=article.id)
        ],
    }


def parse_reply(text: str, article: ArticleView, offered: tuple[str, ...]) -> list[SenseBrief]:
    """Treat the reply as untrusted: an unknown style or sense id is an error, not a nudge."""
    cleaned = FENCE.sub("", text.strip())
    try:
        payload = json.loads(cleaned)
    except ValueError as error:
        raise ValueError(f"The brief writer did not return JSON: {error}") from error

    entries = payload.get("senses")
    if not isinstance(entries, list):
        raise ValueError("The brief writer returned no `senses` list.")

    known = {sense.id for sense in article.senses}
    out: list[SenseBrief] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("A sense entry was not an object.")
        sense_id = str(entry.get("senseId", ""))
        if sense_id not in known:
            raise ValueError(f"The brief writer named an unknown sense {sense_id!r}.")
        refused = bool(entry.get("refused"))
        if refused:
            out.append(SenseBrief(sense_id, "", None, "", "", True,
                                  str(entry.get("refusalReason") or "unstated")))
            continue
        style_id = str(entry.get("styleId", ""))
        if style_id not in offered:  # an invented style names nothing, so it cannot be reproduced
            raise ValueError(
                f"The brief writer chose {style_id!r} for sense {sense_id}, which is not a style."
            )
        brief = str(entry.get("brief") or "").strip()
        if not brief:
            raise ValueError(f"The brief writer returned an empty brief for sense {sense_id}.")
        anchor = entry.get("anchorExampleId")
        out.append(SenseBrief(sense_id, style_id, str(anchor) if anchor else None,
                              str(entry.get("subject") or "").strip(), brief, False, None))

    missing = known - {item.sense_id for item in out}
    if missing:
        raise ValueError(f"The brief writer skipped {len(missing)} sense(s).")
    return out


class BriefWriter:
    def __init__(self, client: genai.Client, model: str, template_path: str | Path,
                 styles: StyleTable, weights: dict[str, float] | None = None) -> None:
        self.client = client
        self.model = model
        self.template = Path(template_path).read_text(encoding="utf-8")
        self.styles = styles
        self.weights = weights

    def write(self, article: ArticleView) -> tuple[list[SenseBrief], dict[str, Any]]:
        request = build_request(article, self.styles, self.weights)
        offered = tuple(style["styleId"] for style in request["styles"])
        contents = f"{self.template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = response.text or ""
        briefs = parse_reply(text, article, offered)
        usage = response.usage_metadata
        return briefs, {
            "model": self.model,
            "promptTokens": getattr(usage, "prompt_token_count", None),
            "outputTokens": getattr(usage, "candidates_token_count", None),
            "thoughtTokens": getattr(usage, "thoughts_token_count", None),
            "stylesOffered": len(offered),
        }
