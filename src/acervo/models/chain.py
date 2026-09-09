"""A chain of rows, walked in order, falling through on 429 and 5xx and never on anything else.

That rule is the locked one and it is the whole of this module's judgement. An authentication
failure or a rejected configuration is a mistake to fix, not a condition to route around: falling
through on it hides the mistake and spends money at the next provider. So `ProviderUnavailable`
moves to the next row and `ProviderRefused` stops the walk where it happened.

The other contract here is provenance. `Answer.provider_id` names the row that *answered*, and
`attempts` names every row tried, oldest first. A fall-through that left `modelId` naming the first
choice would be a bug, so the answer is rewritten as it comes back out rather than assembled by the
caller from what it asked for.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Sequence, TypeVar

from acervo.models.catalogue import Catalogue, Row, available, reason
from acervo.models.errors import ChainExhausted, ProviderRefused, ProviderUnavailable

Result = TypeVar("Result")


def resolve(kind: str, ids: Sequence[str] | None, catalogue: Catalogue) -> tuple[Row, ...]:
    """The rows that will be tried, in order.

    With no ids, every credentialed row that serves this kind, in catalogue order — so a deployment
    that has configured one provider needs no chain setting at all, and one that has configured
    three gets them in the order the file lists. With ids, exactly those, skipping the ones this
    deployment has no credentials for.

    An id that is not in the catalogue is a mistake in the configuration, not a row to skip past.
    """
    serving = catalogue.serving(kind)
    if not ids:
        return tuple(row for row in serving if available(row))

    chosen: list[Row] = []
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
            chosen.append(row)
    return tuple(chosen)


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
    ask: Callable[[Row], Result],
    stamp: Callable[[Result, tuple[str, ...]], Result],
) -> Result:
    """Ask each row in turn until one answers.

    `stamp` writes the attempt list into whatever `ask` returned, because only this function knows
    how many rows were tried and only the caller knows the shape of its own result.
    """
    rows = resolve(kind, ids, catalogue)
    if not rows:
        raise unconfigured(kind, ids, catalogue)

    attempts: list[str] = []
    last: ProviderUnavailable | None = None
    for row in rows:
        attempts.append(row.id)
        try:
            return stamp(ask(row), tuple(attempts))
        except ProviderUnavailable as error:
            last = error
    assert last is not None
    raise ChainExhausted(tuple(attempts), last)


def stamped(result, attempts: tuple[str, ...]):
    """Rewrite a result's answer with the rows actually tried. The provenance contract, applied."""
    return replace(result, answer=replace(result.answer, attempts=attempts))
