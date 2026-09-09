"""A chain of (provider, model) pairs, walked in order.

It falls through on 429 and 5xx and never on anything else. That rule is the locked one and it is
the whole of this module's judgement: an authentication failure or a rejected configuration is a
mistake to fix, not a condition to route around, and falling through on it hides the mistake and
spends money at the next provider.

**The unit is a pair, not a provider.** A free tier is metered per model, so two models with 500
requests a day each are a thousand requests a day and the second is reached by the first one's 429.
The default walk is therefore provider by provider and, inside each, model by model — the order the
catalogue lists them in.

The other contract here is provenance. `Answer.provider_id` and `Answer.model` name the pair that
*answered*, and `attempts` names every pair tried, oldest first. A fall-through that left `modelId`
naming the first choice would be a bug, so the answer is rewritten as it comes back out rather than
assembled by the caller from what it asked for.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Sequence, TypeVar

from acervo.models.catalogue import Catalogue, Row, available, reason
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable

Result = TypeVar("Result")


@dataclass(frozen=True)
class Candidate:
    """One thing that can be asked: a row and one of its models for a kind."""

    row: Row
    model: str

    @property
    def named(self) -> tuple[str, str]:
        return (self.row.id, self.model)


def resolve(kind: str, ids: Sequence[str] | None, catalogue: Catalogue) -> tuple[Candidate, ...]:
    """The pairs that will be tried, in order.

    With no ids, every credentialed row that serves this kind in catalogue order, each row's models
    in the order it lists them — so a deployment that has configured one provider needs no chain
    setting at all, and one that has configured three gets them in the order the file lists.

    With ids, exactly those rows in that order, skipping the ones this deployment has no credentials
    for. An id that is not in the catalogue is a mistake in the configuration, not a row to skip
    past; choosing *which* of a row's models to use is plan 03's, and this list is what it chooses
    from.
    """
    if not ids:
        rows = [row for row in catalogue.serving(kind) if available(row)]
    else:
        rows = []
        for identifier in ids:
            try:
                row = catalogue.find(identifier)
            except KeyError:
                raise ProviderRefused(
                    "configuration", f"no provider {identifier!r} is in the catalogue"
                ) from None
            if not row.serves(kind):
                raise ProviderRefused(
                    "configuration", f"provider {identifier!r} does not serve {kind}"
                )
            if available(row):
                rows.append(row)
    return tuple(
        Candidate(row, model) for row in rows for model in row.models_for(kind)
    )


def unconfigured(kind: str, ids: Sequence[str] | None, catalogue: Catalogue) -> ProviderRefused:
    """Why nothing can serve this kind, named as an environment variable rather than a value.

    It reports the *first* row that would have served, so the message is about the provider the
    deployment is closest to having, rather than about the last one in the file.
    """
    candidates = [catalogue.find(i) for i in ids] if ids else list(catalogue.serving(kind))
    detail = next(
        (reason(row) for row in candidates if reason(row) is not None),
        f"no provider in the catalogue serves {kind}",
    )
    return ProviderRefused("unconfigured", detail or "")


def walk(
    kind: str,
    ids: Sequence[str] | None,
    catalogue: Catalogue,
    ask: Callable[[Candidate], Result],
    stamp: Callable[[Result, tuple[tuple[str, str], ...]], Result],
) -> Result:
    """Ask each pair in turn until one answers.

    `stamp` writes the attempt list into whatever `ask` returned, because only this function knows
    how many pairs were tried and only the caller knows the shape of its own result.
    """
    candidates = resolve(kind, ids, catalogue)
    if not candidates:
        raise unconfigured(kind, ids, catalogue)

    attempts: list[tuple[str, str]] = []
    last: ProviderUnavailable | None = None
    for candidate in candidates:
        attempts.append(candidate.named)
        try:
            return stamp(ask(candidate), tuple(attempts))
        except ProviderUnavailable as error:
            last = error
    assert last is not None
    raise ChainExhausted(tuple(attempts), last)


def stamped(result, attempts: tuple[tuple[str, str], ...]):
    """Rewrite a result's answer with the pairs actually tried. The provenance contract, applied."""
    return replace(result, answer=replace(result.answer, attempts=attempts))
