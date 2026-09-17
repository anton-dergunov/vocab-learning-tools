"""The draft as a change set, for the transports that have no replica to diff against."""

from __future__ import annotations

from typing import Any

from acervo.domain.ids import new_record_id, now_instant
from acervo.repository import graph


def apply_draft(owner: str, device: str, draft: dict[str, Any], topics: list[dict[str, Any]]) -> str:
    at = now_instant()
    stamp = {"deleted": False, "createdAt": at, "editedAt": at, "editedBy": device, "revision": 0}
    topic_ids = {topic["name"].lower(): topic["id"] for topic in topics}
    lexeme_id = new_record_id()

    changes: dict[str, list[dict[str, Any]]] = {
        "topics": [],
        "lexemes": [],
        "senses": [],
        "attestations": [],
        "examples": [],
        "imagePrompts": [],
        "studyStates": [],
    }
    changes["lexemes"].append(
        {
            "id": lexeme_id,
            "language": draft["language"],
            "headword": draft["headword"],
            "lemma": draft["lemma"],
            "reading": draft["reading"],
            "ipa": draft["ipa"],
            "pos": draft["pos"],
            "gender": draft["gender"],
            "register": draft["register"],
            "dialect": draft["dialect"],
            "emoji": draft["emoji"],
            "topicIds": [topic_ids[name.lower()] for name in draft["topics"] if name.lower() in topic_ids],
            # Applied with nobody reviewing it — an ingestion script, a headless transport — which is
            # exactly what the Inbox is for.
            "status": "inbox",
            "shortGloss": draft["shortGloss"],
            "notes": draft["notes"],
            **stamp,
        }
    )

    for attestation in draft["attestations"]:
        changes["attestations"].append({**attestation, "lexemeId": lexeme_id, **stamp})

    for sense in draft["senses"]:
        changes["senses"].append(
            {
                "id": sense["id"],
                "lexemeId": lexeme_id,
                "definition": sense["definition"],
                "definitionLang": sense["definitionLang"],
                "glosses": sense["glosses"],
                "domain": sense["domain"],
                "emoji": sense["emoji"],
                "order": sense["order"],
                **stamp,
            }
        )
        for example in sense["examples"]:
            changes["examples"].append({**example, "senseId": sense["id"], **stamp})

    # The same route every other writer uses: same validation, same revision allocation, same
    # transaction. Nothing about capture gets a private way into the store.
    graph.merge_graph(owner, device, changes, enqueue=graph.Enqueue("ingest"))
    return lexeme_id
