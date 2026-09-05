"""A read-only pull of the vocabulary graph, and the articles assembled from it.

Deliberately a duplicate of the shape `web/src/selectors.ts` derives rather than a shared one:
this stage runs beside a live ingestion and must not be able to disturb it. It calls exactly two
routes, `POST /session` and `GET /graph`, and neither writes.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable

API_PATH = "/api/acervo/v1"
SCHEMA_VERSION = 6
REQUEST_TIMEOUT = 300

# An entry the learner has put away is not worth spending an image on.
GENERATED_STATUSES = ("inbox", "active", "learned")

EXAMPLE_PREFERENCE = {"attestation": 0, "manual": 1, "tatoeba": 2, "subtitle": 3, "wiktionary": 4, "llm": 5}


class AcervoError(RuntimeError):
    pass


class ReadOnlyClient:
    """Two routes, both reads. There is no write method here on purpose."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def _call(self, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}{API_PATH}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        request.add_header("Accept", "application/json")
        if data:
            request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read()).get("data") or {}
        except urllib.error.HTTPError as error:
            body: dict[str, Any] = {}
            try:
                body = json.loads(error.read())
            except Exception:  # noqa: BLE001 - the body is diagnostic, not required
                pass
            problem = body.get("error") or {}
            raise AcervoError(
                problem.get("message") or f"The server refused the request ({error.code})."
            ) from error
        except urllib.error.URLError as error:
            raise AcervoError(f"The Acervo server could not be reached: {error.reason}") from error

    def sign_in(self, email: str, password: str) -> None:
        self.token = self._call("/session", {"email": email, "password": password})["token"]

    def pull(self) -> dict[str, list[dict]]:
        query = urllib.parse.urlencode({"since": 0, "schemaVersion": SCHEMA_VERSION})
        result = self._call(f"/graph?{query}")
        return result.get("changes") or {}


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
            )
        )
    return articles
