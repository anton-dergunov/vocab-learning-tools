"""A chain of (provider, model) pairs, walked in order.

It falls through on 429 and 5xx and never on anything else. That rule is the locked one and it is
the whole of this module's judgement: an authentication failure or a rejected configuration is a
mistake to fix, not a condition to route around, and falling through on it hides the mistake and
spends money at the next provider.

**The unit is a pair, not a provider.** A free tier is metered per model, so two models with 500
requests a day each are a thousand requests a day and the second is reached by the first one's 429.
The default walk is therefore provider by provider and, inside each, model by model — the order the
catalogue lists them in.

A refusal is also remembered, in `cooldown.py`: a pair that has just been rate limited goes to
the back of the queue for a while, so an exhausted free tier is not re-probed on every entry. It is
only ever an ordering hint — when every pair is resting the hints are ignored and the chain is
walked as written, which is what makes recovery automatic without knowing anyone's reset hour.

The other contract here is provenance. `Answer.provider_id` and `Answer.model` name the pair that
*answered*, and `attempts` names every pair tried, oldest first. A fall-through that left `modelId`
naming the first choice would be a bug, so the answer is rewritten as it comes back out rather than
assembled by the caller from what it asked for.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Callable, Sequence, TypeVar

from acervo.models import journal
from acervo.models.catalogue import Catalogue, Row, available, reason
from acervo.models.cooldown import rests, retry_after_of
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable

Result = TypeVar("Result")

Choice = str | tuple[str, str]
"""One entry in a chain: a whole row, or one of its models.

A bare id is shorthand for "this row, every model it offers for this kind, in the order it lists
them" — the shape `ACERVO_TEXT_CHAIN` writes, because a deploy-time flag should pin a provider and
leave the models to the catalogue. A pair is "this row, exactly this model" — the shape the owner's
record stores, because a free tier is metered per model and the owner is choosing buckets rather
than vendors.

A widening rather than an overload: an id names a *group* of pairs, not a second kind of thing.
`Candidate.named` and `Answer.attempts` are already this tuple, so a stored choice and a recorded
attempt are the same shape and can be compared without a mapping layer.
"""


@dataclass(frozen=True)
class Candidate:
    """One thing that can be asked: a row and one of its models for a kind."""

    row: Row
    model: str

    @property
    def named(self) -> tuple[str, str]:
        return (self.row.id, self.model)


def _named(choice: Choice) -> tuple[str, str | None]:
    """A choice as (row id, model or None). None means "every model this row offers"."""
    return (choice, None) if isinstance(choice, str) else (choice[0], choice[1])


def resolve(
    kind: str, chosen: Sequence[Choice] | None, catalogue: Catalogue
) -> tuple[Candidate, ...]:
    """The pairs that will be tried, in order.

    `None` means nothing has been chosen: every credentialed row that serves this kind in catalogue
    order, each row's models in the order it lists them — so a deployment that has configured one
    provider needs no chain setting at all.

    An **empty** sequence is not the same thing. It means every model was switched off deliberately,
    and it resolves to nothing at all. The distinction is the whole reason this takes a `Sequence |
    None` rather than a list: "I have not chosen" and "I choose none" look identical in a list and
    mean opposite things, and conflating them made unticking the last model silently fall back to
    the server's order.

    Otherwise, exactly the choices given, in that order.

    **A retired model is refused; an uncredentialed row is skipped.** The line is whether the state
    is legitimate. Not holding a key is expected — ordering three providers on a deployment that
    holds one key is the entire point of a chain. A pair naming a model the catalogue does not offer
    is a state nothing is supposed to produce, and skipping it is silently wrong twice over: retire
    both of a row's models and `unconfigured()` would report a key as missing when it is plainly
    set, and retire one and capture would quietly walk half the chain the owner configured, forever,
    with no symptom.
    """
    if chosen is None:
        return tuple(
            Candidate(row, model)
            for row in catalogue.serving(kind)
            if available(row)
            for model in row.models_for(kind)
        )

    found: list[Candidate] = []
    for choice in chosen:
        identifier, model = _named(choice)
        try:
            row = catalogue.find(identifier)
        except KeyError:
            raise ProviderRefused(
                "configuration", f"no provider {identifier!r} is in the catalogue"
            ) from None
        if not row.serves(kind):
            raise ProviderRefused("configuration", f"provider {identifier!r} does not serve {kind}")
        offered = row.models_for(kind)
        # Before the credential check, deliberately: otherwise the same stored record is a refusal
        # on a server holding the key and a silent skip on one that does not, so the error would
        # depend on the environment rather than on the record.
        if model is not None and model not in offered:
            raise ProviderRefused(
                "configuration", f"provider {identifier!r} does not offer {model!r} for {kind}"
            )
        if not available(row):
            continue
        found.extend(Candidate(row, one) for one in ((model,) if model else offered))
    # A pair named twice would fail twice, double the latency of an exhausted chain and appear twice
    # in `attempts`. First occurrence wins, so the owner's order is untouched.
    return tuple({candidate.named: candidate for candidate in found}.values())


def unconfigured(
    kind: str, chosen: Sequence[Choice] | None, catalogue: Catalogue
) -> ProviderRefused:
    """Why nothing can serve this kind, named as an environment variable rather than a value.

    It reports the *first* row that would have served, so the message is about the provider the
    deployment is closest to having, rather than about the last one in the file.
    """
    if chosen is not None and not chosen:
        return ProviderRefused("unconfigured", f"no model is switched on for {kind}")
    rows = (
        [catalogue.find(_named(choice)[0]) for choice in chosen]
        if chosen
        else list(catalogue.serving(kind))
    )
    detail = next(
        (reason(row) for row in rows if reason(row) is not None),
        f"no provider in the catalogue serves {kind}",
    )
    return ProviderRefused("unconfigured", detail or "")


def walk(
    kind: str,
    chosen: Sequence[Choice] | None,
    catalogue: Catalogue,
    ask: Callable[[Candidate], Result],
    stamp: Callable[[Result, tuple[tuple[str, str], ...], tuple[tuple[str, str, str], ...]], Result],
    caller: str = "text",
) -> Result:
    """Ask each pair in turn until one answers.

    `stamp` writes the attempt list into whatever `ask` returned, because only this function knows
    how many pairs were tried and only the caller knows the shape of its own result.

    `caller` names the job for the journal — "brief", "clips", "capture". This is the one place that
    sees every attempt and its outcome, so it is the one place worth writing them down from; without
    it a chain that walked nine pairs left no trace but a `passedOver` array in a reply that may
    never have come.
    """
    candidates = resolve(kind, chosen, catalogue)
    if not candidates:
        raise unconfigured(kind, chosen, catalogue)

    # Rested pairs go last rather than away: `ready` hands back everything when everything is
    # resting, so a remembered refusal can never empty a chain that has members.
    awake = rests.ready([candidate.named for candidate in candidates])
    order = sorted(candidates, key=lambda candidate: candidate.named not in awake)

    attempts: list[tuple[str, str]] = []
    passed_over: list[tuple[str, str, str]] = []
    last: ProviderUnavailable | None = None
    for candidate in order:
        attempts.append(candidate.named)
        started = time.monotonic()
        try:
            answer = stamp(ask(candidate), tuple(attempts), tuple(passed_over))
        except ProviderUnavailable as error:
            rests.note(candidate.named, error.reason, retry_after=retry_after_of(error))
            passed_over.append((*candidate.named, error.reason))
            journal.passed(caller, *candidate.named, error.reason, str(error))
            last = error
        else:
            rests.succeeded(candidate.named)
            journal.answered(caller, *candidate.named, time.monotonic() - started)
            return answer
    assert last is not None
    reasons = tuple(reason for _, _, reason in passed_over)
    journal.exhausted(caller, len(attempts), reasons)
    raise ChainExhausted(tuple(attempts), last, reasons)


def stamped(
    result,
    attempts: tuple[tuple[str, str], ...],
    passed_over: tuple[tuple[str, str, str], ...] = (),
):
    """Rewrite a result's answer with what was tried, and what was passed over on the way.

    The provenance contract, applied — and the passed-over list is what lets a caller say a
    fall-through happened at all. Without it, a provider that is quietly broken is indistinguishable
    from one nobody chose.
    """
    return replace(
        result, answer=replace(result.answer, attempts=attempts, passed_over=passed_over)
    )
