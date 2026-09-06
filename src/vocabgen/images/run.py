"""Plan the work, do it concurrently, and be resumable by looking at the filesystem.

The output directory is the state. A sense whose `.webp` exists is done; delete the file and the
next run draws it again — with a fresh brief and a fresh seed, because deleting a picture is how
you say you disliked it, and handing back the same one would be useless.

Nothing here writes to PocketBase. The graph is read once at the start of a run.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .brief import BriefWriter, SenseBrief
from .compose import compose, prompt_version
from .graph import ArticleView, SenseView
from .ids import image_prompt_id, seed_for
from .pacing import ModelPool, is_quota_error
from .render import Rendered, RenderRefused, Renderer
from .styles import StyleTable


@dataclass
class Job:
    article: ArticleView
    sense: SenseView
    prompt_id: str

    @property
    def sense_id(self) -> str:
        return self.sense.id


class Store:
    """The run directory. `records/` is what a later import reads; `images/` is what you look at."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.records = self.root / "records"
        self.images = self.root / "images"
        self.briefs = self.root / "briefs"
        self.refusals = self.root / "refusals"
        for directory in (self.records, self.images, self.briefs, self.refusals):
            directory.mkdir(parents=True, exist_ok=True)

    def image_path(self, prompt_id: str) -> Path:
        return self.images / f"{prompt_id}.webp"

    def record_path(self, prompt_id: str) -> Path:
        return self.records / f"{prompt_id}.json"

    def refusal_path(self, prompt_id: str) -> Path:
        return self.refusals / f"{prompt_id}.json"

    def brief_path(self, lexeme_id: str) -> Path:
        return self.briefs / f"{lexeme_id}.json"

    def is_drawn(self, prompt_id: str) -> bool:
        path = self.image_path(prompt_id)
        return path.exists() and path.stat().st_size > 0

    def read(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def attempts(self, prompt_id: str) -> int:
        record = self.read(self.record_path(prompt_id)) or self.read(self.refusal_path(prompt_id))
        return int((record or {}).get("attempts", 0))


def plan(articles: Iterable[ArticleView], store: Store, *, redo: bool = False,
         only: Iterable[str] | None = None) -> list[Job]:
    """Every sense that has no picture yet, in a stable order.

    Re-reading the graph on every run is what makes this pick up words ingested since last time:
    the work is derived from the data, never from a queue. That is also why `--limit` alone cannot
    name a set of senses — the graph grows underneath it and the alphabet shifts. `only` names them:
    a headword, a sense id, or an image id.
    """
    wanted = {item.strip().lower() for item in (only or ()) if item.strip()}
    jobs: list[Job] = []
    for article in articles:
        for sense in article.senses:
            prompt_id = image_prompt_id(sense.id)
            if wanted and not (
                {article.headword.lower(), sense.id.lower(), prompt_id.lower()} & wanted
            ):
                continue
            if sense.has_image and not redo:
                continue          # the graph already holds a drawn image for this sense
            if store.is_drawn(prompt_id) and not redo:
                continue          # this run directory already holds one
            jobs.append(Job(article=article, sense=sense, prompt_id=prompt_id))
    return jobs


class Runner:
    def __init__(self, store: Store, writer: BriefWriter, renderer: Renderer, styles: StyleTable,
                 template_path: str | Path, *, workers: int = 6, rate_limit: int = 0,
                 attempts: int = 4, report: Callable[[str], None] = print) -> None:
        self.store = store
        self.writer = writer
        self.renderer = renderer
        self.styles = styles
        self.version = prompt_version(template_path, styles.digest)
        self.workers = workers
        self.attempts = max(1, attempts)
        # The text calls are cheap and generous; the image models are the scarce ones, and each has
        # its own bucket, so each gets its own gate and a job takes whichever is free soonest.
        self.pace = ModelPool([(model, rate_limit) for model in renderer.models])
        self.report = report
        self._lock = threading.Lock()
        self._brief_locks: dict[str, threading.Lock] = {}
        self._refreshed: set[str] = set()
        self.stats = {"drawn": 0, "refused": 0, "failed": 0, "throttled": 0,
                      "briefTokens": 0, "imageTokens": 0}
        self.by_model: Counter[str] = Counter()

    def _brief_lock(self, lexeme_id: str) -> threading.Lock:
        with self._lock:
            return self._brief_locks.setdefault(lexeme_id, threading.Lock())

    def _briefs_for(self, article: ArticleView, refresh: bool = False) -> dict[str, SenseBrief]:
        """One text call per lexeme, cached, and reused by every sense of that lexeme in this run.

        `refresh` is set when a sense of this lexeme has been attempted before — you deleted the
        picture because you disliked it, and handing back the brief that produced it would waste the
        call. Refreshing happens at most once per lexeme per run.
        """
        path = self.store.brief_path(article.id)
        with self._brief_lock(article.id):
            with self._lock:
                stale = refresh and article.id not in self._refreshed
                if stale:
                    self._refreshed.add(article.id)
            cached = None if stale else self.store.read(path)
            if cached and cached.get("promptVersion") == self.version:
                return {
                    item["senseId"]: SenseBrief(
                        item["senseId"], item.get("styleId", ""), item.get("anchorExampleId"),
                        item.get("situation", ""), item.get("subject", ""), item.get("brief", ""),
                        bool(item.get("refused")), item.get("refusalReason"),
                    )
                    for item in cached.get("senses", [])
                }
            briefs, usage = self.writer.write(article)
            self.store.write(path, {
                "lexemeId": article.id,
                "headword": article.headword,
                "language": article.language,
                "promptVersion": self.version,
                "writtenAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "usage": usage,
                "senses": [
                    {
                        "senseId": item.sense_id, "styleId": item.style_id,
                        "anchorExampleId": item.anchor_example_id, "situation": item.situation,
                        "subject": item.subject,
                        "brief": item.brief, "refused": item.refused,
                        "refusalReason": item.refusal_reason,
                    }
                    for item in briefs
                ],
            })
            with self._lock:
                self.stats["briefTokens"] += int(usage.get("outputTokens") or 0)
            return {item.sense_id: item for item in briefs}

    def _run_one(self, job: Job) -> None:
        article, sense = job.article, job.sense
        label = f"{article.headword} · sense {sense.order + 1}"
        attempts = self.store.attempts(job.prompt_id) + 1
        try:
            briefs = self._briefs_for(article, refresh=attempts > 1)
        except Exception as error:  # noqa: BLE001 - one bad lexeme must not stop the run
            self.report(f"  ✗ {label}: brief failed — {error}")
            with self._lock:
                self.stats["failed"] += 1
            return

        brief = briefs.get(sense.id)
        if brief is None:
            self.report(f"  ✗ {label}: no brief was returned")
            with self._lock:
                self.stats["failed"] += 1
            return

        if brief.refused:
            self.store.write(self.store.refusal_path(job.prompt_id), {
                "id": job.prompt_id, "lexemeId": article.id, "senseId": sense.id,
                "headword": article.headword, "refusalReason": brief.refusal_reason,
                "promptVersion": self.version, "attempts": attempts,
            })
            self.report(f"  · {label}: refused — {brief.refusal_reason}")
            with self._lock:
                self.stats["refused"] += 1
            return

        style = self.styles[brief.style_id]
        prompt = compose(brief.brief, style)
        seed = seed_for(sense.id, attempts)
        started = time.time()
        drawn: Rendered | None = None
        failure = ""
        for attempt in range(1, self.attempts + 1):
            model = self.pace.acquire()
            try:
                drawn = self.renderer.draw(prompt, seed, self.store.image_path(job.prompt_id), model)
                self.pace.succeeded(model)
                break
            except RenderRefused as error:
                # The provider looked at the prompt and declined. Retrying is pointless and costs
                # quota that a drawable sense could have had.
                self._record(job, brief, style.id, seed, prompt, attempts, None, str(error), 0.0)
                self.report(f"  · {label}: not drawn — {error}")
                with self._lock:
                    self.stats["refused"] += 1
                return
            except Exception as error:  # noqa: BLE001 - transport, quota, anything
                failure = str(error)
                if not is_quota_error(error) or attempt == self.attempts:
                    break
                delay = self.pace.penalise(model)
                with self._lock:
                    self.stats["throttled"] += 1
                self.report(f"  ⏳ {label}: {model} over quota, it waits {delay:.0f}s")

        if drawn is None:
            self._record(job, brief, style.id, seed, prompt, attempts, None, failure, 0.0)
            self.report(f"  ✗ {label}: {failure}")
            with self._lock:
                self.stats["failed"] += 1
            return

        elapsed = time.time() - started
        self._record(job, brief, style.id, seed, prompt, attempts, drawn, None, elapsed)
        with self._lock:
            self.stats["drawn"] += 1
            self.stats["imageTokens"] += int(drawn.usage.get("outputTokens") or 0)
            self.by_model[str(drawn.usage.get("model") or "?")] += 1
        self.report(f"  ✓ {label} · {style.id} · {elapsed:.1f}s · {drawn.bytes_written // 1024} KiB")

    def _record(self, job: Job, brief: SenseBrief, style_id: str, seed: int, prompt: str,
                attempts: int, drawn: Rendered | None, failure: str | None, elapsed: float) -> None:
        """The row a later import will write, plus everything needed to explain or redo it.

        `prompt` is the brief — what §04 says is stored. `composedPrompt` is kept here in the run
        directory only, for reading back what was actually sent while we iterate on the template.
        """
        article, sense = job.article, job.sense
        anchor = next((example for example in sense.examples
                       if example.get("id") == brief.anchor_example_id), None)
        self.store.write(self.store.record_path(job.prompt_id), {
            "id": job.prompt_id,
            "lexemeId": article.id,
            "senseId": sense.id,
            "prompt": brief.brief,
            "styleId": style_id,
            "seed": seed,
            "modelId": self.writer.model,
            "promptVersion": self.version,
            # The path this image will have on the server. Locally the file is flat under
            # `images/`, so a contact sheet and a Finder window are both easy to work in; the
            # import is what fans it out into per-lexeme directories.
            "imageRef": f"images/{article.id}/{job.prompt_id}.webp" if drawn else None,
            "imageModelId": (drawn.usage.get("model") if drawn else None),
            "attempts": attempts,
            "failureReason": failure,
            "run": {
                "headword": article.headword,
                "language": article.language,
                "topics": article.topics,
                "senseOrder": sense.order,
                "situation": brief.situation,
                "subject": brief.subject,
                "definition": sense.definition,
                "glosses": sense.glosses,
                "anchorExample": {"text": anchor.get("text"), "translation": anchor.get("translation"),
                                  "origin": anchor.get("origin")} if anchor else None,
                "composedPrompt": prompt,
                "file": f"{job.prompt_id}.webp" if drawn else None,
                "bytes": drawn.bytes_written if drawn else 0,
                "seconds": round(elapsed, 2),
                "usage": drawn.usage if drawn else None,
            },
        })

    def run(self, jobs: list[Job]) -> dict[str, Any]:
        started = time.time()
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(self._run_one, jobs))
        return {**self.stats, "jobs": len(jobs), "byModel": self.by_model,
                "seconds": round(time.time() - started, 1)}
