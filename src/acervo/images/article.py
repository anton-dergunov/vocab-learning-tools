"""The article view the brief writer is given, assembled from wire-shaped records.

One view model with two feeders, the way `articleFor` and `articleFromDraft` both build one
`Article` on the client. `build_articles` takes the `changes` mapping the graph route speaks, so the
worker sweep feeds it a `client.pull_graph()` payload and `services/images.py` feeds it rows the
repository projected — neither knows which. That is what keeps the interactive path and the
unattended one on one pipeline rather than two.

Deliberately a duplicate of the shape `web/src/selectors.ts` derives rather than a shared one. The
pull itself is `acervo.client`; this module reads no graph and opens no connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# An entry the learner has put away is not worth spending an image on.
GENERATED_STATUSES = ("inbox", "active", "learned")

EXAMPLE_PREFERENCE = {"attestation": 0, "manual": 1, "tatoeba": 2, "subtitle": 3, "wiktionary": 4, "llm": 5}


def live(records: Iterable[dict]) -> list[dict]:
    return [record for record in records if not record.get("deleted")]


@dataclass
class SenseView:
    id: str
    definition: str
    definition_lang: str
    domain: str | None
    glosses: list[dict]
    order: int
    examples: list[dict] = field(default_factory=list)
    has_image: bool = False

    @property
    def anchor(self) -> dict | None:
        if not self.examples:
            return None
        return min(
            self.examples,
            key=lambda example: (
                EXAMPLE_PREFERENCE.get(example.get("origin", "llm"), 9),
                example.get("createdAt", ""),
                example.get("id", ""),
            ),
        )


@dataclass
class ArticleView:
    lexeme: dict
    vocabulary: dict | None
    topics: list[str]
    senses: list[SenseView]
    # The live image-prompt rows for this word, so a caller writing new ones can see what it is
    # editing. `SenseView.has_image` answers "is there a picture"; this answers "what does the row
    # say", which is what a re-brief needs in order to keep the revision, the attempt count and the
    # picture already drawn.
    image_prompts: list[dict] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.lexeme["id"]

    @property
    def headword(self) -> str:
        return self.lexeme.get("headword", "")

    @property
    def language(self) -> str:
        return self.lexeme.get("language", "")


def build_articles(changes: dict[str, list[dict]], language: str | None = None) -> list[ArticleView]:
    """Every lexeme worth considering, with its senses and their examples attached."""
    vocabularies = {record["language"]: record for record in live(changes.get("vocabularies", []))}
    topics = {record["id"]: record for record in live(changes.get("topics", []))}
    lexemes = live(changes.get("lexemes", []))
    senses = live(changes.get("senses", []))
    examples = live(changes.get("examples", []))
    prompts = live(changes.get("imagePrompts", []))

    drawn = {prompt.get("senseId") for prompt in prompts if prompt.get("imageRef")}
    prompts_by_lexeme: dict[str, list[dict]] = {}
    for prompt in prompts:
        prompts_by_lexeme.setdefault(prompt.get("lexemeId", ""), []).append(prompt)

    by_lexeme: dict[str, list[SenseView]] = {}
    for sense in sorted(senses, key=lambda record: (record.get("order", 0), record.get("id", ""))):
        view = SenseView(
            id=sense["id"],
            definition=sense.get("definition", ""),
            definition_lang=sense.get("definitionLang", ""),
            domain=sense.get("domain"),
            glosses=sense.get("glosses") or [],
            order=int(sense.get("order", 0) or 0),
            has_image=sense["id"] in drawn,
        )
        by_lexeme.setdefault(sense["lexemeId"], []).append(view)

    index = {view.id: view for views in by_lexeme.values() for view in views}
    for example in examples:
        view = index.get(example.get("senseId", ""))
        if view is not None:
            view.examples.append(example)

    articles = []
    for lexeme in sorted(lexemes, key=lambda record: (record.get("headword", ""), record.get("id", ""))):
        if language and lexeme.get("language") != language:
            continue
        if lexeme.get("status") not in GENERATED_STATUSES:
            continue
        views = by_lexeme.get(lexeme["id"], [])
        if not views:
            continue
        articles.append(
            ArticleView(
                lexeme=lexeme,
                vocabulary=vocabularies.get(lexeme.get("language", "")),
                topics=[topics[topic]["name"] for topic in lexeme.get("topicIds", []) if topic in topics],
                senses=views,
                image_prompts=prompts_by_lexeme.get(lexeme["id"], []),
            )
        )
    return articles
