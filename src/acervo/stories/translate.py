"""The translation call: the whole story at once, asked cold.

**The whole story, not a part at a time**, and that is the design rather than an optimisation. A
name, a nickname and a running joke have to read the same in every part, and a model shown one
paragraph in isolation has no way to know what it already called somebody. Per-part calls are also
where an off-by-one becomes possible at all.

Cold, because this is the opposite task to writing one. `TRANSLATE_PARAMS` asks for a low
temperature; a row that pins its own still wins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from acervo.models import call, chain
from acervo.models.catalogue import Catalogue
from acervo.models.errors import ProviderUnavailable
from acervo.stories.write import Part

TRANSLATE_PARAMS: Mapping[str, Any] = {"temperature": 0.2}


@dataclass(frozen=True)
class Translated:
    title: str
    parts: tuple[Part, ...]


def build_request(
    *, title: str, parts: Sequence[Part], source_name: str, target_name: str, target_code: str
) -> dict[str, Any]:
    return {
        "from": source_name,
        "into": {"code": target_code, "name": target_name},
        "title": title,
        "parts": [{"heading": part.heading, "text": part.text} for part in parts],
    }


def parse_reply(payload: Any, parts: Sequence[Part]) -> Translated:
    if not isinstance(payload, Mapping):
        raise ValueError("the reply was not a JSON object")
    raw = payload.get("parts")
    if not isinstance(raw, list):
        raise ValueError("the reply had no parts")
    # **Count first, and exactly.** Each translation is shown beside its own original, so one part
    # too few puts every later translation under the wrong picture — a failure that looks like a bad
    # translation rather than like a bad count, and is nearly impossible to diagnose from the page.
    if len(raw) != len(parts):
        raise ValueError(f"the story has {len(parts)} parts and the translation has {len(raw)}")

    translated: list[Part] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            raise ValueError(f"translated part {index + 1} is not an object")
        text = str(entry.get("text") or "").strip()
        if not text:
            raise ValueError(f"translated part {index + 1} is empty")
        translated.append(Part(heading=str(entry.get("heading") or "").strip(), text=text))

    return Translated(title=str(payload.get("title") or "").strip(), parts=tuple(translated))


class Translator:
    def __init__(self, catalogue: Catalogue, candidates: Sequence[chain.Candidate], template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def translate(
        self, request: Mapping[str, Any], parts: Sequence[Part]
    ) -> tuple[Translated, dict[str, Any]]:
        prompt = f"{self.template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"

        def ask(candidate: chain.Candidate) -> call.TextResult:
            result = call.text(
                prompt, row=candidate.row, model=candidate.model, as_json=True,
                params=TRANSLATE_PARAMS,
            )
            if not result.text.strip():
                raise ProviderUnavailable("empty", "the model returned nothing",
                                          provider_id=candidate.row.id, model=candidate.model)
            try:
                parse_reply(result.parsed, parts)
            except ValueError as error:
                raise ProviderUnavailable(
                    "unusable", f"the translation did not hold its shape: {error}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return result

        answered = chain.walk(
            "text", [c.named for c in self.candidates], self.catalogue, ask, chain.stamped,
            caller="story.translate",
        )
        return parse_reply(answered.parsed, parts), {
            "provider": answered.answer.provider_id,
            "model": answered.answer.model,
            "seconds": round(answered.answer.seconds, 2),
            "costUsd": answered.answer.cost_usd,
        }
