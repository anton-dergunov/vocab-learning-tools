"""The one model call: which recorded utterance, if any, is a good example of which sense.

One call per *lexeme*, covering all of its senses against one bounded candidate set. The model is
the last and best quality gate, not the retrieval mechanism (`docs/plans/spoken-clips.md` §2.7): the
corpus does IR over millions of segments because it must, and Acervo spends one frontier call per
word on the judgement a feature cannot make — reading a messy fragment and deciding whether it is
really an instance of *this* sense.

Three things follow, and all three are the point.

**Refusing is the default, not the failure.** A thin corpus must produce articles with no clips,
never articles with bad clips. A sense with no selection is a successful outcome and is not counted
as anything.

**The stored text is the corpus's sentence, verbatim.** The model chooses; it never rewrites, trims
or joins (§2.6). Where a passage starts and ends is an open research question in the other
repository, and a model that quietly re-cut it would make those measurements meaningless and break
the audit that `clipRef` exists for.

**An id the request did not offer is dropped and counted, never a refusal of the whole word.** This
is the deliberate difference from `images/brief.parse_reply`, which raises: a hallucinated id is a
prompt bug to fix, and refusing the batch would throw away the good selections with it.

This package stands alone. It imports `acervo.models`, `acervo.article` and its own corpus client,
and nothing else of Acervo's — so the request path and the batch sweep are two callers of one
pipeline rather than two pipelines.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from acervo.article import ArticleView
from acervo.models import ChainExhausted, TextResult, call, chain, journal
from acervo.models.catalogue import Catalogue
from acervo.models.errors import SHAPE_TRIES, ProviderUnavailable

from .corpus import Candidate

# What the selector must return. Sent as `response_format` where the row understands one and written
# into the prompt where it does not — the row decides, and `parse_reply` checks the answer either
# way against *this* article's sense ids and the segments *this* call offered, neither of which a
# schema can name.
#
# **`segmentId` is required, and null is how a sense declines.** Where the schema is sent natively
# it becomes the definition of a legal answer, so a merely *optional* `segmentId` let a model omit
# it for every sense — a reply that satisfied the schema, named no clip, and read exactly like the
# honest "none of these are good enough" this pipeline is built to expect. Requiring the field while
# allowing null keeps refusing as cheap as §2.7 demands and makes silence impossible to mistake for
# a decision. `images/brief.py` carries the same note and the same scar.
#
# `translation` and `matchedTranslationForm` stay optional: they are absent by definition when
# nothing was chosen.
SELECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "senses": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "senseId": {"type": "string"},
                    "segmentId": {"type": ["string", "null"]},
                    "translation": {"type": "string"},
                    "matchedTranslationForm": {"type": "string"},
                },
                "required": ["senseId", "segmentId"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["senses"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Selection:
    """One sense's clip, and the article line that goes under it.

    The translation comes from this same call (§2.13), in `glossLangs[0]`, exactly as
    `acervo_compose.md` produces one beside every generated example. No second call and no second
    provider configuration: the retrieval service can translate too, but what *it* produces is the
    player's interactive alignment, which Acervo stores none of.
    """

    sense_id: str
    candidate: Candidate
    translation: str | None
    matched_translation_form: str | None


def _example_payload(example: dict) -> dict[str, Any]:
    return {
        "text": example.get("text"),
        "translation": example.get("translation"),
        "origin": example.get("origin"),
    }


def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
    """What the model is told about one segment.

    Every field here is prompt weight, so every one has to earn its place —
    `docs/plans/clip-selection-experiment.md` names this set as the first thing to vary. The
    provenance fields are here because a learner judging *naturalness* would want them: an
    automatic caption of streamed Rioplatense conversation is a different kind of evidence from an
    authored subtitle on a scripted lesson.
    """
    return {
        "segmentId": candidate.segment_id,
        "sentence": candidate.sentence,
        "matchedForm": candidate.matched_surface,
        "channel": candidate.channel,
        "speechStyle": list(candidate.speech_style),
        "variety": list(candidate.varieties),
        "captionKind": candidate.caption_kind,
        "boundary": candidate.boundary_reason,
    }


def build_request(article: ArticleView, candidates: Sequence[Candidate],
                  gloss_lang: str) -> dict[str, Any]:
    """Everything the selector sees: one word, its senses, and the segments retrieved for it.

    The senses are described the way `prompts/acervo_image_brief.md` describes them, and for the
    reason that prompt learned the hard way — the definition in the language being learned is the
    authority and the glosses are hints that can mislead. Judging a fragment against an English
    gloss finds instances of the English word instead of the Spanish one.
    """
    lexeme = article.lexeme
    return {
        "headword": article.headword,
        "lemma": article.lemma,
        "language": article.language,
        "pos": lexeme.get("pos"),
        "register": lexeme.get("register"),
        "shortGloss": lexeme.get("shortGloss"),
        # The language the article's own translation line must be written in.
        "translationLang": gloss_lang,
        "senses": [
            {
                "senseId": sense.id,
                # Named so the model can see that the definition is in the language being learned
                # and the glosses are not: the definition rules, the glosses are hints.
                "definition": sense.definition,
                "definitionLang": sense.definition_lang,
                "domain": sense.domain,
                "glosses": sense.glosses,
                "examples": [_example_payload(example) for example in sense.examples],
            }
            for sense in article.senses
        ],
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
    }


def parse_reply(payload: Any, article: ArticleView,
                offered: Sequence[Candidate]) -> tuple[list[Selection], int]:
    """The selections, and how many the reply named that the request never offered.

    The count is surfaced rather than swallowed: an invented id is a prompt bug, and one that is
    dropped silently is a prompt bug nobody finds.
    """
    if not isinstance(payload, dict):
        raise ValueError("The clip selector did not return an object.")
    entries = payload.get("senses")
    if not isinstance(entries, list):
        raise ValueError("The clip selector returned no `senses` list.")
    # **Refusing is an answer; saying nothing is not, and the two must not look alike.** A reply of
    # `segmentId: null` for every sense is the expected outcome for most words and passes straight
    # through below. An *empty list* is not that: it answers nothing at all, and because the caller
    # stamps `clipsSearchedAt` on a clean return and §2.12 ships no rescan, letting it through marks
    # the word consulted-and-empty for good. Deliberately only the empty case — an id this article
    # does not have stays dropped-and-counted, never a refusal of the whole word.
    if article.senses and not entries:
        raise ValueError("The clip selector returned no senses at all.")

    by_segment = {candidate.segment_id: candidate for candidate in offered}
    known = {sense.id for sense in article.senses}
    taken: set[str] = set()
    out: list[Selection] = []
    dropped = 0

    for entry in entries:
        if not isinstance(entry, dict):
            dropped += 1
            continue
        sense_id = str(entry.get("senseId") or "")
        segment_id = str(entry.get("segmentId") or "")
        if not segment_id:
            continue        # a refusal, which is the expected outcome for most words
        if sense_id not in known or sense_id in taken or segment_id not in by_segment:
            dropped += 1
            continue
        taken.add(sense_id)
        candidate = by_segment[segment_id]
        translation = str(entry.get("translation") or "").strip() or None
        # **A translation that names the segment is not a translation.** `gemini-3.5-flash-lite`
        # answers this schema by running two fields into one string — "…something to eat.,
        # segmentId: seg_4270b0…" — with `matchedTranslationForm` left empty. Stored, that reaches
        # the article as a sentence with an internal id in it, and the clip search is one-shot, so
        # nothing would ever replace it. Raised rather than dropped: a model that merges fields does
        # it for every entry it writes, which is a fact about the model and exactly what the pair
        # behind it is for.
        if translation and (segment_id in translation or "segmentId" in translation):
            raise ValueError(
                f"The clip selector wrote the segment id into the translation for sense {sense_id}."
            )
        matched = str(entry.get("matchedTranslationForm") or "").strip() or None
        # The invariant is verbatim, untrimmed and un-normalised. A form that does not hold loses
        # the form rather than being stored as a lie — the rule the capture path already follows.
        if matched and not (translation and matched in translation):
            matched = None
        out.append(Selection(sense_id, candidate, translation, matched))

    return out, dropped


class ClipSelector:
    """One text call per lexeme, through the owner's chain.

    Given resolved candidates and the prompt *text* rather than a chain to resolve and a path to
    read: this package may not read `Settings`, and resolving once is what makes a mistyped provider
    refuse before any money is spent instead of at the first word of a sweep.
    """

    def __init__(self, catalogue: Catalogue, candidates: Sequence[chain.Candidate],
                 template: str) -> None:
        self.catalogue = catalogue
        self.candidates = tuple(candidates)
        self.template = template

    def select(self, article: ArticleView, candidates: Sequence[Candidate], gloss_lang: str,
               attempts: int = 4,
               wait: Callable[[float], None] = time.sleep) -> tuple[list[Selection], int, dict[str, Any]]:
        """Wait out a chain that is entirely over quota, the way `BriefWriter.write` does.

        The chain handles one provider being rate limited by moving to the next, so this loop only
        runs when *every* pair has refused — the single-provider case, and the long sweep that
        eventually meets a daily allowance.
        """
        for attempt in range(1, attempts + 1):
            try:
                return self._select_once(article, candidates, gloss_lang)
            except ChainExhausted as exhausted:
                if attempt == attempts or (exhausted.waited_on_nothing and attempt >= SHAPE_TRIES):
                    raise
                # Only a quota or an outage is worth sleeping on; a chain that answered with the
                # wrong shape will answer the same way after any delay. See `BriefWriter.write`.
                if not exhausted.waited_on_nothing:
                    wait(min(15.0 * 2 ** (attempt - 1), 240.0))
        raise AssertionError("unreachable")

    def _select_once(self, article: ArticleView, candidates: Sequence[Candidate],
                     gloss_lang: str) -> tuple[list[Selection], int, dict[str, Any]]:
        request = build_request(article, candidates, gloss_lang)
        prompt = f"{self.template}\n\n{json.dumps(request, ensure_ascii=False, indent=2)}\n"

        def ask(candidate: chain.Candidate) -> TextResult:
            answered = call.text(
                prompt, row=candidate.row, model=candidate.model, schema=SELECTION_SCHEMA,
                timeout=call.SHORT_TIMEOUT_SECONDS,
            )
            # Judged inside the chain's callback, exactly as `images/brief.py` judges its own, so a
            # model that cannot hold the shape is passed over instead of having its answer accepted.
            # This one matters more than the brief's: an unusable reply here is indistinguishable
            # from an honest refusal, and the caller stamps `clipsSearchedAt` on a clean return with
            # nothing ever re-searching. Parsed twice on the happy path, which is microseconds
            # against a model call.
            try:
                parse_reply(answered.parsed, article, candidates)
            except ValueError as unusable:
                raise ProviderUnavailable(
                    "unusable", f"{unusable} — got {journal.excerpt(answered.text)}",
                    provider_id=candidate.row.id, model=candidate.model,
                ) from None
            return answered

        result: TextResult = chain.walk(
            "text",
            [candidate.named for candidate in self.candidates],
            self.catalogue,
            ask,
            chain.stamped,
            caller="clips",
        )
        selections, dropped = parse_reply(result.parsed, article, candidates)
        answer = result.answer
        return selections, dropped, {
            "provider": answer.provider_id,
            # The model that *answered*, not the one asked first. A fall-through that left this
            # naming the head of the chain would be a lie in every record it stamped.
            "model": answer.model,
            "seconds": round(answer.seconds, 2),
            "costUsd": answer.cost_usd,
            "candidatesOffered": len(candidates),
        }
