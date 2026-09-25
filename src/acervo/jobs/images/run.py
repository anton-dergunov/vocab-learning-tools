"""Plan the work, do it concurrently, and be resumable by looking at the filesystem.

The output directory is the state. A sense whose `.webp` exists is done; delete the file and the
next run draws it again — with a fresh brief and a fresh seed, because deleting a picture is how
you say you disliked it, and handing back the same one would be useless.

Nothing here writes to the graph. It is read once at the start of a run.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet, Any, Callable, Iterable, Sequence

from acervo.article import ArticleView, SenseView
from acervo.images.brief import BriefWriter, SenseBrief
from acervo.images.compose import compose, prompt_version
from acervo.images.ids import image_prompt_id, image_reference, seed_for
from acervo.images.render import Rendered, Renderer
from acervo.images.styles import StyleTable
from acervo.models import ChainExhausted, ProviderRefused, ProviderUnavailable, chain
from acervo.models.cooldown import retry_after_of
from acervo.models.pacing import Key, ModelPool


# Whole-chain walks a brief is worth before the run gives up on that word.
BRIEF_ATTEMPTS = 6


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

    def is_blocked(self, prompt_id: str) -> bool:
        """The image provider declined this prompt. Terminal, like a writer refusal."""
        record = self.read(self.record_path(prompt_id))
        return bool(record and record.get("blocked"))

    def is_refused(self, prompt_id: str) -> bool:
        """A refusal is a finished outcome, not a gap.

        A sense the writer declines (`docs/features/sense-images.md` §04) gets no picture and is not
        retried. Without this every later run spends a text call rediscovering the same refusal —
        `joder` was re-planned on every Spanish pass. Delete the file under `refusals/` to ask
        again.
        """
        return self.refusal_path(prompt_id).exists()

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

    def write_image(self, prompt_id: str, data: bytes) -> None:
        """The drawn master, under the flat local name the run is resumable by.

        The *server* path carries a digest of these bytes; this one deliberately does not. A run
        directory is resumed by looking at the filesystem — `is_drawn` asks whether this sense has a
        picture — and a name that changed with the bytes could not answer that.
        """
        path = self.image_path(prompt_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_suffix(path.suffix + ".part")
        staging.write_bytes(data)
        staging.replace(path)

    def attempts(self, prompt_id: str) -> int:
        record = self.read(self.record_path(prompt_id)) or self.read(self.refusal_path(prompt_id))
        return int((record or {}).get("attempts", 0))


def plan(articles: Iterable[ArticleView], store: Store, *, drawn: AbstractSet[str],
         redo: bool = False, only: Iterable[str] | None = None) -> list[Job]:
    """Every sense that has no picture yet, in a stable order.

    Re-reading the graph on every run is what makes this pick up words ingested since last time:
    the work is derived from the data, never from a queue. That is also why `--limit` alone cannot
    name a set of senses — the graph grows underneath it and the alphabet shifts. `only` names them:
    a headword, a sense id, or an image id.

    `drawn` is `images.article.drawn_senses(changes)` — required rather than defaulted, because an
    empty default reads as "nothing has a picture" and would redraw every sense in the account.
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
            if sense.id in drawn and not redo:
                continue          # the graph already holds a drawn image for this sense
            if store.is_drawn(prompt_id) and not redo:
                continue          # this run directory already holds one
            if store.is_refused(prompt_id) and not redo:
                continue          # the writer declined, which is a successful outcome
            if store.is_blocked(prompt_id) and not redo:
                continue          # the image provider declined; §01, a sense with no image is fine
            jobs.append(Job(article=article, sense=sense, prompt_id=prompt_id))
    return jobs


class Runner:
    def __init__(self, store: Store, writer: BriefWriter, renderer: Renderer, styles: StyleTable,
                 template_path: str | Path, *, candidates: Sequence[chain.Candidate],
                 workers: int = 6, rate_limit: int = 0,
                 attempts: int = 4, report: Callable[[str], None] = print,
                 wait: Callable[[float], None] = time.sleep) -> None:
        self.store = store
        self.writer = writer
        self.renderer = renderer
        self.styles = styles
        self.version = prompt_version(template_path, styles.digest)
        self.workers = workers
        self.attempts = max(1, attempts)
        self.wait = wait
        self.candidates = tuple(candidates)
        if not self.candidates:
            raise ValueError("An image run needs at least one (provider, model) pair.")
        self._by_pair = {candidate.named: candidate for candidate in self.candidates}
        # The text calls are cheap and generous; the image pairs are the scarce ones, and each has
        # its own bucket, so each gets its own gate and a job takes whichever is free soonest.
        #
        # This is the pool's chain walk, and deliberately *not* `chain.walk`: a sweep wants
        # whichever pair is free soonest rather than a fixed order, and the pool's own `Pace` is
        # already the cooldown. Do not add `cooldown.rests` beside it — two mechanisms would
        # disagree about the ordering and neither would be in charge.
        self.pace = ModelPool([(candidate.named, rate_limit) for candidate in self.candidates])
        # Set by an authentication or configuration refusal: a mistake to fix, not a condition to
        # route around. Every other job then returns at once rather than marking 500 senses blocked.
        self._stop: ProviderRefused | None = None
        self.report = report
        self._lock = threading.Lock()
        self._brief_locks: dict[str, threading.Lock] = {}
        self._refreshed: set[str] = set()
        self.stats = {"drawn": 0, "refused": 0, "failed": 0, "throttled": 0}
        # What each pair actually drew, and what it was billed. `None` from a provider that does
        # not price its answer is a legal reading, not a zero — Cloudflare inside its free
        # allocation genuinely costs nothing and outside it is priced per neuron.
        self.by_pair: Counter[Key] = Counter()
        self.cost_usd = 0.0
        self.unpriced = 0

    def _brief_lock(self, lexeme_id: str) -> threading.Lock:
        with self._lock:
            return self._brief_locks.setdefault(lexeme_id, threading.Lock())

    def _write(self, article: ArticleView) -> tuple[list[SenseBrief], dict[str, Any]]:
        """Write the briefs, waiting out a chain that is entirely over quota.

        This run is the one place that decides to wait: a long unattended run eventually meets a
        daily allowance, and without the ladder a 429 loses every sense of that lexeme. A chain that
        only answered badly is not waiting for anything, so it is raised at once.
        """
        for attempt in range(1, BRIEF_ATTEMPTS + 1):
            try:
                return self.writer.write(article)
            except ChainExhausted as exhausted:
                if attempt == BRIEF_ATTEMPTS or exhausted.waited_on_nothing:
                    raise
                self.wait(min(15.0 * 2 ** (attempt - 1), 240.0))
        raise AssertionError("unreachable")

    def _briefs_for(self, article: ArticleView,
                    refresh: bool = False) -> tuple[dict[str, SenseBrief], str]:
        """One text call per lexeme, cached, and reused by every sense of that lexeme in this run.

        `refresh` is set when a sense of this lexeme has been attempted before — you deleted the
        picture because you disliked it, and handing back the brief that produced it would waste the
        call. Refreshing happens at most once per lexeme per run.

        It returns the model that *wrote* the briefs alongside them, taken from the cache file on
        the cache path. Stamping the record with whatever model the chain names today would put a
        brief written by one model under another one's name — provenance that is wrong exactly when
        it is most wanted, which is after the chain has changed.
        """
        path = self.store.brief_path(article.id)
        with self._brief_lock(article.id):
            with self._lock:
                stale = refresh and article.id not in self._refreshed
                if stale:
                    self._refreshed.add(article.id)
            cached = None if stale else self.store.read(path)
            if cached and cached.get("promptVersion") == self.version:
                written_by = str((cached.get("usage") or {}).get("model") or "")
                return {
                    item["senseId"]: SenseBrief(
                        item["senseId"], item.get("styleId", ""), item.get("anchorExampleId"),
                        item.get("situation", ""), item.get("subject", ""), item.get("brief", ""),
                        bool(item.get("refused")), item.get("refusalReason"),
                    )
                    for item in cached.get("senses", [])
                }, written_by
            briefs, usage = self._write(article)
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
                if usage.get("costUsd") is None:
                    self.unpriced += 1
                else:
                    self.cost_usd += float(usage["costUsd"])
            return {item.sense_id: item for item in briefs}, str(usage.get("model") or "")

    def _run_one(self, job: Job) -> None:
        article, sense = job.article, job.sense
        label = f"{article.headword} · sense {sense.order + 1}"
        # A mistake, not a condition: once one job has met a bad key or a rejected configuration,
        # every remaining job returns without spending anything or writing a misleading record.
        if self._stop is not None:
            return
        attempts = self.store.attempts(job.prompt_id) + 1
        try:
            briefs, brief_model = self._briefs_for(article, refresh=attempts > 1)
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
        tried: list[Key] = []
        for attempt in range(1, self.attempts + 1):
            pair = self.pace.acquire()
            tried.append(pair)
            try:
                drawn = self.renderer.draw(prompt, seed, self._by_pair[pair])
                self.store.write_image(job.prompt_id, drawn.data)
                self.pace.succeeded(pair)
                break
            except ProviderRefused as refusal:
                if refusal.reason == "refused":
                    # The provider looked at the prompt and declined. Retrying is pointless and
                    # costs quota that a drawable sense could have had.
                    self._record(job, brief, brief_model, style.id, seed, prompt, attempts, None,
                                 str(refusal), 0.0, tried, blocked=True)
                    self.report(f"  · {label}: not drawn — {refusal}")
                    with self._lock:
                        self.stats["refused"] += 1
                    return
                # Authentication, or a configuration the provider rejected. Falling through would
                # hide the mistake and spend the next provider's money on it.
                with self._lock:
                    self._stop = refusal
                self._record(job, brief, brief_model, style.id, seed, prompt, attempts, None,
                             str(refusal), 0.0, tried)
                self.report(f"  ✗ {label}: {refusal} — stopping the run")
                with self._lock:
                    self.stats["failed"] += 1
                return
            except ProviderUnavailable as unavailable:
                failure = str(unavailable)
                if attempt == self.attempts:
                    break
                delay = self.pace.penalise(pair, retry_after_of(unavailable))
                with self._lock:
                    self.stats["throttled"] += 1
                self.report(f"  ⏳ {label}: {pair[0]}/{pair[1]} is resting {delay:.0f}s")

        if drawn is None:
            self._record(job, brief, brief_model, style.id, seed, prompt, attempts, None, failure,
                         0.0, tried)
            self.report(f"  ✗ {label}: {failure}")
            with self._lock:
                self.stats["failed"] += 1
            return

        elapsed = time.time() - started
        self._record(job, brief, brief_model, style.id, seed, prompt, attempts, drawn, None,
                     elapsed, tried)
        with self._lock:
            self.stats["drawn"] += 1
            self.by_pair[(drawn.answer.provider_id, drawn.answer.model)] += 1
            if drawn.answer.cost_usd is None:
                self.unpriced += 1
            else:
                self.cost_usd += drawn.answer.cost_usd
        self.report(f"  ✓ {label} · {style.id} · {elapsed:.1f}s · {len(drawn.data) // 1024} KiB")

    def _record(self, job: Job, brief: SenseBrief, brief_model: str, style_id: str, seed: int,
                prompt: str, attempts: int, drawn: Rendered | None, failure: str | None,
                elapsed: float, tried: Sequence[Key] = (), blocked: bool = False) -> None:
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
            # The model that wrote the brief — the one that *answered*, and for a cached brief
            # the one that answered when it was written rather than whatever the chain says now.
            "modelId": brief_model,
            "promptVersion": self.version,
            # The path this image will have on the server, carrying a digest of the bytes so a
            # device that cached an earlier picture for this sense misses rather than keeps it.
            # Locally the file is flat under `images/`, so a contact sheet and a Finder window are
            # both easy to work in; the import is what fans it out into per-lexeme directories.
            "imageRef": image_reference(article.id, job.prompt_id, drawn.data) if drawn else None,
            "imageModelId": (drawn.answer.model if drawn else None),
            # The sentence the scene was built from, so the article can put the picture under it.
            "exampleId": brief.anchor_example_id,
            "attempts": attempts,
            "failureReason": failure,
            # The provider looked at the prompt and declined, as opposed to a transport or quota
            # error. Terminal: `plan` will not offer this sense again.
            "blocked": blocked,
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
                "bytes": len(drawn.data) if drawn else 0,
                "seconds": round(elapsed, 2),
                # `tried` comes from the pool rather than from the answer: the pool is what walked
                # the pairs, so an answer names only the one that succeeded. Recording just that
                # would hide every fall-through, which is the thing worth seeing.
                "attempts": [list(pair) for pair in tried],
                "usage": {
                    "provider": drawn.answer.provider_id,
                    "model": drawn.answer.model,
                    "seconds": round(drawn.answer.seconds, 2),
                    "costUsd": drawn.answer.cost_usd,
                    "warnings": list(drawn.answer.warnings),
                } if drawn else None,
            },
        })

    def run(self, jobs: list[Job]) -> dict[str, Any]:
        started = time.time()
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(self._run_one, jobs))
        return {
            **self.stats,
            "jobs": len(jobs),
            "byPair": self.by_pair,
            # What the providers said it cost, never a table in this repository. A provider that
            # does not price its answer is counted rather than guessed at.
            "costUsd": round(self.cost_usd, 4),
            "unpriced": self.unpriced,
            "stopped": str(self._stop) if self._stop else None,
            "seconds": round(time.time() - started, 1),
        }
