"""Writing a verified run into the graph, and its images onto the server.

Phase B of the sense-image design. The run records already carry every column an `imagePrompt` has —
the id derived from the sense, the style the writer chose, the seed, both model ids and the prompt
version — so this is a plain write of rows that already know their ids, pointing at files put where
the records already say they are.

Two orderings matter and neither is arbitrary:

- **Files first, then rows.** A row whose file is missing is a broken `imageRef` in the database; a
  file whose row is missing is an orphan nobody looks at. One of those is visible to the owner.
- **Every check before any write.** A half-published run is worse than an unpublished one, so a
  record that cannot be written stops the whole publish rather than being skipped past.

`attempts` and `failureReason` now have columns and travel, so a run's terminal outcomes land with
its successes and the sweep does not re-plan them. `blocked` does not: it was the run directory's
word for a provider refusal, and in the graph that is a `failureReason` plus `suppressed`, so it is
translated here rather than carried as a third spelling of the same fact.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from acervo.client import AcervoClient
from acervo.domain.ids import now_instant
from acervo.jobs.images.run import Store
from acervo.jobs.images.verify import verify

# One `409 stale_record` refuses a whole batch, so a batch is a unit of retry as well as of writing.
BATCH = 100


@dataclass
class Published:
    written: int = 0
    copied: int = 0
    held: int = 0
    undrawn: int = 0
    problems: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems

    def fault(self, kind: str, subject: str) -> None:
        self.problems.setdefault(kind, []).append(subject)


def _wire(record: dict[str, Any], at: str, device: str) -> dict[str, Any]:
    """One run record as the graph route wants it.

    `revision: 0` says "this record is new"; the route refuses anything else for an id it has never
    held. The two timestamps are ours because the run does not keep them — a record's `createdAt` is
    when it reached the graph, not when the image was drawn.
    """
    return {
        "id": record["id"],
        "lexemeId": record["lexemeId"],
        "senseId": record["senseId"],
        "prompt": record["prompt"],
        "styleId": record["styleId"],
        "seed": record["seed"],
        "modelId": record["modelId"],
        "promptVersion": record["promptVersion"],
        "imageRef": record["imageRef"],
        "imageModelId": record["imageModelId"],
        "exampleId": record.get("exampleId"),
        "attempts": record.get("attempts", 0),
        "failureReason": record.get("failureReason") or "",
        # A provider that looked at the prompt and declined is finished, not pending. Recording it
        # as suppressed is what stops the sweep coming back to it every night forever.
        "suppressed": bool(record.get("blocked")),
        "deleted": False,
        "createdAt": at,
        "editedAt": at,
        "editedBy": device,
        "revision": 0,
    }


def plan_publish(store: Store, changes: dict[str, list[dict]]) -> tuple[list[dict], Published]:
    """What this run would write against this graph, and everything wrong with it.

    The senses are checked against the account because the ids in a run were read from whatever
    database it ran against. Re-import a bundle and every sense is minted afresh, which leaves a run
    pointing at senses nobody holds — and `verify` cannot see it, because a run directory is
    internally consistent either way. Saying so here is the difference between a clear refusal and a
    few thousand anonymous 400s.
    """
    outcome = Published()
    live_senses = {
        str(sense["id"]) for sense in changes.get("senses") or [] if not sense.get("deleted")
    }
    live_lexemes = {
        str(lexeme["id"]) for lexeme in changes.get("lexemes") or [] if not lexeme.get("deleted")
    }
    already = {str(prompt["id"]) for prompt in changes.get("imagePrompts") or []}

    queued: list[dict] = []
    for path in sorted(store.records.glob("*.json")):
        record = store.read(path)
        if record is None or "id" not in record:
            outcome.fault("unreadable record", path.name)
            continue
        identifier = str(record["id"])
        if identifier in already:
            outcome.held += 1
            continue
        if not record.get("imageRef"):
            # Refused by the writer or blocked by the provider. A finished outcome with no picture,
            # and nothing to publish.
            outcome.undrawn += 1
            continue
        if str(record.get("senseId") or "") not in live_senses:
            outcome.fault("names a sense this account does not hold", identifier)
            continue
        if str(record.get("lexemeId") or "") not in live_lexemes:
            outcome.fault("names a lexeme this account does not hold", identifier)
            continue
        if not store.is_drawn(identifier):
            outcome.fault("record claims an image that is not on disk", identifier)
            continue
        queued.append(record)
    return queued, outcome


def publish(
    store: Store,
    client: AcervoClient,
    *,
    media: Path,
    device_id: str,
    batch: int = BATCH,
    report: Callable[[str], None] = print,
) -> Published:
    """Copy the images and write the rows, or explain why neither happened."""
    internal = verify(store)
    if not internal.ok:
        outcome = Published(problems=dict(internal.problems))
        report("The run directory is not internally consistent; nothing was published.")
        return outcome

    queued, outcome = plan_publish(store, client.pull_graph().get("changes") or {})
    if not outcome.ok:
        for kind, subjects in outcome.problems.items():
            report(f"  ✗ {kind}: {len(subjects)} — first is {subjects[0]}")
        report("Nothing was published: a half-published run is worse than an unpublished one.")
        return outcome

    media = Path(media)
    for record in queued:
        # The record already says where the file belongs; locally it is flat, and this is the fan-out.
        destination = media / str(record["imageRef"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(store.image_path(str(record["id"])), destination)
        outcome.copied += 1
    report(f"Copied {outcome.copied} images into {media}")

    at = now_instant()
    for start in range(0, len(queued), batch):
        window = queued[start : start + batch]
        client.push_graph(
            {"imagePrompts": [_wire(record, at, device_id) for record in window]},
            device_id=device_id,
        )
        outcome.written += len(window)
        report(f"  wrote {outcome.written}/{len(queued)}")
    return outcome
