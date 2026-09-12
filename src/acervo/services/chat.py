"""One turn of conversation about one word.

The device assembles what is discussed and sends it; this layer holds the credentials, owns the
prompt, and writes nothing. That split is deliberate (design `§06`, revised): `web/src/yaml.ts` is
the only place the article projection is understood, so a server-side serialiser would be a second
implementation of it, drifting from the first the moment a field is added. The document that arrives
came from that owner's own replica and goes nowhere but into their own prompt.

Two subject kinds, two prompts, and they differ in exactly two places: which file is read, and which
of `proposal` / `capture` survives. An article subject may be proposed against; a dictionary entry
may not, because there is nothing editable on screen.

Everything the model returns is untrusted. The rule from `capture/coerce.py` applies unchanged —
coerce what can be coerced, drop what cannot — with one addition: a malformed proposal drops the
*whole* proposal and leaves the prose, because half an edit is worse than none and the answer is
still worth reading.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from acervo.errors import ApiError
from acervo.services.capture.coerce import (
    REFERENCE_LIMIT,
    pick_optional_choice,
    text_list,
    trimmed,
)
from acervo.services.models import llm_json
from acervo.services.prompts import prompt_text
from acervo.settings import Settings

DOCUMENT_LIMIT = 32000
TURN_LIMIT = 8
NEIGHBOUR_LIMIT = 20
REPLY_LIMIT = 1200
FOLLOW_UP_LIMIT = 3
FOLLOW_UP_CHARS = 40
OP_LIMIT = 12

REFERENCE_MODES = ("faithful", "expand")

# What each operation must carry to be worth sending to a client, as (field, kind). This is the
# *shape* only — whether `sense:kq2…` names a record, whether `notes` may be set on it, and whether
# the value is of the right type are questions about the document's meaning, and the document is a
# YAML string this layer deliberately does not parse. `web/src/articleEdit.ts` answers those.
_OP_SHAPE: dict[str, tuple[tuple[str, type], ...]] = {
    "set": (("target", str), ("field", str)),
    "addSense": (("sense", dict),),
    "addExample": (("senseId", str), ("example", dict)),
    "addAttestation": (("ref", str), ("attestation", dict)),
    "remove": (("target", str),),
    "orderSenses": (("ids", list),),
}


UNUSABLE = "The language model did not return a usable answer, so nothing was changed."


def run_chat(settings: Settings, owner: str, body: dict[str, Any]) -> dict[str, Any]:
    subject = _subject(body)
    name = "acervo_chat" if subject["kind"] == "article" else "acervo_chat_reference"
    try:
        answer, call = llm_json(
            settings, owner, prompt_text(settings.prompts_path, name), _user_turn(subject, body)
        )
    except ApiError as refused:
        # `llm_json`'s own two messages end "so nothing was created", which is true of every other
        # caller and false of this one: chat creates nothing, ever. Re-phrase those two rather than
        # forking `REFUSALS` — that table is a contract the file ingestion retries against by code,
        # and the seven mapped refusals keep their wording untouched.
        if refused.code in ("llm_empty", "llm_unusable"):
            raise ApiError(refused.status, refused.code, UNUSABLE) from None
        raise
    if not isinstance(answer, Mapping):
        raise ApiError(502, "llm_unusable", UNUSABLE)
    return _shaped(answer, subject, call.model)


def _subject(body: dict[str, Any]) -> dict[str, Any]:
    raw = body.get("subject")
    if not isinstance(raw, Mapping):
        raise ApiError(400, "invalid_input", "That request does not say what it is about.")
    kind = trimmed(raw.get("kind"))
    if kind == "article":
        document = trimmed(raw.get("document"))
        if not document:
            raise ApiError(400, "invalid_input", "That request carries no entry to talk about.")
        return {
            "kind": "article",
            "lexemeId": trimmed(raw.get("lexemeId")),
            "document": document[:DOCUMENT_LIMIT],
            "focus": trimmed(raw.get("focus")) or None,
        }
    if kind == "reference":
        headword = trimmed(raw.get("headword"))
        if not headword:
            raise ApiError(400, "invalid_input", "That request carries no word to talk about.")
        return {
            "kind": "reference",
            "headword": headword,
            "language": trimmed(raw.get("language")) or None,
        }
    raise ApiError(400, "invalid_input", "That request is about something Acervo does not recognise.")


def _turns(body: dict[str, Any]) -> list[dict[str, str]]:
    """The transcript, oldest first, capped. The last `you` turn is the question being asked."""
    raw = body.get("turns")
    if not isinstance(raw, list):
        return []
    kept: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        text = trimmed(item.get("text"))
        if not text:
            continue
        role = "you" if trimmed(item.get("role")) == "you" else "acervo"
        kept.append({"role": role, "text": text})
    return kept[-TURN_LIMIT:]


def _neighbours(body: dict[str, Any]) -> list[dict[str, str]]:
    """Headword and gloss only — enough to say "you already have «el traje»", and nothing more."""
    raw = body.get("neighbours")
    if not isinstance(raw, list):
        return []
    kept: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        headword = trimmed(item.get("headword"))
        if not headword:
            continue
        kept.append({"headword": headword, "shortGloss": trimmed(item.get("shortGloss"))})
        if len(kept) == NEIGHBOUR_LIMIT:
            break
    return kept


def _user_turn(subject: dict[str, Any], body: dict[str, Any]) -> str:
    reference = trimmed(body.get("reference"))[:REFERENCE_LIMIT]
    sources = text_list(body.get("referenceSources"))
    neighbours = _neighbours(body)
    turns = _turns(body)

    return "\n".join(
        line
        for line in [
            "The learner's own entry for this word, in the projection Acervo stores.\n"
            "THIS IS THE SOURCE OF TRUTH, and the only thing you may propose changing:\n"
            "```\n" + subject["document"] + "\n```"
            if subject["kind"] == "article"
            else "",
            "They tapped this part of the entry, so keep any edit inside it: " + subject["focus"]
            if subject["kind"] == "article" and subject["focus"]
            else "",
            "The dictionary entry they are reading: " + subject["headword"]
            if subject["kind"] == "reference"
            else "",
            "Its language: " + subject["language"]
            if subject["kind"] == "reference" and subject["language"]
            else "",
            "",
            "Other words this learner already has, so you can point at one by name:\n"
            + "\n".join(
                f"- {item['headword']}" + (f" — {item['shortGloss']}" if item["shortGloss"] else "")
                for item in neighbours
            )
            if neighbours
            else "",
            "\nExternal dictionary entries open on the same screen"
            + (f" (from {', '.join(sources)})" if sources else "")
            + ". READ-ONLY reference,\noften poor, and never something you may propose changing:\n"
            "```\n" + reference + "\n```"
            if reference
            else "",
            "\nThe conversation so far, oldest first. The last line is what they are asking now:\n"
            + "\n".join(f"{item['role']}: {item['text']}" for item in turns)
            if turns
            else "",
        ]
        if line != ""
    )


def _shaped(answer: Mapping[str, Any], subject: dict[str, Any], model: str) -> dict[str, Any]:
    reply = trimmed(answer.get("reply"))
    if not reply:
        raise ApiError(502, "llm_unusable", UNUSABLE)
    follow_ups = [text[:FOLLOW_UP_CHARS] for text in text_list(answer.get("followUps"))]
    return {
        "reply": reply[:REPLY_LIMIT],
        "followUps": follow_ups[:FOLLOW_UP_LIMIT],
        # Which of the two survives is the whole difference between the subject kinds. A dictionary
        # entry is not the learner's to edit, so a proposal against one is dropped rather than
        # refused: the prose is still worth reading.
        "proposal": _proposal(answer.get("proposal")) if subject["kind"] == "article" else None,
        "capture": _capture(answer.get("capture")) if subject["kind"] == "reference" else None,
        "modelId": model,
    }


def _proposal(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    ops = raw.get("ops")
    if not isinstance(ops, list) or not ops or len(ops) > OP_LIMIT:
        return None
    shaped: list[dict[str, Any]] = []
    for item in ops:
        op = _op(item)
        # One malformed operation drops the whole proposal. A partly-readable edit set is exactly
        # the thing `applyOps` refuses on the device, and shipping it would only move the refusal
        # somewhere the reader cannot tell a model's mistake from Acervo's.
        if op is None:
            return None
        shaped.append(op)
    return {"summary": trimmed(raw.get("summary")), "ops": shaped}


def _op(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    name = trimmed(raw.get("op"))
    required = _OP_SHAPE.get(name)
    if required is None:
        return None
    op: dict[str, Any] = {"op": name}
    for field, kind in required:
        value = raw.get(field)
        if kind is str:
            text = trimmed(value)
            if not text:
                return None
            op[field] = text
        elif not isinstance(value, kind):
            return None
        else:
            op[field] = value
    if name == "orderSenses":
        ids = [trimmed(item) for item in op["ids"]]
        if not ids or not all(ids):
            return None
        op["ids"] = ids
    if name == "set":
        # `value` is the one field with no shape at all: a string, a list of strings, a list of
        # gloss objects, or null, depending on which field is being set. The device knows which.
        op["value"] = raw.get("value")
    if name == "addSense":
        op["after"] = trimmed(raw.get("after")) or None
    if name == "addExample":
        # Accepted at the top level or inside `example`, because a real model puts it in both
        # places. This is not compatibility machinery: the answer is untrusted input and reading it
        # generously is what `capture/coerce.py` exists for. Getting it wrong is *silent* — the
        # applier would derive `origin: "llm"` for a sentence the learner actually met, which is a
        # provenance lie no validation would catch.
        nested = op["example"].pop("fromAttestation", None)
        op["fromAttestation"] = trimmed(raw.get("fromAttestation")) or trimmed(nested) or None
    if name == "remove":
        op["reason"] = trimmed(raw.get("reason"))
    return op


def _capture(raw: Any) -> dict[str, Any] | None:
    """The argument list for the capture the interface already performs from an external article."""
    if not isinstance(raw, Mapping):
        return None
    headword = trimmed(raw.get("headword"))
    if not headword:
        return None
    return {
        "headword": headword,
        "note": trimmed(raw.get("note")),
        "referenceMode": pick_optional_choice(raw.get("referenceMode"), REFERENCE_MODES),
    }
