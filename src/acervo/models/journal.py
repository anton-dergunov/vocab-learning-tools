"""What was asked of which model, and what came back.

There was no record of any of this. A chain could walk nine pairs, be refused by every one for the
same reason, sleep four minutes and walk them again — and leave behind a `passedOver` array inside
whichever response eventually succeeded, or nothing at all if none did. Working out *why* a picture
took six minutes meant reading the code and guessing, which is how a schema that asked for one field
out of eight survived two deployments.

So: **one line per attempt**, written where `chain.walk` already knows the outcome. The line names
the caller, the pair, what happened, how long it took, and — when the answer was refused for its
shape — the reason it was refused. That last part is the one that pays: it is the difference between
"unusable" and "it returned only senseId".

**The package emits; it does not configure.** `acervo.models` may not import `Settings`
(`test_layering.py`), and it should not care where a log lives in any case. It writes to an ordinary
logger and stops there; `services/models.py`, which already reads `Settings`, decides whether that
goes to a file and where. A deployment that installs no handler loses the lines and nothing else.

Nothing here formats a credential. Every detail on a `ProviderError` is redacted at construction
(`redact.py`), which is the property this module leans on rather than re-implements — a message
cleaned only on its way to a log has a path that skips the cleaning, and this repository is public.
"""

from __future__ import annotations

import logging

# The name a handler attaches to. Deliberately not `acervo.models`, so installing a file for this
# does not also capture whatever else the package might one day log.
LOGGER = "acervo.models.calls"

logger = logging.getLogger(LOGGER)

# How much of a rejected answer is worth keeping. Enough to see the shape of what came back —
# whether it was prose, an empty object, or an object with one field of eight — and not so much
# that a chatty model fills the file. A reply is truncated rather than summarised: a summary of
# malformed output is one more thing that can be wrong.
EXCERPT = 400


def excerpt(text: str) -> str:
    """A bounded, single-line view of a reply, for the detail of a shape refusal."""
    flattened = " ".join((text or "").split())
    return flattened if len(flattened) <= EXCERPT else flattened[:EXCERPT] + "…"


def answered(caller: str, provider: str, model: str, seconds: float) -> None:
    logger.info("%s %s:%s ok in %.2fs", caller, provider, model, seconds)


def passed(caller: str, provider: str, model: str, reason: str, detail: str) -> None:
    """One pair that did not answer, and the reason the next one is being asked.

    At `warning`, because every one of these costs a call and some of them cost a minute. A run that
    is quietly walking the whole chain on every word should be visible at the default level rather
    than only to somebody who thought to turn logging up.
    """
    logger.warning("%s %s:%s %s — %s", caller, provider, model, reason, detail)


def exhausted(caller: str, attempts: int, reasons: tuple[str, ...]) -> None:
    logger.error("%s exhausted after %d attempt(s): %s", caller, attempts, ", ".join(reasons))
