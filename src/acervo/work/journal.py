"""What the runner did, one line each — the second of Acervo's two logs.

`acervo.models.journal` records every *model call*: which pair answered, how fast, what was done
with the answer. It cannot say why a job failed, because most of the ways a job fails are not model
calls at all — a companion service that refused, a file that could not be written, a render that
died on a missing sample pack. Before this, that class of failure was recorded **only** in the job
row's JSON, reachable through the web interface and nowhere else: `docker logs` showed an access-log
status code, and `admin jobs list` showed open jobs alone. A four-minute loop failed and the server
said nothing.

Shaped exactly like the model-call journal, deliberately:

- `key=value` pairs, so `grep 'kind=loop' jobs.log | grep state=failed` is a question with an answer;
- this module **emits and never configures**, so the level, the file and the rotation are the
  deployment's business and a test can read the records without one;
- `open_job_log` is idempotent and a log that cannot be opened warns and is dropped — a server that
  cannot write its log should still do its work.

**`operationId` is here for one reason**: it is the only id shared between Acervo's containers and
the generator's. Until this line existed it lived in the database and in no log, so a failed render
in one container's log could not be joined to its cause in the other's.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Any, Mapping

# Its own logger, not `acervo.work`, so the runner's exception traces and this record can be routed
# apart: one belongs in the container's stderr and the other in a file beside the database.
LOGGER = "acervo.work.jobs"
logger = logging.getLogger(LOGGER)

# Long enough for a provider's own sentence, short enough that one bad message cannot fill the file.
EXCERPT = 400


def excerpt(value: str) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1] + "…"


def _render(fields: Mapping[str, Any]) -> str:
    parts = []
    for name, value in fields.items():
        if value is None or value == "":
            continue
        if isinstance(value, float):
            rendered = f"{value:.2f}"
        elif isinstance(value, str) and (not value.isprintable() or any(c in value for c in ' "=')):
            rendered = json.dumps(excerpt(value), ensure_ascii=False)
        else:
            rendered = str(value)
        parts.append(f"{name}={rendered}")
    return " ".join(parts)


def started(job: Mapping[str, Any]) -> None:
    subject = job.get("subject") or {}
    logger.info("job start %s", _render({
        "id": job.get("id"), "kind": job.get("kind"), "trigger": job.get("trigger"),
        "subject": f"{subject.get('kind', '')}:{subject.get('id', '')}".strip(":"),
        "owner": job.get("ownerId"),
    }))


def step(job_id: str, kind: str, name: str, state: str, **fields: Any) -> None:
    """One line per step outcome. `waiting` is not logged: a render polls hundreds of times."""
    failed = state == "failed"
    (logger.warning if failed else logger.info)("job step %s", _render({
        "id": job_id, "kind": kind, "step": name, "state": state, **fields,
    }))


def finished(job: Mapping[str, Any], state: str, seconds: float,
             error: str | None = None, message: str | None = None) -> None:
    subject = job.get("subject") or {}
    failed = state in ("failed", "cancelled")
    (logger.warning if failed else logger.info)("job end %s", _render({
        "id": job.get("id"), "kind": job.get("kind"), "state": state,
        "subject": f"{subject.get('kind', '')}:{subject.get('id', '')}".strip(":"),
        "seconds": float(seconds), "error": error, "message": message,
    }))


def open_job_log(settings: Any) -> None:
    """Point this journal at a file, if the deployment wants one. `open_call_log`'s twin.

    Idempotent, because the runner is built more than once in the tests and a second handler would
    double every line. An empty path means the lines are emitted and nothing listens, which is the
    right default for a laptop and costs nothing.
    """
    path = getattr(settings, "job_log_path", None)
    if not path:
        return
    if any(getattr(handler, "acervo_job_log", False) for handler in logger.handlers):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=settings.job_log_bytes, backupCount=settings.job_log_keep,
            encoding="utf-8",
        )
    except OSError as unwritable:   # noqa: BLE001 — a log nobody can write must not stop the work
        logging.getLogger("acervo.work").warning(
            "Acervo: the job log could not be opened (%s); jobs will not be recorded", unwritable)
        return
    handler.acervo_job_log = True   # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Its own file. Letting it climb to the root handler too would put every step in the container's
    # stdout beside the request log, which is the noise this exists to replace.
    logger.propagate = False
